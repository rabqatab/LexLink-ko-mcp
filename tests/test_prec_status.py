"""prec_status: has a later 전원합의체 decision overruled this precedent? (offline, mocked upstream)

The decision fixture is the real 대법원 2014.7.16. 선고 2013므2250 전원합의체 판결 (trimmed): its 참조판례
lists "대법원 1995. 5. 23. 선고 94므1713, 1720 판결(공1995하, 2265)(변경)".
"""

import json
import pathlib

import pytest

import lexlink.server as server_mod
from lexlink import precedent_status as ps
from lexlink.cache import get_cache

pytestmark = pytest.mark.unit

FIX = pathlib.Path(__file__).parent / "fixtures"
DECISION = json.loads((FIX / "prec_service_2013므2250_trimmed.json").read_text(encoding="utf-8"))["PrecService"]


def row(no, date, pid, kind="판결", court="대법원", name="이혼등"):
    return {"사건번호": no, "선고일자": date, "판례일련번호": pid, "판결유형": kind, "법원명": court, "사건명": name}


R_94 = row("94므1713", "1995.05.23", "111970", name="이혼및재산분할·이혼및위자료등(반소)")
R_2013 = row("2013므2250", "2014.07.16", "187486", kind="전원합의체 판결")
R_98 = row("98므213", "1998.06.12", "600745", name="이혼및위자료")
R_2002 = row("2002스36", "2002.08.28", "81848", kind="결정", name="재산분할")

# search results keyed by (query-or-nb, search mode)
LISTS = {
    ("nb", "94므1713"): [R_94],
    ("q", "94므1713"): [R_2013, R_2002, R_98, R_94],
    ("nb", "98므213"): [R_98],
    ("q", "98므213"): [R_2013, R_98],
    ("nb", "92다17754"): [row("92다17754", "1992.09.14", "1", name="퇴직금")],
    ("q", "92다17754"): [R_2013],
    ("nb", "2010므4071"): [row("2010므4071", "2013.06.20", "9", kind="전원합의체 판결")],
    ("q", "2010므4071"): [R_2013],
    ("nb", "99다1"): [],
    ("q", "99다1"): [],
}


class FakeClient:
    calls: list = []
    body_missing: set = set()

    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        FakeClient.calls.append((endpoint, dict(params)))
        if endpoint == "/DRF/lawSearch.do":
            kind, term = ("nb", params["nb"]) if params.get("nb") else ("q", (params.get("query") or "").strip('"'))
            rows = LISTS.get((kind, term), [])
            body = {"PrecSearch": {"totalCnt": str(len(rows)), "page": "1", "prec": rows}}
            return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                    "raw_content": json.dumps(body, ensure_ascii=False)}
        pid = str(params.get("ID"))
        if pid in FakeClient.body_missing:
            return {"status": "error", "error_code": "NOT_FOUND", "message": "일치하는 판례가 없습니다", "request_id": "fake"}
        if pid == "187486":
            return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                    "raw_content": json.dumps({"PrecService": DECISION}, ensure_ascii=False)}
        return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                "raw_content": json.dumps({"PrecService": {"사건번호": "98므213", "선고일자": "19980612",
                                                          "판결유형": "판결", "법원명": "대법원", "사건명": "이혼및위자료"}},
                                          ensure_ascii=False)}


@pytest.fixture
def status(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", FakeClient)
    monkeypatch.setenv("OC", "test")
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    FakeClient.calls = []
    FakeClient.body_missing = set()
    get_cache().invalidate()
    server = server_mod.create_server()
    return lambda **kw: server._tool_manager.get_tool("prec_status").fn(**kw)


# ---- parsing -------------------------------------------------------------------------------

def test_case_number_parsing_and_joined_numbers():
    assert ps.parse_case_numbers("94므1713, 1720 판결") == [(1994, "므", 1713), (1994, "므", 1720)]
    assert ps.parse_case_numbers("2010므4071, 4088 전원합의체 판결") == [(2010, "므", 4071), (2010, "므", 4088)]
    # article numbers, dates and 공보 pages are not case numbers
    assert ps.parse_case_numbers("민법 제839조의2 제2항, 1995. 5. 23. (공1995하, 2265)") == []
    assert ps.parse_target("대법원 1995. 5. 23. 선고 94므1713 판결")[0] == (1994, "므", 1713)
    assert ps.parse_case_numbers("대법원 1957. 12. 13. 선고 4289민상182 판결") == [(4289, "민상", 182)]
    with pytest.raises(ValueError):
        ps.parse_target("no number here")


def test_marker_belongs_to_its_own_entry_only():
    ref = ps.clean(DECISION["참조판례"])
    marked = ps.find_evidence({"참조판례": DECISION["참조판례"]}, (1994, "므", 1713))["explicit"]
    assert [e["evidence"] for e in marked] == ["explicit_marker"] and marked[0]["marker"] == "(변경)"
    assert marked[0]["quote"] == "대법원 1995. 5. 23. 선고 94므1713, 1720 판결(공1995하, 2265)(변경)"
    assert marked[0]["quote"] in ref
    # the joined co-number is the same case
    assert ps.find_evidence({"참조판례": DECISION["참조판례"]}, (1994, "므", 1720))["explicit"]
    # an entry cited without a marker next to a marked one gets no marker
    plain = ps.find_evidence({"참조판례": DECISION["참조판례"]}, (1992, "다", 17754))
    assert plain["explicit"] == [] and plain["cited"]
    assert ps.find_evidence({"참조판례": DECISION["참조판례"]}, (1998, "므", 213))["explicit"]


def test_negated_change_wording_is_not_evidence():
    f = {"판례내용": "대법원 1995. 5. 23. 선고 94므1713 판결의 견해는 그대로 유지하고 변경할 필요가 없다."}
    assert ps.find_evidence(f, (1994, "므", 1713))["explicit"] == []
    g = {"판례내용": "대법원 1995. 5. 23. 선고 94므1713 판결은 이 판결과 저촉되는 범위에서 변경한다."}
    assert ps.find_evidence(g, (1994, "므", 1713))["explicit"][0]["evidence"] == "explicit_sentence"


# ---- tool ----------------------------------------------------------------------------------

def test_overruled_found_with_source_and_exact_quote(status):
    out = status(case_number="94므1713")
    assert out["status"] == "ok" and out["overruling_status"] == "overruled_found"
    ev = out["evidence"][0]
    assert ev["source"]["case_number"] == "2013므2250" and ev["source"]["id"] == "187486"
    assert ev["source"]["decision_date"] == "20140716" and ev["source"]["decision_type"] == "전원합의체 판결"
    assert ev["evidence"] == "explicit_marker" and ev["confidence"] == "high"
    assert ev["quote"] == "대법원 1995. 5. 23. 선고 94므1713, 1720 판결(공1995하, 2265)(변경)"
    assert out["target"]["found_in_index"] is True and out["target"]["decision_date"] == "19950523"
    scope = out["searched_scope"]
    assert scope["later_en_banc_candidates"] == 1 and scope["scanned"][0]["case_number"] == "2013므2250"
    assert scope["later_non_en_banc_citing_count"] == 2          # 98므213, 2002스36 are not read
    assert out["upstream_calls"] == 3                               # nb + citing list + one body
    assert any("(변경)" in c for c in out["caveats"])


def test_direction_matters_older_citing_decisions_are_not_candidates(status):
    out = status(case_number="98므213")
    assert out["overruling_status"] == "overruled_found"
    assert out["searched_scope"]["later_en_banc_candidates"] == 1
    # 94므1713 (earlier than 98므213) is not looked at as an overruler even if it cited the case
    assert all(e["source"]["case_number"] != "94므1713" for e in out["evidence"])


def test_cited_without_marker_is_not_overruled(status):
    out = status(case_number="92다17754")
    assert out["overruling_status"] == ps.NONE_FOUND
    assert out["evidence"] == [] and out["cited_without_change_marker"][0]["source"]["case_number"] == "2013므2250"
    assert "변경되지 않았다는 뜻이 아닙니다" in out["statement"]
    assert out["overruling_status"] != "not_overruled"


def test_generic_change_sentence_is_only_a_lead(status):
    # supportive citation "(... 등 참조)" next to a 변경 of other cases is not even a lead
    out = status(case_number="2010므4071")
    assert out["overruling_status"] == ps.NONE_FOUND and out["leads"] == []
    # the same decision without its 참조판례 marker: it cites 94므1713 as the departed-from position and
    # says "견해에 배치되는 범위 내에서 변경한다" without naming the case -> a lead, not a finding
    blank = dict(DECISION, 참조판례="")
    res = ps.check_status(
        key=(1994, "므", 1713), co_keys=[], case_text="94므1713", target_row=R_94,
        search=lambda params: {"total": 2, "rows": [R_2013, R_94]}, service=lambda pid: blank)
    assert res["overruling_status"] == ps.POSSIBLE and res["evidence"] == []
    lead = res["leads"][0]
    assert lead["source"]["case_number"] == "2013므2250"
    assert "94므1713, 1720 판결" in lead["cited_as"]["quote"]
    assert "배치되는 범위 내에서" in lead["generic_change"]["quote"]


def test_unknown_target_and_no_hits_state_scope(status):
    out = status(case_number="99다1")
    assert out["overruling_status"] == ps.NONE_FOUND and out["target"]["found_in_index"] is False
    assert out["searched_scope"]["scanned"] == [] and out["searched_scope"]["search_rows_total"] == 0
    assert any("선고일을 알 수 없습니다" in c for c in out["caveats"])


def test_by_id_and_validation(status):
    out = status(id="187486")           # the 전원합의체 decision itself: nothing later cites it with a marker
    assert out["status"] == "ok" and out["target"]["case_number"] == "2013므2250"
    assert out["overruling_status"] == ps.NONE_FOUND
    err = status()
    assert err["status"] == "error" and err["error_code"] == "VALIDATION_ERROR"
    assert status(case_number="사건번호 없음")["error_code"] == "VALIDATION_ERROR"


def test_unreadable_body_is_reported_not_hidden(status):
    FakeClient.body_missing = {"187486"}
    out = status(case_number="94므1713")
    assert out["overruling_status"] == ps.NONE_FOUND
    assert out["searched_scope"]["unscannable"][0]["case_number"] == "2013므2250"


def test_upstream_failure_is_an_error_never_no_overruling(status, monkeypatch):
    def get(self, endpoint, params, response_type="JSON"):
        return {"status": "error", "error_code": "TIMEOUT", "message": "x", "request_id": "r"}

    monkeypatch.setattr(FakeClient, "get", get)
    out = status(case_number="94므1713")
    assert out["status"] == "error" and out["error_code"] == "TIMEOUT"
    assert "overruling_status" not in out


def test_scan_budget_is_bounded(status, monkeypatch):
    many = [row(f"20{10 + i}므{100 + i}", f"20{10 + i}.01.01", str(500 + i), kind="전원합의체 판결") for i in range(8)]
    LISTS[("q", "94므1713")] = many + [R_94]
    try:
        out = status(case_number="94므1713", max_scan=2)
    finally:
        LISTS[("q", "94므1713")] = [R_2013, R_2002, R_98, R_94]
    scope = out["searched_scope"]
    assert len(scope["scanned"]) + len(scope["unscannable"]) == 2 and len(scope["not_scanned_en_banc"]) == 6
    assert out["upstream_calls"] <= 1 + 1 + 2
    assert any("본문을 확인했습니다" in c for c in out["caveats"])


def test_policy_entry_and_registration():
    from lexlink.tool_policy import TOOL_POLICIES
    tools = {t.name for t in server_mod.create_server()._tool_manager.list_tools()}
    assert "prec_status" in tools and TOOL_POLICIES["prec_status"]["category"] == "precedent"
    assert TOOL_POLICIES["prec_status"]["evidence"] == "heuristic"
