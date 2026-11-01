"""Filters that silently do nothing, size control, id collision, paging notes and event-loop blocking.

Every case here was reproduced against the live API first (2026-11): the upstream ignores `date` on
prec/detc/decc/special_decc, answers a comma list in `nb` and an agency name in `inq` with 0 / unrelated
rows, accepts unknown sort/search/cls values, ignores `page` on aiSearch, returns a 3.7 MB lsDelegated
body for 건축법 and resolves the same number as 자치법규ID and as 일련번호.
"""

import asyncio
import json
import pathlib
import threading
import time

import pytest

import lexlink.server as server_mod
from lexlink import guards
from lexlink._helpers import LOW_RELEVANCE_WARNING, low_relevance_warning
from lexlink.cache import ResponseCache, get_cache
from lexlink.linkage import parse_drlaw_html

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
FAKE_OC = "unit-test-oc"

PREC_LIST = {"PrecSearch": {"totalCnt": "2", "page": "1", "prec": [
    {"id": "1", "사건명": "손해배상(기)", "사건번호": "2023다1", "판례일련번호": "1"},
    {"id": "2", "사건명": "담보권 실행", "사건번호": "2023다2", "판례일련번호": "2"},
]}}
EXPC_LIST = {"Expc": {"totalCnt": "2", "page": "1", "expc": [
    {"id": "1", "안건명": "임차 관련 질의", "법령해석례일련번호": "1"},
    {"id": "2", "안건명": "임차", "법령해석례일련번호": "2"},
]}}


class RecordingClient:
    calls: list = []
    bodies: dict = {}
    delay = 0.0

    def __init__(self, *args, **kwargs):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        RecordingClient.calls.append((endpoint, dict(params)))
        if RecordingClient.delay:
            time.sleep(RecordingClient.delay)
        body = RecordingClient.bodies.get(params.get("target"), {})
        if callable(body):
            return body(endpoint, params, response_type)
        raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        return {"status": "ok", "request_id": "fake", "upstream_type": response_type, "raw_content": raw}


@pytest.fixture
def tool(monkeypatch):
    get_cache().invalidate()
    monkeypatch.setattr(server_mod, "LawAPIClient", RecordingClient)
    monkeypatch.setenv("OC", FAKE_OC)
    RecordingClient.calls = []
    RecordingClient.bodies = {"prec": PREC_LIST, "detc": {}, "expc": EXPC_LIST, "decc": {}}
    RecordingClient.delay = 0.0
    server = server_mod.create_server()
    yield lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)
    get_cache().invalidate()


def last_params():
    return RecordingClient.calls[-1][1]


# ---------- 1. date ----------

@pytest.mark.unit
@pytest.mark.parametrize("name,extra,upstream_key", [
    ("prec_search", {}, "prncYd"),
    ("detc_search", {}, "edYd"),
    ("decc_search", {}, "rslYd"),
    ("special_decc_search", {"tribunal": "조세심판원"}, "rslYd"),
])
def test_date_is_sent_as_one_day_range_and_shown(tool, name, extra, upstream_key):
    out = tool(name, date=20240111, **extra)
    assert out["status"] == "ok"
    p = last_params()
    assert p[upstream_key] == "20240111~20240111"
    assert "date" not in p
    assert out["filters_applied"] == {"date": "20240111", "applied_as": out["filters_applied"]["applied_as"]}
    assert out["filters_applied"]["applied_as"].endswith("=20240111~20240111")


@pytest.mark.unit
def test_date_conflicting_with_range_is_rejected(tool):
    out = tool("prec_search", date=20240111, prnc_yd="20240101~20240131")
    assert out["error_code"] == "VALIDATION_ERROR" and "date" in out["message"]
    assert RecordingClient.calls == []
    same = tool("prec_search", date=20240111, prnc_yd="20240111~20240111")
    assert same["status"] == "ok"


@pytest.mark.unit
def test_bad_date_is_rejected(tool):
    assert tool("detc_search", date=20261301)["error_code"] == "VALIDATION_ERROR"
    assert tool("decc_search", date=2024)["error_code"] == "VALIDATION_ERROR"


@pytest.mark.unit
def test_dpa_yd_warns_that_zero_rows_mean_little(tool):
    out = tool("decc_search", dpa_yd="20200101~20200131")
    assert any(w.startswith("dpa_yd_sparse") for w in out["warnings"])
    assert last_params()["dpaYd"] == "20200101~20200131"


# ---------- 2. nb ----------

@pytest.mark.unit
def test_prec_nb_comma_list_rejected_and_dash_form_converted(tool):
    out = tool("prec_search", nb="2023다287663,2024마7294")
    assert out["error_code"] == "VALIDATION_ERROR" and RecordingClient.calls == []
    tool("prec_search", nb="대법원-2025-두-34754")
    assert last_params()["nb"] == "2025두34754"


@pytest.mark.unit
def test_detc_nb_is_a_string_and_numeric_only_warns(tool):
    tool("detc_search", nb="2022헌마1312")
    assert last_params()["nb"] == "2022헌마1312"
    assert "query" not in last_params()      # upstream ignores nb when any query (even "*") is sent
    mixed = tool("detc_search", nb="2022헌마1312", query="신고")
    assert mixed["error_code"] == "VALIDATION_ERROR" and "query" in mixed["message"]
    out = tool("detc_search", nb=1312)
    assert last_params()["nb"] == "1312"
    assert any(w.startswith("nb_substring") for w in out["warnings"])
    assert tool("detc_search", nb="2022헌마1312,2017헌바323")["error_code"] == "VALIDATION_ERROR"


@pytest.mark.unit
def test_detc_nb_schema_accepts_string():
    server = server_mod.create_server()
    schema = server._tool_manager.get_tool("detc_search").parameters["properties"]["nb"]
    assert "string" in json.dumps(schema)


# ---------- 3. inq ----------

@pytest.mark.unit
def test_expc_inq_name_rejected_code_sent(tool):
    out = tool("expc_search", inq="국방부")
    assert out["error_code"] == "VALIDATION_ERROR" and "1290000" in out["message"]
    assert RecordingClient.calls == []
    tool("expc_search", inq=1290000)
    assert last_params()["inq"] == "1290000"


# ---------- 4. ranking field ----------

@pytest.mark.unit
def test_prec_ranking_uses_real_title_field(tool):
    out = tool("prec_search", query="담보권", display=5)
    titles = [r["사건명"] for r in out["ranked_data"]["prec"]]
    assert titles[0] == "담보권 실행"          # starts-with query ranks first (was a no-op with 판례명)


@pytest.mark.unit
def test_expc_ranking_uses_real_title_field(tool):
    out = tool("expc_search", query="임차", display=5)
    titles = [r["안건명"] for r in out["ranked_data"]["expc"]]
    assert titles[0] == "임차"                  # exact match first


@pytest.mark.unit
def test_explicit_sort_is_not_reordered_by_relevance(tool):
    out = tool("prec_search", query="담보권", display=5, sort="ddes")
    assert last_params()["sort"] == "ddes"
    assert "ranking_applied" not in out
    assert [r["사건명"] for r in out["ranked_data"]["prec"]] == ["손해배상(기)", "담보권 실행"]


# ---------- 5. display cap, enum validation, lm / sections ----------

@pytest.mark.unit
@pytest.mark.parametrize("name,extra", [
    ("prec_search", {}), ("expc_search", {}), ("decc_search", {}), ("detc_search", {}),
    ("special_decc_search", {"tribunal": "조세심판원"}),
])
def test_display_over_100_is_capped_with_warning(tool, name, extra):
    out = tool(name, display=500, **extra)
    assert last_params()["display"] == 100
    assert any(w.startswith("display_capped") for w in out["warnings"])
    exact = tool(name, display=100, **extra)
    assert not any(w.startswith("display_capped") for w in exact.get("warnings", []))


@pytest.mark.unit
@pytest.mark.parametrize("name,kw", [
    ("prec_search", {"sort": "zzz"}), ("prec_search", {"search": 9}),
    ("detc_search", {"sort": "dasc,x"}), ("detc_search", {"search": 3}),
    ("expc_search", {"sort": "efasc"}), ("expc_search", {"search": 0}),
    ("decc_search", {"sort": "bogus"}), ("decc_search", {"search": 9}), ("decc_search", {"cls": "zz"}),
    ("special_decc_search", {"tribunal": "조세심판원", "cls": "abc"}),
    ("special_decc_search", {"tribunal": "조세심판원", "sort": "efasc"}),
    ("prec_search", {"gana": "ㄱ"}),
])
def test_invalid_enum_values_are_validation_errors(tool, name, kw):
    out = tool(name, **kw)
    assert out["error_code"] == "VALIDATION_ERROR"
    assert RecordingClient.calls == []


@pytest.mark.unit
def test_valid_enum_values_pass(tool):
    assert tool("prec_search", search=3, sort="ndes")["status"] == "ok"
    assert tool("detc_search", sort="efdes")["status"] == "ok"
    assert tool("decc_search", cls="429022", search=2)["status"] == "ok"


@pytest.mark.unit
@pytest.mark.parametrize("name", ["prec_service", "detc_service", "expc_service", "decc_service"])
def test_sections_validated_and_lm_not_sent(tool, name):
    assert tool(name, id="1", sections="sumary")["error_code"] == "VALIDATION_ERROR"
    assert RecordingClient.calls == []
    out = tool(name, id="1", sections="Summary", lm="틀린 이름")
    assert "LM" not in last_params()
    assert any(w.startswith("lm_ignored") for w in out["warnings"])
    assert tool(name, id="2", sections="full")["status"] == "ok"


# ---------- 6. drlaw paging ----------

@pytest.mark.unit
def test_drlaw_rowspan_rows_keep_their_law():
    html = (FIXTURES / "drlaw_page_rowspan_trimmed.html").read_text(encoding="utf-8")
    parsed = parse_drlaw_html(html)
    assert parsed["total"] == 981 and len(parsed["rows"]) == 5
    last = parsed["rows"][-1]
    assert last["법령명"] == "노후계획도시 정비 및 지원에 관한 특별법" and last["소관부처"] == "국토교통부"
    assert last["조문"].startswith("제22조")
    assert last["자치법규수"]["전체"] == "4"       # was: 법령명 '4', 조문 '1'


@pytest.mark.unit
def test_drlaw_passes_display_and_page(tool):
    html = (FIXTURES / "drlaw_page_rowspan_trimmed.html").read_text(encoding="utf-8")
    RecordingClient.bodies["drlaw"] = html
    out = tool("drlaw_search", display=100, page=3)
    p = last_params()
    assert p["display"] == 100 and p["page"] == 3
    assert out["parsed_data"]["page"] == 3 and out["parsed_data"]["total"] == 981
    capped = tool("drlaw_search", display=500)
    assert last_params()["display"] == 100 and any(w.startswith("display_capped") for w in capped["warnings"])


# ---------- 7. lsDelegated jo ----------

DELEGATED = (FIXTURES / "lsDelegated_000798_trimmed.json").read_text(encoding="utf-8")


@pytest.mark.unit
def test_lsdelegated_jo_keeps_only_that_article(tool):
    RecordingClient.bodies["lsDelegated"] = DELEGATED
    out = tool("lsDelegated_service", id="000798", jo="2")
    items = json.loads(out["raw_content"])["lsDelegated"]["법령"]["위임조문정보"]
    assert [i["조정보"]["조문제목"] for i in items] == ["정의"]
    sel = out["selection"]
    assert sel["articles_with_delegation_in_law"] == 6 and sel["matched"] == 1
    assert sel["filtered_bytes"] < sel["original_bytes"]
    branch = tool("lsDelegated_service", id="000798", jo="제2조의2")
    assert json.loads(branch["raw_content"])["lsDelegated"]["법령"]["위임조문정보"][0]["조정보"]["조문가지번호"] == "2"
    assert len(json.loads(tool("lsDelegated_service", id="000798")["raw_content"])["lsDelegated"]["법령"]["위임조문정보"]) == 6


@pytest.mark.unit
def test_lsdelegated_jo_without_delegation_and_xml(tool):
    RecordingClient.bodies["lsDelegated"] = DELEGATED
    out = tool("lsDelegated_service", id="000798", jo=3)
    assert out["selection"]["matched"] == 0
    assert any(w.startswith("no_delegation_for_article") for w in out["warnings"])
    assert tool("lsDelegated_service", id="000798", jo=3, type="XML")["error_code"] == "VALIDATION_ERROR"
    assert tool("lsDelegated_service", id="000798", jo="abc")["error_code"] == "VALIDATION_ERROR"


@pytest.mark.unit
def test_lsdelegated_large_unfiltered_body_warns(tool):
    RecordingClient.bodies["lsDelegated"] = json.dumps({"lsDelegated": {"법령": {"위임조문정보": [], "x": "가" * 1_100_000}}})
    out = tool("lsDelegated_service", id="001823")
    assert any(w.startswith("large_response") for w in out["warnings"])


# ---------- 8. ordin id collision ----------

def _ordin(id_, serial, name, org):
    return json.dumps({"LawService": {"자치법규기본정보": {
        "자치법규ID": id_, "자치법규일련번호": serial, "자치법규명": name, "지자체기관명": org}}}, ensure_ascii=False)


JEONGEUP = _ordin("2116749", "2007843", "정읍시립도서관 관리운영 조례 시행규칙", "전북특별자치도 정읍시")
SEOUL = _ordin("2000120", "2116749", "서울특별시 건축 조례", "서울특별시")


def _ordin_upstream(endpoint, params, response_type):
    body = {"ID": {"2116749": JEONGEUP}, "MST": {"2116749": SEOUL}}
    key, val = ("ID", params.get("ID")) if params.get("ID") else ("MST", params.get("MST"))
    raw = body[key].get(str(val))
    if raw is None:
        return {"status": "error", "error_code": "NOT_FOUND", "message": "x", "request_id": "r"}
    return {"status": "ok", "request_id": "fake", "upstream_type": response_type, "raw_content": raw}


@pytest.mark.unit
def test_ordin_id_equal_to_other_serial_number_warns(tool):
    RecordingClient.bodies["ordin"] = _ordin_upstream
    out = tool("ordin_service", id="2116749")
    assert out["status"] == "ok" and "정읍시립도서관" in out["raw_content"]
    (w,) = [w for w in out["warnings"] if w.startswith("id_collision")]
    assert "서울특별시 건축 조례" in w and "mst=2116749" in w
    assert len(RecordingClient.calls) == 2           # the id lookup and the mst probe


@pytest.mark.unit
def test_ordin_serial_number_as_id_not_found_gets_hint(tool):
    RecordingClient.bodies["ordin"] = lambda e, p, t: (
        _ordin_upstream(e, p, t) if p.get("MST") else
        {"status": "error", "error_code": "NOT_FOUND", "message": "x", "request_id": "r"})
    out = tool("ordin_service", id="2116749")
    assert out["error_code"] == "NOT_FOUND"
    assert any(h.startswith("id_is_serial_number") for h in out["hints"])


@pytest.mark.unit
def test_ordin_no_collision_no_warning_and_mst_has_no_probe(tool):
    RecordingClient.bodies["ordin"] = lambda e, p, t: (
        {"status": "ok", "request_id": "r", "upstream_type": "JSON", "raw_content": JEONGEUP} if p.get("ID") else
        {"status": "error", "error_code": "NOT_FOUND", "message": "x", "request_id": "r"})
    out = tool("ordin_service", id="2116749")
    assert "warnings" not in out
    RecordingClient.calls = []
    tool("ordin_service", mst="2116749")
    assert len(RecordingClient.calls) == 1


@pytest.mark.unit
def test_ordin_probe_failure_is_reported_not_silent(tool):
    def flaky(e, p, t):
        if p.get("MST"):
            return {"status": "error", "error_code": "TIMEOUT", "message": "x", "request_id": "r"}
        return {"status": "ok", "request_id": "r", "upstream_type": "JSON", "raw_content": JEONGEUP}
    RecordingClient.bodies["ordin"] = flaky
    out = tool("ordin_service", id="2116749")
    assert any(w.startswith("id_check_skipped") for w in out["warnings"])


# ---------- 9. aiSearch / ls_rlt ----------

@pytest.mark.unit
def test_aisearch_page_over_one_warns_and_docs_say_seven(tool):
    RecordingClient.bodies["aiSearch"] = {"aiSearch": {"법령조문": [
        {"법령명": "형법", "조문제목": "도주", "조문내용": "도주한"}]}}
    out = tool("aiSearch", query="도주", page=2)
    assert any(w.startswith("page_ignored") for w in out["warnings"])
    assert "warnings" not in tool("aiSearch", query="도주")
    assert last_params()["display"] == 7
    doc = server_mod.create_server()._tool_manager.get_tool("aiSearch").description
    assert "default 7" in doc and "default 20" not in doc


@pytest.mark.unit
def test_colloquial_ppaengsoni_is_not_flagged():
    row = {"법령명": "특정범죄 가중처벌 등에 관한 법률", "조문제목": "도주차량 운전자의 가중처벌", "조문내용": "..."}
    assert low_relevance_warning("뺑소니", [row]) is None
    assert low_relevance_warning("뺑소니 처벌", [row]) is None
    assert low_relevance_warning("asdfqwer", [row]) == LOW_RELEVANCE_WARNING   # junk is still flagged


@pytest.mark.unit
def test_ls_rlt_zero_results_hints_exact_name(tool):
    RecordingClient.bodies["lsRlt"] = {"Law": "일치하는 관련법령 정보가 없습니다. 검색조건을 확인하여 주십시오."}
    out = tool("ls_rlt_search", query="주택임대차")
    assert out["warning"] == "no_results"
    assert guards.LS_RLT_EXACT_NAME_HINT in out["hints"]


# ---------- 10. event loop ----------

@pytest.mark.unit
def test_slow_sync_tool_does_not_block_other_calls(monkeypatch):
    """A blocking upstream call must not stop the loop from answering other tool calls."""
    monkeypatch.setattr(server_mod, "LawAPIClient", RecordingClient)
    monkeypatch.setenv("OC", FAKE_OC)
    get_cache().invalidate()
    RecordingClient.calls = []
    RecordingClient.bodies = {"lsDelegated": DELEGATED}
    RecordingClient.delay = 1.0
    server = server_mod.create_server()

    async def scenario():
        started = time.perf_counter()
        slow = asyncio.create_task(server.call_tool("lsDelegated_service", {"id": "000798"}))
        await asyncio.sleep(0.2)
        ping_start = time.perf_counter()
        await server.call_tool("cache_stats", {})
        ping = time.perf_counter() - ping_start
        await slow
        return ping, time.perf_counter() - started

    ping, total = asyncio.run(scenario())
    RecordingClient.delay = 0.0
    assert total >= 1.0
    assert ping < 0.5, f"cache_stats waited {ping:.2f}s behind a 1s blocking call"


@pytest.mark.unit
def test_tool_fn_stays_synchronous_and_cache_is_threadsafe():
    server = server_mod.create_server()
    assert not asyncio.iscoroutinefunction(server._tool_manager.get_tool("cache_stats").fn)
    cache = ResponseCache(max_entries=50)
    errors = []

    def hammer(n):
        try:
            for i in range(400):
                params = {"query": f"q{(i * n) % 97}", "type": "JSON"}
                cache.put("law", params, {"status": "ok", "raw_content": "x"})
                cache.get("law", params)
                if i % 50 == 0:
                    cache.invalidate()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=hammer, args=(n,)) for n in range(1, 9)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
