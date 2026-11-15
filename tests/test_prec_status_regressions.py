"""prec_status regression: three real overrulings must stay detected (offline, mocked upstream; issue #182).

The decision fixtures in tests/fixtures/prec_service_*_trimmed.json are trimmed public 대법원 decisions
(사건번호, 선고일자, 판결유형, 법원명, 사건명, 참조판례, and a 판례내용 reduced to the sentences that name the
target case, verbatim). The search rows are the public 판례 목록 rows. No links or credentials are included.
"""

import json
import pathlib

import pytest

import lexlink.server as server_mod
from lexlink import precedent_status as ps
from lexlink.cache import get_cache

pytestmark = pytest.mark.unit

FIX = pathlib.Path(__file__).parent / "fixtures"


def body(name):
    return json.loads((FIX / f"prec_service_{name}_trimmed.json").read_text(encoding="utf-8"))["PrecService"]


def row(no, date, pid, kind="판결", name="", court="대법원"):
    return {"사건번호": no, "선고일자": date, "판례일련번호": pid, "판결유형": kind, "법원명": court, "사건명": name}


EB = "전원합의체 판결"
BODIES = {
    "170395": body("2010므4071"),
    "187485": body("2012므2888"),
    "126193": body("2004다26133"),
    "184812": body("2012다86895"),
}

# target -> (nb rows, citing-list rows)
LISTS = {
    "2001므718": (
        [row("2001므718", "2002.09.04", "219661", name="이혼및재산분할등")],
        [row("2012므2888", "2014.07.16", "187485", EB, "이혼등"),
         row("춘천지방법원-2013-나-670", "2013.10.11", "341456", "", "사해행위", court=""),
         row("2010므4071", "2013.06.20", "170395", EB, "이혼·이혼및재산분할등"),
         row("2005다74900", "2006.09.14", "215889", name="사해행위취소")]),
    "2001다39657": (
        [row("2001다39657", "2001.10.30", "600759", name="배당이의")],
        [row("2004다26133", "2007.06.21", "126193", EB, "배당이의"),
         row("대전지방법원논산지원-2006-가단-5591", "2006.12.27", "289978", "", "배당이의", court="")]),
    "2009다96984": (
        [row("2009다96984", "2010.04.29", "600955", name="임차보증금반환")],
        [row("2023다244895", "2023.11.02", "237923", name="구상금"),
         row("2012다86895", "2017.05.18", "184812", EB, "손해배상(기)·손해배상(기)"),
         row("2014나13609", "2014.06.20", "174940", "판결 : 확정", "손해배상(기)", court="서울중앙지방법원"),
         row("2011다107405", "2012.03.29", "161662", name="손해배상(기)")]),
}


class FakeClient:
    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == "/DRF/lawSearch.do":
            if params.get("nb"):
                rows = LISTS[params["nb"]][0]
            else:
                rows = LISTS[(params.get("query") or "").strip('"')][1]
            payload = {"PrecSearch": {"totalCnt": str(len(rows)), "page": "1", "prec": rows}}
        else:
            payload = {"PrecService": BODIES[str(params.get("ID"))]}
        return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                "raw_content": json.dumps(payload, ensure_ascii=False)}


@pytest.fixture
def status(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", FakeClient)
    monkeypatch.setenv("OC", "test")
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    get_cache().invalidate()
    server = server_mod.create_server()
    return lambda **kw: server._tool_manager.get_tool("prec_status").fn(**kw)


CASES = [
    # target, overruling decision, evidence kinds
    ("2001므718", "2010므4071", {"explicit_marker", "explicit_sentence"}),
    ("2001다39657", "2004다26133", {"explicit_marker", "explicit_sentence"}),
    ("2009다96984", "2012다86895", {"explicit_marker"}),
]


@pytest.mark.parametrize("target,overruler,kinds", CASES)
def test_real_overruling_stays_detected(status, target, overruler, kinds):
    out = status(case_number=target)
    assert out["status"] == "ok" and out["overruling_status"] == "overruled_found"
    assert {e["evidence"] for e in out["evidence"]} == kinds
    assert {e["source"]["case_number"] for e in out["evidence"]} == {overruler}
    assert all(e["source"]["decision_type"] == EB for e in out["evidence"])
    assert out["target"]["found_in_index"] is True
    assert out["searched_scope"]["unscannable"] == [] and out["searched_scope"]["unreadable"] == []
    assert not any("일부만 확인" in c or "읽지 않은" in c for c in out["caveats"])
    assert "읽지 않은 후보" not in out["statement"]


def test_2001므718_later_citation_without_marker_is_not_evidence(status):
    out = status(case_number="2001므718")
    assert {e["source"]["case_number"] for e in out["evidence"]} == {"2010므4071"}
    cited = [c["source"]["case_number"] for c in out["cited_without_change_marker"]]
    assert cited == ["2012므2888"]
    # 2012므2888 marks other cases (변경) in [1] but cites 2001므718 in [2] without a marker
    ev = ps.find_evidence({"참조판례": BODIES["187485"]["참조판례"]}, (2001, "므", 718))
    assert ev["explicit"] == [] and ev["cited"]


def test_2009다96984_marker_is_tied_to_its_own_entry(status):
    out = status(case_number="2009다96984")
    markers = [e for e in out["evidence"] if e["evidence"] == "explicit_marker"]
    assert len(markers) == 1
    assert "2009다96984" in markers[0]["quote"] and "86다카1066" not in markers[0]["quote"]
    assert "92다16652" not in markers[0]["quote"]
    # other marked entries in the same 참조판례 do not make an unmarked cited case look overruled
    ref = {"참조판례": BODIES["184812"]["참조판례"]}
    assert ps.find_evidence(ref, (1994, "다", 38182))["explicit"] == []
    assert ps.find_evidence(ref, (1986, "다카", 1066))["explicit"]
