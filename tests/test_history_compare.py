"""Offline tests for the history / comparison / appendix / dictionary tools.

oldAndNew, thdCmp, lsJoHstInf, lsHstInf, delHst, lsAbrv, licbyl, lstrm. The real
LawAPIClient runs against an httpx.MockTransport, so upstream error detection
(NOT_FOUND, empty bodies) is the production code. Fixtures in tests/fixtures
are trimmed real responses with the OC masked.
"""

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import lexlink.server as server_mod
from lexlink.cache import get_cache
from lexlink.client import LawAPIClient
from lexlink.law_extras import (
    ascii_digits, filter_abbreviations, parse_lstrm_xml, select_thdcmp_article,
    validate_digits, validate_yyyymmdd, validate_ymd_range,
)
from lexlink._helpers import SLIM_MAX_BYTES, ToolValidationError, _json_size

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_OC = "unit-test-oc"


def fx(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    get_cache().invalidate()
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    monkeypatch.setenv("OC", FAKE_OC)
    yield
    get_cache().invalidate()


class Upstream:
    """Routes a request by (endpoint, target) to a (text) body; records the calls."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        q = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
        self.calls.append((request.url.path, q))
        route = self.routes.get((request.url.path, q.get("target")))
        body = route(q) if callable(route) else route
        if body is None:
            body = ""
        return httpx.Response(200, text=body, request=request)


@pytest.fixture
def call(monkeypatch):
    holder = {}

    def make(routes):
        up = Upstream(routes)

        def make_client(*a, **k):
            c = LawAPIClient(base_url="http://law.test")
            c.client = httpx.Client(transport=httpx.MockTransport(up.handler))
            return c

        monkeypatch.setattr(server_mod, "LawAPIClient", make_client)
        asyncio.set_event_loop(asyncio.new_event_loop())
        server = server_mod.create_server()
        holder["up"] = up
        return lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)

    make.holder = holder
    return make


SEARCH = "/DRF/lawSearch.do"
SERVICE = "/DRF/lawService.do"


def assert_error(out, code):
    assert out["status"] == "error", out
    assert out["error_code"] == code, out


# ---------------------------------------------------------------- pure validators

@pytest.mark.unit
@pytest.mark.parametrize("bad", ["20251301", "20250230", "2025-04-01", "2025040", "", "abcdefgh", None, "202504011"])
def test_validate_yyyymmdd_rejects(bad):
    with pytest.raises(ToolValidationError):
        validate_yyyymmdd(bad, "d")


@pytest.mark.unit
def test_validate_yyyymmdd_and_range_accept():
    assert validate_yyyymmdd(20250401, "d") == "20250401"
    assert validate_yyyymmdd("20240229", "d") == "20240229"
    assert validate_ymd_range("20250101~20251231", "r") == "20250101~20251231"
    for bad in ("20251231~20250101", "20250101", "20250101~2025", "20250101~20251301"):
        with pytest.raises(ToolValidationError):
            validate_ymd_range(bad, "r")


@pytest.mark.unit
def test_all_new_tools_registered(call):
    c = call({})
    server = server_mod.create_server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert len(names) == 66
    for n in ("oldAndNew_search", "oldAndNew_service", "lsJoHstInf_search", "lsHstInf_search",
              "delHst_search", "lsAbrv_search", "licbyl_search", "thdCmp_search",
              "thdCmp_service", "lstrm_search", "lstrm_service"):
        assert n in names
    assert c is not None


# ---------------------------------------------------------------- oldAndNew

@pytest.mark.unit
def test_old_and_new_search_rows_and_params(call):
    t = call({(SEARCH, "oldAndNew"): lambda q: fx("oldAndNew_list_minbeop.json")})
    out = t("oldAndNew_search", query="민법", ef_yd="20260101~20261231", rr_cls_cd="300203", sort="efdes")
    assert out["status"] == "ok"
    rows = out["ranked_data"]["oldAndNew"]
    assert isinstance(rows, list) and rows[0]["신구법일련번호"] == "284415"
    assert "rank" in rows[0] and "id" not in rows[0]
    q = call.holder["up"].calls[0][1]
    assert q["efYd"] == "20260101~20261231" and q["rrClsCd"] == "300203" and q["sort"] == "efdes"
    assert q["query"] == "민법" and q["display"] == "20"
    assert "OC=" not in json.dumps(out, ensure_ascii=False)  # links carry no credential


@pytest.mark.unit
def test_old_and_new_search_single_row_is_a_list(call):
    t = call({(SEARCH, "oldAndNew"): fx("oldAndNew_list_single.json")})
    rows = t("oldAndNew_search", query="가사소송법")["ranked_data"]["oldAndNew"]
    assert isinstance(rows, list) and len(rows) == 1 and rows[0]["신구법명"] == "가사소송법"


@pytest.mark.unit
def test_old_and_new_search_zero_rows_is_ok(call):
    body = json.dumps({"OldAndNewLawSearch": {"키워드": "zzz", "page": "1", "totalCnt": "0", "numOfRows": "0"}})
    out = call({(SEARCH, "oldAndNew"): body})("oldAndNew_search", query="zzz")
    assert out["status"] == "ok" and out["warning"] == "no_results"
    assert out["ranked_data"]["oldAndNew"] == []


@pytest.mark.unit
@pytest.mark.parametrize("kw", [
    {"ef_yd": "20269999~20261231"}, {"ef_yd": "20261231~20260101"}, {"anc_yd": "2026"},
    {"date": "20261301"}, {"rr_cls_cd": "999999"}, {"sort": "zzz"}, {"nb": "abc"},
    {"anc_no": "10~x"}, {"org": "abc"}, {"page": 0}, {"display": 0}, {"type": "CSV"},
])
def test_old_and_new_search_bad_args_never_reach_upstream(call, kw):
    t = call({(SEARCH, "oldAndNew"): fx("oldAndNew_list_minbeop.json")})
    assert_error(t("oldAndNew_search", query="민법", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_old_and_new_search_display_capped_and_page_past_end_hint(call):
    t = call({(SEARCH, "oldAndNew"): json.dumps({"OldAndNewLawSearch": {"totalCnt": "9", "page": "999", "numOfRows": "0"}})})
    out = t("oldAndNew_search", query="민법", display=500, page=999)
    assert call.holder["up"].calls[0][1]["display"] == "100"
    assert out["status"] == "ok" and any("no_more_results" in h for h in out["hints"])


@pytest.mark.unit
def test_old_and_new_service_ok_and_versions(call):
    t = call({(SERVICE, "oldAndNew"): fx("oldAndNew_body_273705.json")})
    out = t("oldAndNew_service", mst=273705)
    assert out["status"] == "ok"
    assert out["versions"]["new"]["mst"] == "273705" and out["versions"]["old"]["mst"] == "266723"
    assert out["versions"]["new"]["law_id"] == "011878"
    assert "warning" not in out
    assert call.holder["up"].calls[0][1]["MST"] == "273705"


@pytest.mark.unit
def test_old_and_new_service_mst_mismatch_warns(call):
    t = call({(SERVICE, "oldAndNew"): fx("oldAndNew_body_273705.json")})
    out = t("oldAndNew_service", mst="111")
    assert out["status"] == "ok" and "273705" in out["warning"]


@pytest.mark.unit
@pytest.mark.parametrize("type_", ["JSON", "XML"])
def test_old_and_new_service_unknown_id_is_not_found(call, type_):
    bodies = {"JSON": '{"Law":"일치하는 신구법 없습니다."}',
              "XML": '<?xml version="1.0" encoding="utf-8"?><Law>일치하는 신구법 없습니다. </Law>'}
    t = call({(SERVICE, "oldAndNew"): bodies[type_]})
    assert_error(t("oldAndNew_service", mst="9999999", type=type_), "NOT_FOUND")


@pytest.mark.unit
def test_old_and_new_service_flag_n_is_not_found(call):
    body = json.dumps({"OldAndNewService": {"신구법존재여부": "N"}})
    assert_error(call({(SERVICE, "oldAndNew"): body})("oldAndNew_service", id="001706"), "NOT_FOUND")


@pytest.mark.unit
@pytest.mark.parametrize("kw", [{}, {"mst": "abc"}, {"id": "00 1706"}, {"mst": "-1"}])
def test_old_and_new_service_requires_numeric_id_or_mst(call, kw):
    t = call({(SERVICE, "oldAndNew"): fx("oldAndNew_body_273705.json")})
    assert_error(t("oldAndNew_service", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


# ---------------------------------------------------------------- lsJoHstInf

@pytest.mark.unit
def test_jo_hst_list_normalizes_jo_info(call):
    t = call({(SEARCH, "lsJoHstInf"): fx("lsJoHstInf_list_trimmed.json")})
    out = t("lsJoHstInf_search", id="001706", from_reg_dt="20200101", to_reg_dt="20261231")
    assert out["status"] == "ok"
    rows = out["ranked_data"]["law"]
    assert len(rows) == 4
    assert rows[0]["조문정보"] == {"jo": []}                      # "" -> empty list
    assert isinstance(rows[1]["조문정보"]["jo"], list)             # dict -> list
    assert rows[1]["조문정보"]["jo"][0]["조문번호"] == "037900"
    assert len(rows[3]["조문정보"]["jo"]) == 2                    # list stays
    q = call.holder["up"].calls[0][1]
    assert q["ID"] == "001706" and q["fromRegDt"] == "20200101" and q["toRegDt"] == "20261231"


@pytest.mark.unit
def test_jo_hst_jo_filter_adds_note_and_6_digit_code(call):
    t = call({(SEARCH, "lsJoHstInf"): fx("lsJoHstInf_list_trimmed.json")})
    out = t("lsJoHstInf_search", id="001706", jo="제379조", reg_dt="20210126")
    assert call.holder["up"].calls[0][1]["JO"] == "037900"
    assert "note" in out


@pytest.mark.unit
@pytest.mark.parametrize("kw", [
    {},                                                   # no date: upstream says 0 rows
    {"id": "001706"},
    {"reg_dt": "20259999"},
    {"reg_dt": "20250401", "from_reg_dt": "20250101"},
    {"from_reg_dt": "20250201", "to_reg_dt": "20250101"},
    {"from_reg_dt": "2025-01-01"},
    {"reg_dt": "20250401", "jo": "abc"},
    {"reg_dt": "20250401", "id": "x"},
    {"reg_dt": "20250401", "type": "HTML"},
])
def test_jo_hst_bad_args(call, kw):
    t = call({(SEARCH, "lsJoHstInf"): fx("lsJoHstInf_list_trimmed.json")})
    assert_error(t("lsJoHstInf_search", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_jo_hst_from_date_alone_is_allowed(call):
    t = call({(SEARCH, "lsJoHstInf"): fx("lsJoHstInf_list_trimmed.json")})
    assert t("lsJoHstInf_search", from_reg_dt="20250101")["status"] == "ok"


ZERO_LAW = json.dumps({"LawSearch": {"target": "lsJoHstInf", "totalCnt": "0"}})


@pytest.mark.unit
def test_jo_hst_zero_rows_ok_with_empty_list(call):
    out = call({(SEARCH, "lsJoHstInf"): ZERO_LAW})("lsJoHstInf_search", reg_dt="20250402")
    assert out["status"] == "ok" and out["warning"] == "no_results"
    assert out["ranked_data"]["law"] == []


@pytest.mark.unit
def test_page_past_the_end_is_not_reported_as_no_results(call):
    def route(q):
        if q.get("page") == "1":
            return fx("lsJoHstInf_list_trimmed.json")
        return ZERO_LAW                      # upstream: totalCnt 0 past the last page
    out = call({(SEARCH, "lsJoHstInf"): route})("lsJoHstInf_search", reg_dt="20250401", page=9)
    assert out["status"] == "ok" and out["warning"] == "page_out_of_range"
    assert out["ranked_data"]["totalCnt"] == "7" and out["ranked_data"]["law"] == []
    assert "message" not in out


# ---------------------------------------------------------------- lsHstInf

@pytest.mark.unit
def test_hst_inf_ok_and_params(call):
    t = call({(SEARCH, "lsHstInf"): fx("lsHstInf_list_20260317.json")})
    out = t("lsHstInf_search", reg_dt=20260317, org="1270000", display=3)
    rows = out["ranked_data"]["law"]
    assert out["status"] == "ok" and rows[0]["법령일련번호"] == "284651" and rows[0]["현행연혁코드"] == "연혁"
    q = call.holder["up"].calls[0][1]
    assert q["regDt"] == "20260317" and q["org"] == "1270000" and q["display"] == "3"


@pytest.mark.unit
@pytest.mark.parametrize("kw", [{"reg_dt": ""}, {"reg_dt": None}, {"reg_dt": "20260231"}, {"reg_dt": "20260317", "org": "x"},
                                {"reg_dt": "20260317", "page": -1}])
def test_hst_inf_bad_args(call, kw):
    t = call({(SEARCH, "lsHstInf"): fx("lsHstInf_list_20260317.json")})
    assert_error(t("lsHstInf_search", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_hst_inf_empty_day_and_past_end(call):
    zero = json.dumps({"LawSearch": {"target": "lsHstInf", "totalCnt": "0"}})
    out = call({(SEARCH, "lsHstInf"): zero})("lsHstInf_search", reg_dt="20010101")
    assert out["status"] == "ok" and out["warning"] == "no_results" and out["ranked_data"]["law"] == []
    get_cache().invalidate()
    t = call({(SEARCH, "lsHstInf"): lambda q: fx("lsHstInf_list_20260317.json") if q.get("page") == "1" else zero})
    out = t("lsHstInf_search", reg_dt="20260317", page=50)
    assert out["warning"] == "page_out_of_range" and out["ranked_data"]["totalCnt"] == "346"


# ---------------------------------------------------------------- delHst

@pytest.mark.unit
def test_del_hst_range_and_kind(call):
    t = call({(SEARCH, "delHst"): fx("delHst_list_2025.json")})
    out = t("delHst_search", knd=1, frm_dt="20250101", to_dt="20251231", display=3)
    assert out["status"] == "ok" and out["ranked_data"]["totalCnt"] == "45"
    assert out["ranked_data"]["law"][0]["구분명"] == "법령"
    q = call.holder["up"].calls[0][1]
    assert q["knd"] == "1" and q["frmDt"] == "20250101" and q["toDt"] == "20251231"


@pytest.mark.unit
def test_del_hst_single_row_is_list(call):
    t = call({(SEARCH, "delHst"): fx("delHst_list_single.json")})
    rows = t("delHst_search", knd="3", del_dt="20231013")["ranked_data"]["law"]
    assert isinstance(rows, list) and len(rows) == 1
    assert call.holder["up"].calls[0][1]["delDt"] == "20231013"


@pytest.mark.unit
@pytest.mark.parametrize("kw", [
    {"knd": 99}, {"knd": "법령"}, {"del_dt": "20259999"}, {"frm_dt": "20250101"}, {"to_dt": "20250101"},
    {"frm_dt": "20250201", "to_dt": "20250101"}, {"del_dt": "20250101", "frm_dt": "20250101", "to_dt": "20250102"},
    {"type": "HTML"},
])
def test_del_hst_bad_args(call, kw):
    t = call({(SEARCH, "delHst"): fx("delHst_list_2025.json")})
    assert_error(t("delHst_search", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_del_hst_past_end_page(call):
    empty = json.dumps({"LawSearch": {"page": "0", "target": "delHst", "totalCnt": "0"}})
    t = call({(SEARCH, "delHst"): lambda q: fx("delHst_list_2025.json") if q.get("page") == "1" else empty})
    out = t("delHst_search", knd=1, frm_dt="20250101", to_dt="20251231", page=999)
    assert out["warning"] == "page_out_of_range" and out["ranked_data"]["totalCnt"] == "45"


# ---------------------------------------------------------------- lsAbrv

def abrv_routes(counter=None):
    def route(q):
        if counter is not None:
            counter.append(q)
        return fx("lsAbrv_list_trimmed.json")
    return {(SEARCH, "lsAbrv"): route}


@pytest.mark.unit
def test_abrv_filters_by_abbreviation_and_name_locally(call):
    calls = []
    t = call(abrv_routes(calls))
    out = t("lsAbrv_search", query="가족관계등록법")
    rows = out["ranked_data"]["law"]
    assert out["status"] == "ok" and rows and all("가족관계" in r["법령명한글"] for r in rows)
    assert any(r["법령약칭명"] == "가족관계등록법" for r in rows)
    assert "query" not in calls[0]                  # the upstream ignores query: never sent
    assert out["ranked_data"]["totalCnt"] == str(len(rows))
    assert int(out["ranked_data"]["upstream_totalCnt"]) > len(rows)
    by_name = t("lsAbrv_search", query="가족관계의 등록 등에 관한 법")  # spaces are ignored
    assert by_name["ranked_data"]["law"] and all("가족관계" in r["법령명한글"] for r in by_name["ranked_data"]["law"])


@pytest.mark.unit
def test_abrv_paging_is_local_and_cached(call):
    calls = []
    t = call(abrv_routes(calls))
    p1 = t("lsAbrv_search", display=10, page=1)
    p2 = t("lsAbrv_search", display=10, page=2)
    assert len(p1["ranked_data"]["law"]) == 10 and p2["ranked_data"]["law"][0]["rank"] == "11"
    assert p1["ranked_data"]["law"][0]["rank"] == "1"
    assert p1["ranked_data"]["law"][-1]["법령일련번호"] != p2["ranked_data"]["law"][0]["법령일련번호"]
    assert len(calls) == 1                           # one upstream fetch, second page from cache
    far = t("lsAbrv_search", display=10, page=999)
    assert far["ranked_data"]["law"] == [] and any("no_more_results" in h for h in far["hints"])


@pytest.mark.unit
def test_abrv_zero_matches_is_ok(call):
    out = call(abrv_routes())("lsAbrv_search", query="존재하지않는약칭zzz")
    assert out["status"] == "ok" and out["warning"] == "no_results" and out["ranked_data"]["law"] == []


@pytest.mark.unit
@pytest.mark.parametrize("kw", [{"std_dt": "20261301"}, {"end_dt": "x"}, {"std_dt": "20261231", "end_dt": "20260101"}, {"display": 0}])
def test_abrv_bad_args(call, kw):
    t = call(abrv_routes())
    assert_error(t("lsAbrv_search", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_abrv_dates_forwarded_and_upstream_error_propagates(call):
    t = call({(SEARCH, "lsAbrv"): ""})                # 0-byte body
    out = t("lsAbrv_search", std_dt="20260101", end_dt="20261231")
    assert out["status"] == "error"
    assert "stdDt" not in call.holder["up"].calls[0][1]      # the range is applied locally on 등록일


@pytest.mark.unit
def test_abrv_empty_or_unparsable_is_an_error_and_never_cached(call):
    good = fx("lsAbrv_list_trimmed.json")
    empty = json.dumps({"LawSearch": {"target": "lsAbrv", "totalCnt": "0"}})
    bodies = iter(["{not json", empty, good])
    t = call({(SEARCH, "lsAbrv"): lambda q: next(bodies)})
    for _ in range(2):
        assert_error(t("lsAbrv_search"), "UPSTREAM_ERROR")
    assert t("lsAbrv_search")["status"] == "ok"          # the 3rd fetch really went upstream: nothing bad was cached
    assert t("lsAbrv_search")["status"] == "ok" and len(call.holder["up"].calls) == 3   # now cached


@pytest.mark.unit
def test_abrv_count_mismatch_serves_the_rows_with_a_warning_and_does_not_cache(call):
    d = json.loads(fx("lsAbrv_list_trimmed.json"))
    d["LawSearch"]["totalCnt"] = str(len(d["LawSearch"]["law"]) + 5)
    mismatch = json.dumps(d, ensure_ascii=False)
    t = call({(SEARCH, "lsAbrv"): mismatch})
    a = t("lsAbrv_search", display=100)
    b = t("lsAbrv_search", display=100)
    assert a["status"] == "ok" and a["ranked_data"]["law"] and "upstream_total_mismatch" in a["warning"]
    assert len(call.holder["up"].calls) == 2              # served twice, cached never


@pytest.mark.unit
def test_abrv_one_cache_key_dates_applied_locally_unique_request_ids(call):
    t = call(abrv_routes())
    a = t("lsAbrv_search", std_dt="20240101", end_dt="20241231", display=100)
    b = t("lsAbrv_search", std_dt="20230101", end_dt="20231231", display=100)
    c = t("lsAbrv_search", display=100)
    assert len(call.holder["up"].calls) == 1 and "stdDt" not in call.holder["up"].calls[0][1]
    assert all("20240101" <= r["등록일"] <= "20241231" for r in a["ranked_data"]["law"]) and a["ranked_data"]["law"]
    assert all("20230101" <= r["등록일"] <= "20231231" for r in b["ranked_data"]["law"])
    assert int(c["ranked_data"]["totalCnt"]) > int(a["ranked_data"]["totalCnt"])
    assert len({a["request_id"], b["request_id"], c["request_id"]}) == 3
    only_from = t("lsAbrv_search", std_dt="20240101", display=100)
    assert all(r["등록일"] >= "20240101" for r in only_from["ranked_data"]["law"])


@pytest.mark.unit
def test_abrv_past_the_end_warns(call):
    out = call(abrv_routes())("lsAbrv_search", display=10, page=999)
    assert out["warning"] == "page_out_of_range" and out["ranked_data"]["law"] == []


@pytest.mark.unit
def test_abrv_fullwidth_date_is_normalized_not_dropped(call):
    t = call(abrv_routes())
    full = t("lsAbrv_search", std_dt="２０２４０１０１", end_dt="２０２４１２３１", display=100)
    ascii_ = t("lsAbrv_search", std_dt="20240101", end_dt="20241231", display=100)
    assert full["ranked_data"]["totalCnt"] == ascii_["ranked_data"]["totalCnt"] != ""
    assert int(full["ranked_data"]["totalCnt"]) < int(full["ranked_data"]["upstream_totalCnt"])


@pytest.mark.unit
def test_filter_abbreviations_pure():
    rows = [{"법령명한글": "가족관계의 등록 등에 관한 법률", "법령약칭명": "가족관계등록법"},
            {"법령명한글": "민법", "법령약칭명": ""}]
    assert len(filter_abbreviations(rows, None)) == 2 and len(filter_abbreviations(rows, "*")) == 2
    assert filter_abbreviations(rows, "가족관계 등록법")[0]["법령명한글"].startswith("가족")
    assert filter_abbreviations(rows, "민법")[0]["법령명한글"] == "민법"


# ---------------------------------------------------------------- licbyl

@pytest.mark.unit
def test_licbyl_rows_are_links_only(call):
    t = call({(SEARCH, "licbyl"): fx("licbyl_list_gajok.json")})
    out = t("licbyl_search", query="가족관계", search=2, knd=2, org="1270000,1320000", mul_org="and", display=2)
    assert out["status"] == "ok"
    row = out["ranked_data"]["licbyl"][0]
    assert row["별표서식파일링크"].startswith("/LSW/flDownload.do") and row["별표종류"] == "서식"
    assert "law.go.kr" in out["links_note"] and "가져오지 않았습니다" in out["links_note"]
    q = call.holder["up"].calls[0][1]
    assert q["search"] == "2" and q["knd"] == "2" and q["mulOrg"] == "AND" and q["org"] == "1270000,1320000"
    assert "OC=" not in json.dumps(out, ensure_ascii=False)


@pytest.mark.unit
def test_licbyl_single_row_and_zero_rows(call):
    rows = call({(SEARCH, "licbyl"): fx("licbyl_list_single.json")})("licbyl_search", query="a")["ranked_data"]["licbyl"]
    assert isinstance(rows, list) and len(rows) == 1
    zero = json.dumps({"licBylSearch": {"키워드": "민법", "page": "1", "totalCnt": "0", "numOfRows": "0"}})
    out = call({(SEARCH, "licbyl"): zero})("licbyl_search", query="민법")
    assert out["status"] == "ok" and out["warning"] == "no_results" and out["ranked_data"]["licbyl"] == []


@pytest.mark.unit
@pytest.mark.parametrize("kw", [{"knd": 9}, {"search": 9}, {"sort": "zz"}, {"mul_org": "XOR"}, {"org": "x"}])
def test_licbyl_bad_args(call, kw):
    t = call({(SEARCH, "licbyl"): fx("licbyl_list_gajok.json")})
    assert_error(t("licbyl_search", query="a", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


# ---------------------------------------------------------------- thdCmp

@pytest.mark.unit
def test_thd_cmp_search(call):
    t = call({(SEARCH, "thdCmp"): fx("thdCmp_list_gasa.json")})
    out = t("thdCmp_search", query="가사소송법")
    rows = out["ranked_data"]["thdCmp"]
    assert isinstance(rows, list) and rows[0]["삼단비교일련번호"] == "265309" and rows[0]["법령ID"] == "001206"
    assert "OC=" not in json.dumps(out, ensure_ascii=False)
    assert_error(t("thdCmp_search", ef_yd="2026"), "VALIDATION_ERROR")


def thd_route(name):
    return {(SERVICE, "thdCmp"): fx(name)}


@pytest.mark.unit
@pytest.mark.parametrize("knd,expected", [(1, "1"), ("2", "2"), ("인용조문", "1"), ("위임조문", "2")])
def test_thd_cmp_service_knd_forms(call, knd, expected):
    t = call(thd_route("thdCmp_body_265309_knd2_trimmed.json"))
    assert t("thdCmp_service", knd=knd, mst="265309")["status"] == "ok"
    assert call.holder["up"].calls[0][1]["knd"] == expected


@pytest.mark.unit
@pytest.mark.parametrize("kw", [
    {"knd": None, "mst": "1"}, {"knd": "", "mst": "1"}, {"knd": 3, "mst": "1"}, {"knd": 1},
    {"knd": 1, "mst": "x"}, {"knd": 1, "mst": "1", "jo": "abc"}, {"knd": 1, "mst": "1", "type": "XML", "jo": 3},
    {"knd": 1, "mst": "1", "type": "CSV"},
])
def test_thd_cmp_service_bad_args(call, kw):
    t = call(thd_route("thdCmp_body_265309_knd2_trimmed.json"))
    assert_error(t("thdCmp_service", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_thd_cmp_service_jo_selects_article_rows_only(call):
    t = call(thd_route("thdCmp_body_265309_knd2_trimmed.json"))
    full = t("thdCmp_service", knd=2, mst="265309")
    full_rows = json.loads(full["raw_content"])["LspttnThdCmpLawXService"]["위임조문삼단비교"]["법률조문"]
    sel = t("thdCmp_service", knd=2, mst="265309", jo=6)
    assert sel["status"] == "ok"
    rows = json.loads(sel["raw_content"])["LspttnThdCmpLawXService"]["위임조문삼단비교"]["법률조문"]
    assert rows and all(r["조번호"] == "0006" and r["조가지번호"] == "00" and r["조제목"] for r in rows)
    assert sel["selection"] == {"jo": "000600", "matched_rows": len(rows), "total_rows": len(full_rows)}
    assert len(rows) >= 2                              # one article can have several rows
    assert len(sel["raw_content"]) < len(full["raw_content"])
    assert sel["anchor"]["law_id"] == "001206" and sel["anchor"]["mst"] == "265309"


@pytest.mark.unit
def test_thd_cmp_service_jo_skips_chapter_headings_and_handles_branch(call):
    t = call(thd_route("thdCmp_body_265309_knd1_trimmed.json"))
    rows = json.loads(t("thdCmp_service", knd=1, mst="265309", jo="제63조의2")["raw_content"])
    rows = rows["ThdCmpLawXService"]["인용조문삼단비교"]["법률조문"]
    assert len(rows) == 1 and rows[0]["조제목"].startswith("제63조의2(")
    # article 1 shares 조번호 0001 with the "제1편 총칙" heading row: only the real article is kept
    one = json.loads(t("thdCmp_service", knd=1, mst="265309", jo=1)["raw_content"])
    one = one["ThdCmpLawXService"]["인용조문삼단비교"]["법률조문"]
    assert len(one) == 1 and one[0]["조제목"].startswith("제1조")


@pytest.mark.unit
def test_thd_cmp_service_missing_article(call):
    t = call(thd_route("thdCmp_body_265309_knd1_trimmed.json"))
    out = t("thdCmp_service", knd=1, mst="265309", jo=999)
    assert_error(out, "ARTICLE_NOT_FOUND")
    assert out["anchor"]["law_name"] == "가사소송법"


@pytest.mark.unit
@pytest.mark.parametrize("body", ["", "{}"])
def test_thd_cmp_service_unknown_id_is_not_found(call, body):
    t = call({(SERVICE, "thdCmp"): body})
    assert_error(t("thdCmp_service", knd=1, mst="9999999"), "NOT_FOUND")


@pytest.mark.unit
def test_thd_cmp_service_anchor_mismatch_warns(call):
    t = call(thd_route("thdCmp_body_265309_knd2_trimmed.json"))
    out = t("thdCmp_service", knd=2, id="005672")            # a 시행령 id: upstream answers with the 모법
    assert out["status"] == "ok" and "001206" in out["warning"]
    out = t("thdCmp_service", knd=2, mst="1")
    assert "265309" in out["warning"]
    assert "warning" not in t("thdCmp_service", knd=2, id="1206")      # same id without zero padding


@pytest.mark.unit
def test_thd_cmp_service_decree_request_warns_about_base_law(call):
    body = json.loads(fx("thdCmp_body_265309_knd2_trimmed.json"))
    info = body["LspttnThdCmpLawXService"]["기본정보"]
    info.update({"법령일련번호": "273705", "법령ID": "011878", "법령명": "난민법 시행령", "기준법령명": "난민법"})
    out = call({(SERVICE, "thdCmp"): json.dumps(body, ensure_ascii=False)})("thdCmp_service", knd=2, mst="273705")
    assert out["status"] == "ok" and "난민법 시행령" in out["warning"] and "난민법" in out["warning"]
    assert out["anchor"]["base_law_name"] == "난민법"
    cited = json.loads(fx("thdCmp_body_265309_knd1_trimmed.json"))
    cited["ThdCmpLawXService"]["기본정보"]["삼단비교기준"] = "R"
    out = call({(SERVICE, "thdCmp"): json.dumps(cited, ensure_ascii=False)})("thdCmp_service", knd=1, mst="266929")
    assert out["anchor"]["basis"] == "R" and "삼단비교기준이 R" in out["warning"]


@pytest.mark.unit
def test_thd_cmp_service_flag_n_is_not_found(call):
    body = json.dumps({"ThdCmpLawXService": {"기본정보": {"법령ID": "1", "삼단비교존재여부": "N"}}})
    assert_error(call({(SERVICE, "thdCmp"): body})("thdCmp_service", knd=1, id="1"), "NOT_FOUND")


def big_thd_body(n=400):
    rows = [{"조제목": f"제{i}조(제목)", "조가지번호": "00", "조번호": f"{i:04d}", "조내용": "가나다라 " * 120}
            for i in range(1, n + 1)]
    return json.dumps({"ThdCmpLawXService": {"기본정보": {"법령ID": "001706", "법령명": "민법", "삼단비교존재여부": "Y"},
                                             "인용조문삼단비교": {"법률조문": rows}}}, ensure_ascii=False)


@pytest.mark.unit
def test_thd_cmp_service_default_keeps_everything_slim_cuts_and_points_to_jo(call, monkeypatch):
    body = big_thd_body()
    t = call({(SERVICE, "thdCmp"): body})
    out = t("thdCmp_service", knd=1, id="001706")
    assert len(out["raw_content"]) > 200_000 and "truncated" not in out
    get_cache().invalidate()
    monkeypatch.setenv("SLIM_RESPONSE", "true")
    slim = t("thdCmp_service", knd=1, id="001706")
    assert slim["truncated"] is True and "jo로 조문 지정" in json.dumps(slim, ensure_ascii=False)
    assert _json_size(slim) <= SLIM_MAX_BYTES
    one = t("thdCmp_service", knd=1, id="001706", jo=250)
    assert "truncated" not in one and one["selection"]["matched_rows"] == 1


@pytest.mark.unit
def test_select_thdcmp_article_pure():
    root = {"기본정보": {}, "인용조문삼단비교": {"시행령조문": [
        {"조번호": "0003", "조가지번호": "02", "조제목": "제3조의2(x)", "조내용": "a"},
        {"조번호": "0003", "조가지번호": "00", "조제목": "제3조(x)", "조내용": "b"},
        {"조번호": "0003", "조가지번호": "00", "조제목": "", "조내용": "제3장 heading"}]}}
    new, matched, total = select_thdcmp_article(root, "000300")
    assert (matched, total) == (1, 3) and new["인용조문삼단비교"]["시행령조문"][0]["조내용"] == "b"
    assert root["인용조문삼단비교"]["시행령조문"][0]["조내용"] == "a"        # input untouched
    single = {"위임조문삼단비교": {"법률조문": {"조번호": "0005", "조가지번호": "00", "조제목": "제5조", "조내용": "c"}}}
    assert select_thdcmp_article(single, "000500")[1:] == (1, 1)


# ---------------------------------------------------------------- lstrm

@pytest.mark.unit
def test_lstrm_search(call):
    t = call({(SEARCH, "lstrm"): fx("lstrm_list_seoneui.json")})
    out = t("lstrm_search", query="선의", sort="rdes", reg_dt="20200101~20261231", dic_knd_cd=10101 and "010101", gana="na")
    rows = out["ranked_data"]["lstrm"]
    assert out["status"] == "ok" and len(rows) == 3 and rows[0]["법령용어ID"] == "5543412"
    q = call.holder["up"].calls[0][1]
    assert q["sort"] == "rdes" and q["regDt"] == "20200101~20261231" and q["dicKndCd"] == "010101" and q["gana"] == "na"
    assert "OC=" not in json.dumps(out, ensure_ascii=False)


@pytest.mark.unit
def test_lstrm_search_does_not_alias_resolve_the_term(call):
    t = call({(SEARCH, "lstrm"): fx("lstrm_list_seoneui.json")})
    t("lstrm_search", query="자통법")
    assert call.holder["up"].calls[0][1]["query"] == "자통법"


@pytest.mark.unit
def test_lstrm_search_zero_rows(call):
    zero = json.dumps({"LsTrmSearch": {"키워드": "zzz", "page": "1", "totalCnt": "0", "numOfRows": "0"}})
    out = call({(SEARCH, "lstrm"): zero})("lstrm_search", query="zzz")
    assert out["status"] == "ok" and out["warning"] == "no_results" and out["ranked_data"]["lstrm"] == []


@pytest.mark.unit
@pytest.mark.parametrize("kw", [{"sort": "zz"}, {"dic_knd_cd": "999999"}, {"reg_dt": "20200101"}, {"reg_dt": "20201301~20201302"}, {"page": 0}])
def test_lstrm_search_bad_args(call, kw):
    t = call({(SEARCH, "lstrm"): fx("lstrm_list_seoneui.json")})
    assert_error(t("lstrm_search", query="a", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_lstrm_service_entries_keep_their_own_fields(call):
    t = call({(SERVICE, "lstrm"): fx("lstrm_body_sangsok.xml")})
    out = t("lstrm_service", query="상속")
    assert out["status"] == "ok" and out["count"] == 4
    e = out["entries"]
    assert [x["dict_name"] for x in e] == ["법령용어사전", "법령정의사전", "법령한영사전", "생활용어사전"]
    assert e[0]["name_hanja"] == "相續" and e[0]["source"] is None and e[0]["example"] is None
    assert e[1]["source"].startswith("상속세 및 증여세법") and e[1]["example"] is None   # 출처 only on entry 2
    assert e[2]["example"].startswith("토지를 상속받아") and e[2]["source"] is None     # 용례 only on entry 3
    assert e[3]["name_hanja"] is None and e[3]["term_id"] == "852194"
    assert call.holder["up"].calls[0][1]["type"] == "XML" and call.holder["up"].calls[0][1]["query"] == "상속"


@pytest.mark.unit
def test_lstrm_json_form_loses_the_association_so_xml_is_used():
    root = json.loads(fx("lstrm_body_sangsok_json.json"))["LsTrmService"]
    assert isinstance(root["법령용어정의"], list) and isinstance(root["출처"], str) and isinstance(root["용례"], str)


@pytest.mark.unit
def test_lstrm_service_entry_without_definition(call):
    out = call({(SERVICE, "lstrm"): fx("lstrm_body_seoneui.xml")})("lstrm_service", query="선의")
    assert out["status"] == "ok" and out["count"] == 1
    assert out["entries"][0]["definition"] is None and out["entries"][0]["dict_name"] == "알법정비사전"


@pytest.mark.unit
@pytest.mark.parametrize("body", [
    '<?xml version="1.0" encoding="utf-8"?><Law>일치하는 법령용어가 없습니다.  법령용어명을 확인하여 주십시오.</Law>',
    '{"Law": "일치하는 법령용어가 없습니다.  법령용어명을 확인하여 주십시오."}',
    "<LsTrmService></LsTrmService>",
])
def test_lstrm_service_unknown_term_is_not_found(call, body):
    assert_error(call({(SERVICE, "lstrm"): body})("lstrm_service", query="zzz"), "NOT_FOUND")


@pytest.mark.unit
def test_lstrm_service_garbage_is_upstream_error_not_not_found(call):
    assert_error(call({(SERVICE, "lstrm"): "<LsTrmService><broken"})("lstrm_service", query="x"), "UPSTREAM_ERROR")


@pytest.mark.unit
@pytest.mark.parametrize("q", ["", "  ", "*", None])
def test_lstrm_service_requires_query(call, q):
    t = call({(SERVICE, "lstrm"): fx("lstrm_body_sangsok.xml")})
    assert_error(t("lstrm_service", query=q), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_parse_lstrm_xml_pure():
    entries = parse_lstrm_xml(fx("lstrm_body_sangsok.xml"))
    assert len(entries) == 4 and entries[1]["dict_code"] == "011402"


# ---------------------------------------------------------------- review fixes

def thd_body(rows, key="법률조문"):
    return json.dumps({"ThdCmpLawXService": {"기본정보": {"법령ID": "1", "법령명": "x", "삼단비교존재여부": "Y"},
                                             "인용조문삼단비교": {key: rows}}}, ensure_ascii=False)


@pytest.mark.unit
def test_thd_cmp_jo_matches_titleless_real_article_but_not_headings(call):
    rows = [
        {"조번호": "0005", "조가지번호": "00", "조제목": "", "조내용": "제5조 삭제 <2010.3.31>"},
        {"조번호": "0005", "조가지번호": "00", "조제목": "", "조내용": "제5편 벌칙"},
        {"조번호": "0005", "조가지번호": "00", "조제목": "", "조내용": "제1항 협의상 파양 <개정 2012.2.10>"},
        {"조번호": "0006", "조가지번호": "00", "조제목": "제6조(x)", "조내용": "b"},
    ]
    out = call({(SERVICE, "thdCmp"): thd_body(rows)})("thdCmp_service", knd=1, id="1", jo=5)
    kept = json.loads(out["raw_content"])["ThdCmpLawXService"]["인용조문삼단비교"]["법률조문"]
    assert [r["조내용"] for r in kept] == ["제5조 삭제 <2010.3.31>"]


@pytest.mark.unit
def test_thd_cmp_jo_filters_every_list_even_with_rows_lacking_joBeonho():
    root = {"인용조문삼단비교": {
        "법률조문": [{"조번호": "0003", "조가지번호": "00", "조제목": "제3조", "조내용": "a"},
                     {"조제목": "제9조", "조내용": "no number"}],
        "시행령조문": [{"조번호": "0004", "조가지번호": "00", "조제목": "제4조", "조내용": "b"}]}}
    new, matched, total = select_thdcmp_article(root, "000300")
    sec = new["인용조문삼단비교"]
    assert [r["조내용"] for r in sec["법률조문"]] == ["a"] and sec["시행령조문"] == []
    assert (matched, total) == (1, 3)


@pytest.mark.unit
@pytest.mark.parametrize("jo", ["", "   "])
def test_thd_cmp_blank_jo_is_validation_error_not_full_law(call, jo):
    t = call(thd_route("thdCmp_body_265309_knd2_trimmed.json"))
    assert_error(t("thdCmp_service", knd=2, mst="265309", jo=jo), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


LSTRM_ONE = fx("lstrm_body_seoneui.xml")


@pytest.mark.unit
def test_lstrm_service_trm_seqs(call):
    t = call({(SERVICE, "lstrm"): LSTRM_ONE})
    out = t("lstrm_service", trm_seqs=31106)
    assert out["status"] == "ok" and out["trm_seqs"] == "31106"
    q = call.holder["up"].calls[0][1]
    assert q["trmSeqs"] == "31106" and "query" not in q and q["type"] == "XML"
    assert "warning" not in out


@pytest.mark.unit
def test_lstrm_service_trm_seqs_comma_list_and_missing_ids(call):
    t = call({(SERVICE, "lstrm"): LSTRM_ONE})
    out = t("lstrm_service", trm_seqs="31106, 999")
    assert call.holder["up"].calls[0][1]["trmSeqs"] == "31106,999"
    assert "999" in out["warning"] and "31106" not in out["warning"]


@pytest.mark.unit
@pytest.mark.parametrize("kw", [{"trm_seqs": "abc"}, {"trm_seqs": "1,,2"}, {"trm_seqs": "1", "query": "x"}, {}])
def test_lstrm_service_trm_seqs_validation(call, kw):
    t = call({(SERVICE, "lstrm"): LSTRM_ONE})
    assert_error(t("lstrm_service", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_lstrm_service_not_found_hint_points_to_trm_seqs_and_search_description_does_too(call):
    nf = '<?xml version="1.0" encoding="utf-8"?><Law>일치하는 법령용어가 없습니다.  법령용어명을 확인하여 주십시오.</Law>'
    out = call({(SERVICE, "lstrm"): nf})("lstrm_service", query="양육비 채무자")
    assert_error(out, "NOT_FOUND")
    assert any("trm_seqs" in h for h in out["hints"])
    desc = asyncio.run(server_mod.create_server().list_tools())
    d = {t.name: t.description for t in desc}["lstrm_search"]
    assert "trm_seqs" in d and "법령용어ID" in d


@pytest.mark.unit
def test_lstrm_service_html_page_mentioning_match_is_not_not_found(call):
    page = "<!DOCTYPE html><html><body><p>일치하는 자료<br></body>"
    out = call({(SERVICE, "lstrm"): page})("lstrm_service", query="x")
    assert out["status"] == "error" and out["error_code"] != "NOT_FOUND"


@pytest.mark.unit
def test_parse_lstrm_xml_nested_tags_repeated_source_and_entities():
    raw = ('<L><법령용어일련번호>1</법령용어일련번호><법령용어명_한글>a</법령용어명_한글>'
           '<출처>법A</출처><출처>법B</출처>'
           '<법령용어정의>앞<b>굵게</b>뒤 갑&amp;middot;을 병</법령용어정의></L>')
    e = parse_lstrm_xml(raw)[0]
    assert e["definition"] == "앞굵게뒤 갑·을 병"
    assert e["definition"].startswith("앞굵게뒤")                       # nested text kept
    assert e["source"] == "법A\n법B"                                     # repeated tag kept
    cdata = '<L><법령용어일련번호>1</법령용어일련번호><법령용어정의><![CDATA[자&middot;의 &lt;x&gt;]]></법령용어정의></L>'
    assert parse_lstrm_xml(cdata)[0]["definition"] == "자·의 <x>"


@pytest.mark.unit
def test_fullwidth_digits_are_normalized_or_rejected_never_silently_dropped(call):
    assert ascii_digits("２０２５０４０１") == "20250401"
    assert validate_yyyymmdd("２０２５０４０１", "d") == "20250401"
    assert validate_digits("２８４４１５", "mst") == "284415"
    with pytest.raises(ToolValidationError):
        validate_yyyymmdd("２０２５１３０１", "d")                    # still a real-date check
    t = call({(SEARCH, "lsHstInf"): fx("lsHstInf_list_20260317.json"),
              (SERVICE, "oldAndNew"): fx("oldAndNew_body_273705.json"),
              (SEARCH, "delHst"): fx("delHst_list_2025.json"),
              (SEARCH, "lstrm"): fx("lstrm_list_seoneui.json")})
    t("lsHstInf_search", reg_dt="２０２６０３１７", org="１２７００００")
    q = call.holder["up"].calls[0][1]
    assert q["regDt"] == "20260317" and q["org"] == "1270000"
    out = t("oldAndNew_service", mst="２７３７０５")
    assert call.holder["up"].calls[1][1]["MST"] == "273705" and "warning" not in out
    t("delHst_search", frm_dt="２０２５０１０１", to_dt="２０２５１２３１")
    assert call.holder["up"].calls[2][1]["frmDt"] == "20250101"
    t("lstrm_search", reg_dt="２０２００１０１~２０２６１２３１")
    assert call.holder["up"].calls[3][1]["regDt"] == "20200101~20261231"


@pytest.mark.unit
def test_old_and_new_service_id_mst_mismatch_warns(call):
    t = call({(SERVICE, "oldAndNew"): fx("oldAndNew_body_273705.json")})
    out = t("oldAndNew_service", id="001206", mst="273705")
    assert out["status"] == "ok" and "001206" in out["warning"] and "011878" in out["warning"]
    assert "warning" not in t("oldAndNew_service", id="11878", mst="273705")


@pytest.mark.unit
def test_old_and_new_service_carries_the_upstream_edit_caution(call):
    t = call({(SERVICE, "oldAndNew"): fx("oldAndNew_body_273705.json")})
    assert "확인" in t("oldAndNew_service", mst="273705")["caution"]
    desc = {x.name: x.description for x in asyncio.run(server_mod.create_server().list_tools())}["oldAndNew_service"]
    assert "5분" in desc and "law_as_of" in desc


@pytest.mark.unit
@pytest.mark.parametrize("tool,kw", [
    ("oldAndNew_search", {"knd": "abc"}), ("oldAndNew_search", {"gana": "zz!"}), ("oldAndNew_search", {"knd": "1"}),
    ("thdCmp_search", {"gana": "가"}), ("lstrm_search", {"gana": "zz"}), ("licbyl_search", {"gana": "zz"}),
])
def test_gana_and_knd_are_validated(call, tool, kw):
    t = call({(SEARCH, "oldAndNew"): fx("oldAndNew_list_minbeop.json"), (SEARCH, "lstrm"): fx("lstrm_list_seoneui.json"),
              (SEARCH, "licbyl"): fx("licbyl_list_gajok.json"), (SEARCH, "thdCmp"): fx("thdCmp_list_gasa.json")})
    assert_error(t(tool, query="a", **kw), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_gana_and_knd_valid_values_are_forwarded(call):
    t = call({(SEARCH, "oldAndNew"): fx("oldAndNew_list_minbeop.json"), (SEARCH, "lstrm"): fx("lstrm_list_seoneui.json")})
    t("oldAndNew_search", knd="a0002", gana="GA")
    t("lstrm_search", gana="etc")
    assert call.holder["up"].calls[0][1]["knd"] == "A0002" and call.holder["up"].calls[0][1]["gana"] == "ga"
    assert call.holder["up"].calls[1][1]["gana"] == "etc"


@pytest.mark.unit
@pytest.mark.parametrize("search,expect,absent", [(None, "search=2", "search=1"), (2, "search=1", "search=2"), (3, "search=1", "search=3")])
def test_licbyl_zero_row_hint_names_the_other_scopes(call, search, expect, absent):
    zero = json.dumps({"licBylSearch": {"키워드": "q", "page": "1", "totalCnt": "0", "numOfRows": "0"}})
    kw = {} if search is None else {"search": search}
    out = call({(SEARCH, "licbyl"): zero})("licbyl_search", query="q", **kw)
    text = " ".join(out["hints"])
    assert expect in text and "본문 검색" not in text
    assert f"{absent}(" not in text.split("현재")[-1].split("기준입니다.")[-1]      # not offered as the alternative


def big_oldnew(n=202):
    col = lambda tag: {"조문": [{"no": str(i + 1), "content": f"{tag} 제{i + 1}조 " + "가나다라 " * 20} for i in range(n)]}
    return json.dumps({"OldAndNewService": {
        "신조문목록": col("신"), "구조문목록": col("구"),
        "구조문_기본정보": {"법령ID": "001706", "법령일련번호": "1", "법령명": "민법"},
        "신조문_기본정보": {"법령ID": "001706", "법령일련번호": "2", "법령명": "민법"}}}, ensure_ascii=False)


@pytest.mark.unit
def test_old_and_new_service_slim_cut_keeps_columns_the_same_length(call, monkeypatch):
    t = call({(SERVICE, "oldAndNew"): big_oldnew()})
    full = t("oldAndNew_service", mst="2")
    assert "truncated" not in full and len(json.loads(full["raw_content"])["OldAndNewService"]["구조문목록"]["조문"]) == 202
    monkeypatch.setenv("SLIM_RESPONSE", "true")
    slim = t("oldAndNew_service", mst="2")
    root = json.loads(slim["raw_content"])["OldAndNewService"]
    old, new = root["구조문목록"]["조문"], root["신조문목록"]["조문"]
    assert slim["truncated"] is True and 0 < len(old) < 202 and len(old) == len(new)
    assert old[-1]["no"] == new[-1]["no"] and str(len(old)) in " ".join(slim["truncated_notes"])
    assert _json_size(slim) <= SLIM_MAX_BYTES


@pytest.mark.unit
def test_del_hst_empty_page_reports_the_requested_page(call):
    empty = json.dumps({"LawSearch": {"page": "0", "target": "delHst", "totalCnt": "0"}})
    out = call({(SEARCH, "delHst"): empty})("delHst_search", knd=1, del_dt="20100101", page=1)
    assert out["ranked_data"]["page"] == "1" and out["warning"] == "no_results"


@pytest.mark.unit
@pytest.mark.parametrize("tool,target,root,key,kw", [
    ("oldAndNew_search", "oldAndNew", "OldAndNewLawSearch", "oldAndNew", {}),
    ("thdCmp_search", "thdCmp", "thdCmpLawSearch", "thdCmp", {}),
    ("licbyl_search", "licbyl", "licBylSearch", "licbyl", {}),
    ("lstrm_search", "lstrm", "LsTrmSearch", "lstrm", {}),
])
def test_other_lists_keep_their_total_past_the_last_page(call, tool, target, root, key, kw):
    """Measured live: these four report the real totalCnt (not 0) past the last page, so no re-ask is needed."""
    body = json.dumps({root: {"page": "99", "totalCnt": "9", "numOfRows": "0"}})
    out = call({(SEARCH, target): body})(tool, query="a", page=99, **kw)
    assert out["ranked_data"]["totalCnt"] == "9" and out["ranked_data"][key] == []
    assert out.get("warning") != "no_results" and any("no_more_results" in h for h in out["hints"])
    assert len(call.holder["up"].calls) == 1


# ---------------------------------------------------------------- second review

@pytest.mark.unit
def test_gana_uses_ah_for_ieung_and_rejects_a(call):
    t = call({(SEARCH, "lstrm"): fx("lstrm_list_seoneui.json")})
    assert_error(t("lstrm_search", gana="a"), "VALIDATION_ERROR")
    for g in ("ga", "na", "da", "ra", "ma", "ba", "sa", "ah", "ja", "cha", "ka", "ta", "pa", "ha", "etc"):
        assert t("lstrm_search", gana=g)["status"] == "ok"
    assert [c[1]["gana"] for c in call.holder["up"].calls][-3:] == ["pa", "ha", "etc"]


@pytest.mark.unit
def test_knd_message_and_codes_use_the_measured_names(call):
    t = call({(SEARCH, "oldAndNew"): fx("oldAndNew_list_minbeop.json")})
    err = t("oldAndNew_search", knd="X")
    assert "A0007" in err["message"] and "A0003" not in err["message"]
    assert t("oldAndNew_search", knd="A0007")["status"] == "ok"
    docs = {x.name: x.description for x in asyncio.run(server_mod.create_server().list_tools())}
    for name in ("oldAndNew_search", "thdCmp_search"):
        assert "A0007" in docs[name] and "A0003" not in docs[name]


@pytest.mark.unit
def test_ascii_digits_folds_only_fullwidth_zero_to_nine():
    assert ascii_digits("０１２３４５６７８９") == "0123456789"
    for other in ("①", "²", "٣", "１２③", "ⅷ"):
        assert not ascii_digits(other).isascii()
        with pytest.raises(ToolValidationError):
            validate_digits(other, "x")
    with pytest.raises(ToolValidationError):
        validate_yyyymmdd("２０２６０３１①", "d")


@pytest.mark.unit
def test_enum_args_are_not_folded(call):
    t = call({(SEARCH, "licbyl"): fx("licbyl_list_gajok.json")})
    assert_error(t("licbyl_search", query="a", knd="２"), "VALIDATION_ERROR")
    assert_error(t("licbyl_search", query="a", search="２"), "VALIDATION_ERROR")
    assert call.holder["up"].calls == []


@pytest.mark.unit
def test_lstrm_entities_without_semicolon_are_left_alone():
    raw = ('<L><법령용어일련번호>1</법령용어일련번호><법령용어정의><![CDATA[AT&reg 와 &copy x &middot; 와 &#183; &amp;]]></법령용어정의></L>')
    assert parse_lstrm_xml(raw)[0]["definition"] == "AT&reg 와 &copy x · 와 · &"


def so_row(num, text, child=None):
    row = {"조제목": "", "조가지번호": "00", "조내용": text, "조번호": num}
    if child:
        row["시행령조문"] = {"조제목": "", "조가지번호": "00", "법령명": "시행령", "조내용": "", "조번호": child}
    return row


@pytest.mark.unit
def test_thd_cmp_knd2_row_with_heading_text_and_children_is_kept_with_warning(call):
    rows = [so_row("0094", "제4절 양도소득금액의 계산 <개정 2009.12.31>", "0157"),
            so_row("0094", "제4절 양도소득금액의 계산 <개정 2009.12.31>", "0158"),
            so_row("0094", "제4절 양도소득금액의 계산 <개정 2009.12.31>"),          # plain heading row, no children
            so_row("0095", "제4절 양도소득금액의 계산 <개정 2009.12.31>", "0160")]
    body = json.dumps({"LspttnThdCmpLawXService": {"기본정보": {"법령ID": "001565", "법령명": "소득세법", "삼단비교존재여부": "Y"},
                                                   "위임조문삼단비교": {"법률조문": rows}}}, ensure_ascii=False)
    out = call({(SERVICE, "thdCmp"): body})("thdCmp_service", id="001565", knd=2, jo=94)
    assert out["status"] == "ok"
    kept = json.loads(out["raw_content"])["LspttnThdCmpLawXService"]["위임조문삼단비교"]["법률조문"]
    assert [r["시행령조문"]["조번호"] for r in kept] == ["0157", "0158"]
    assert out["selection"]["own_text_is_heading"] is True and out["selection"]["matched_rows"] == 2
    assert "제목" in out["warning"] and "knd=1" in out["warning"] and "조문으로" not in out["warning"].replace("조문으로 인용하지", "")


@pytest.mark.unit
def test_thd_cmp_plain_headings_are_still_excluded_and_real_articles_have_no_heading_warning(call):
    t = call({(SERVICE, "thdCmp"): thd_body([so_row("0005", "제5편 벌칙"), so_row("0006", "제6조 삭제 <2010.3.31>")])})
    assert_error(t("thdCmp_service", knd=1, id="1", jo=5), "ARTICLE_NOT_FOUND")
    ok = t("thdCmp_service", knd=1, id="1", jo=6)
    assert ok["status"] == "ok" and "own_text_is_heading" not in ok["selection"] and "warning" not in ok
