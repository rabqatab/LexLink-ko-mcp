"""law_constitutional_check: 헌재 decisions on a law article, outcome from the 주문 (offline).

tests/fixtures/detc_orders_live.json holds the verbatim 주문 of real decisions (law.go.kr detc_service,
read 2026-11-01); detc_service_trimmed.json holds two trimmed full responses.
"""

import json
import pathlib

import pytest

import lexlink.server as server_mod
from lexlink import constitutional as cn
from lexlink.cache import get_cache

pytestmark = pytest.mark.unit

FIX = pathlib.Path(__file__).parent / "fixtures"
ORDERS = json.loads((FIX / "detc_orders_live.json").read_text(encoding="utf-8"))
TRIMMED = json.loads((FIX / "detc_service_trimmed.json").read_text(encoding="utf-8"))


def by_case(no):
    return next((i, v) for i, v in ORDERS.items() if v["case_number"] == no)


def row(no):
    i, v = by_case(no)
    return {"헌재결정례일련번호": i, "사건번호": no, "종국일자": v["decision_date"], "사건명": v["case_name"]}


def body(no):
    i, v = by_case(no)
    return {"사건번호": no, "종국일자": v["decision_date"], "사건명": v["case_name"],
            "심판대상조문": v["target_provisions"], "판시사항": "", "전문": f"【주　　문】{v['order']}【이　　유】1. 사건개요"}


@pytest.mark.parametrize("title,law,art,branch,expected", [
    ("형법 제241조 위헌소원", "형법", 241, 0, True),
    ("형법 제241조 제1항 위헌확인", "형법", 241, 0, True),
    ("구 형법 제241조 위헌소원", "형법", 241, 0, True),
    ("민법(2005. 3. 31. 법률 제7427호로 개정된 것) 제847조 제1항 위헌소원", "민법", 847, 0, True),
    ("민법 제844조 제2항 등 위헌확인", "민법", 844, 0, True),
    ("관세법 제241조 제1항 등 위헌소원", "형법", 241, 0, False),
    ("군형법 제241조 위헌소원", "형법", 241, 0, False),
    ("민법 시행령 제1118조 위헌확인", "민법", 1118, 0, False),
    ("형법 제2410조 위헌소원", "형법", 241, 0, False),
    ("형법 제241조의2 위헌소원", "형법", 241, 0, False),
    ("형법 제241조의2 위헌소원", "형법", 241, 2, True),
    ("민법 제847조 제1항 위헌제청", "형법", 847, 0, False),
])
def test_title_names_article(title, law, art, branch, expected):
    assert cn.title_names_article(title, law, art, branch) is expected


@pytest.mark.parametrize("case,article,outcome,specific", [
    ("2009헌바17", 241, "위헌", True),                     # 형법 제241조(간통) 2015-02-26
    ("2007헌가17", 241, "합헌", True),                     # 2008-10-30
    ("2015헌바67", 241, "각하", False),
    ("95헌가14", 847, "헌법불합치", True),                 # 민법 제847조 제1항 1997-03-27
    ("2012헌바357", 847, "합헌", True),                    # 2015-03-26, rewritten provision
    ("95헌가6", 809, "헌법불합치", True),                  # 민법 제809조 제1항 (동성동본 금혼) 1997-07-16
    ("2018헌바115", 809, "합헌", True),                    # same 주문: 제809조 합헌, 제815조 헌법불합치
    ("2018헌바115", 815, "헌법불합치", True),
    ("2013헌마623", 844, "헌법불합치", True),
    ("2017헌바127", 270, "헌법불합치", True),              # 형법 제269조 제1항, 제270조 제1항 중 ‘의사’ (list of two articles)
    ("2017헌바127", 269, "헌법불합치", True),
    ("2020헌가4", 1118, "헌법불합치", True),               # 민법 제1112조 제1호부터 제3호 및 제1118조
    ("2020헌가4", 1113, "합헌", True),
    ("2020헌가4", 1112, "위헌/헌법불합치", True),          # 제4호 위헌, 제1호~제3호 헌법불합치
    ("2015헌마924", 14, "위헌", True),
])
def test_classify_real_orders(case, article, outcome, specific):
    i, v = by_case(case)
    got = cn.classify_order(v["order"], article, 0, "민법" if case[:4] in ("2018", "2013", "2020", "2012", "95헌가") and case != "2017헌바127" else None)
    labels = "/".join(dict.fromkeys(o["outcome"] for o in got["outcomes"]))
    assert labels == outcome
    assert got["article_specific"] is specific


def test_mixed_outcome_sentence_is_split_per_article():
    order = "민법 제1조는 헌법에 위반되지 아니하나 제2조는 헌법에 위반된다. 제3조 및 제4조는 헌법에 합치되지 아니한다."
    assert [o["outcome"] for o in cn.classify_order(order, 1, 0, "민법")["outcomes"]] == ["합헌"]
    assert [o["outcome"] for o in cn.classify_order(order, 2, 0, "민법")["outcomes"]] == ["위헌"]
    for art in (3, 4):
        assert [o["outcome"] for o in cn.classify_order(order, art, 0, "민법")["outcomes"]] == ["헌법불합치"]


def test_adverse_order_without_an_article_is_needs_review_not_adverse():
    fields = {"사건번호": "99헌가1", "종국일자": "20000101", "사건명": "민법 제5조 위헌제청",
              "전문": "【주　문】심판대상조항은 헌법에 위반된다.【이　유】1."}
    rec = cn.decision_record({"헌재결정례일련번호": "1"}, fields, 5, 0, "민법")
    assert rec["article_specific"] is False and rec["adverse"] is False and rec["needs_review"] is True


def test_sibling_regulation_sentences_are_not_attributed_to_the_law():
    order = "민법 시행령 제1118조는 헌법에 위반된다."
    assert cn.classify_order(order, 1118, 0, "민법")["outcomes"] == []


def test_extract_order_both_bracket_styles():
    for i in ("44928", "137419"):
        fields = TRIMMED[i]["DetcService"]
        order = cn.extract_order(fields)
        assert order and "헌법에" in order and "이유" not in order[:5]


def test_resolve_official_name():
    rows = [{"법령명한글": "난민법", "법령약칭명": ""}, {"법령명한글": "민법", "법령약칭명": ""},
            {"법령명한글": "가족관계의 등록 등에 관한 법률", "법령약칭명": "가족관계등록법"}]
    assert cn.resolve_official_name("민법", rows) == ("민법", "exact")
    assert cn.resolve_official_name("가족관계등록법", rows) == ("가족관계의 등록 등에 관한 법률", "abbreviation")
    assert cn.resolve_official_name("가족관계등록", rows) is None
    assert cn.resolve_official_name("없는법", rows) is None


# ---- tool ------------------------------------------------------------------------------------

NOISE = [
    {"헌재결정례일련번호": "999", "사건번호": "2022헌바187", "종국일자": "2025.10.23",
     "사건명": "특정범죄 가중처벌 등에 관한 법률 제6조 제5항 등 위헌소원"},
    {"헌재결정례일련번호": "998", "사건번호": "2013헌바388", "종국일자": "2015.10.21", "사건명": "관세법 제241조 제1항 등 위헌소원"},
]
FAM = "가족관계의 등록 등에 관한 법률"
LISTS = {
    "형법 제241조": NOISE + [row(n) for n in ("2015헌바67", "2009헌바17", "2014헌마276", "2013헌바357", "2013헌마362", "2007헌가17")],
    # 형법 제270조 is in the 주문 of 2017헌바127 (사건명: 형법 제269조 제1항 등)
    "형법 제270조": [row("2017헌바127"), row("2010헌바402")],
    # 민법 제1118조: 사건명 names 제1112조 / 제1113조 / 제809조; 2022헌마399 (제809조, 각하) has no 제1118조 in its 주문
    "민법 제1118조": [row("2020헌가4"), row("2012헌바467"), row("2022헌마399")],
    "민법 제815조": [row("2018헌바115")],
    f"{FAM} 제14조": [row(n) for n in ("2015헌마924", "2021헌마130", "2020헌마844", "2020헌마505")],
    "민법 제1조": [],
}
LAW_ROWS = {
    "민법": [{"법령명한글": "난민법", "법령약칭명": ""}, {"법령명한글": "민법", "법령약칭명": ""},
           {"법령명한글": "민법 시행령", "법령약칭명": ""}],
    "형법": [{"법령명한글": "형법", "법령약칭명": ""}],
    "가족관계등록법": [{"법령명한글": FAM, "법령약칭명": "가족관계등록법"}],
    FAM: [{"법령명한글": FAM, "법령약칭명": "가족관계등록법"}],
}


class FakeClient:
    calls: list = []
    fail = None
    totals: dict = {}
    bad_body: set = set()

    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        FakeClient.calls.append((endpoint, dict(params)))
        if FakeClient.fail:
            return dict(FakeClient.fail)
        if endpoint == "/DRF/lawSearch.do":
            if params.get("target") == "law":
                rows = LAW_ROWS.get(params["query"], [])
                raw = {"LawSearch": {"totalCnt": str(len(rows)), "law": rows}}
            else:
                q = params["query"].strip('"')
                rows = LISTS.get(q, [])
                raw = {"DetcSearch": {"totalCnt": str(FakeClient.totals.get(q, len(rows))), "Detc": rows}}
            return {"status": "ok", "request_id": "f", "upstream_type": "JSON", "raw_content": json.dumps(raw, ensure_ascii=False)}
        i = str(params["ID"])
        if i in FakeClient.bad_body:
            return {"status": "ok", "request_id": "f", "upstream_type": "JSON", "raw_content": "<html>점검</html>"}
        if i not in ORDERS:
            return {"status": "error", "error_code": "NOT_FOUND", "message": "일치하는 헌재결정례가 없습니다", "request_id": "f"}
        return {"status": "ok", "request_id": "f", "upstream_type": "JSON",
                "raw_content": json.dumps({"DetcService": body(ORDERS[i]["case_number"])}, ensure_ascii=False)}


@pytest.fixture
def check(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", FakeClient)
    monkeypatch.setenv("OC", "test")
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    FakeClient.calls, FakeClient.fail, FakeClient.totals, FakeClient.bad_body = [], None, {}, set()
    get_cache().invalidate()
    server = server_mod.create_server()
    return lambda **kw: server._tool_manager.get_tool("law_constitutional_check").fn(**kw)


def test_adultery_article_struck_down_is_found_as_a_lead(check):
    out = check(law_name="형법", article=241)
    assert out["status"] == "ok" and out["decision_status"] == "adverse_decision_found"
    adv = out["adverse_decisions"]
    assert [a["case_number"] for a in adv] == ["2009헌바17"] and adv[0]["outcome"] == "위헌"
    assert adv[0]["decision_date"] == "20150226" and adv[0]["article_specific"] is True
    assert "제241조는 헌법에 위반된다" in adv[0]["order"]
    assert {d["case_number"] for d in out["decisions"]} == {"2015헌바67", "2009헌바17", "2014헌마276", "2013헌바357", "2013헌마362", "2007헌가17"}
    assert next(d for d in out["decisions"] if d["case_number"] == "2007헌가17")["outcome"] == "합헌"
    assert out["upstream_calls"] == 2 + 6
    assert any("in_force는 바꾸지 않습니다" in c for c in out["caveats"])
    assert any("결정 이후 개정" in c for c in out["caveats"])        # the current text may have been amended


@pytest.mark.parametrize("law,art,case,outcome", [
    ("형법", 270, "2017헌바127", "헌법불합치"),          # 사건명 says 제269조 제1항 등
    ("민법", 1118, "2020헌가4", "헌법불합치"),           # 사건명 says 제1112조 등
    ("민법", 815, "2018헌바115", "헌법불합치"),          # 사건명 says 제809조 제1항 등
    ("가족관계등록법", 14, "2015헌마924", "위헌"),       # abbreviation of the official name
])
def test_article_decided_in_a_decision_titled_for_another_article_is_found(check, law, art, case, outcome):
    out = check(law_name=law, article=art)
    assert out["decision_status"] == "adverse_decision_found", out["statement"]
    got = next(d for d in out["adverse_decisions"] if d["case_number"] == case)
    assert got["outcome"] == outcome and got["article_specific"] is True


def test_decisions_titled_for_the_law_but_not_deciding_the_article_are_dropped(check):
    out = check(law_name="민법", article=1118)
    sc = out["searched_scope"]
    assert [d["case_number"] for d in sc["dropped_no_article_in_order"]] == ["2022헌마399"]
    assert next(d for d in out["decisions"] if d["case_number"] == "2012헌바467")["outcome"] == "합헌"


def test_abbreviation_is_resolved_and_reported(check):
    out = check(law_name="가족관계등록법", article=14)
    assert out["searched_scope"]["law_name_official"] == FAM and out["searched_scope"]["law_name_resolved_by"] == "abbreviation"
    assert any("약칭" in c for c in out["caveats"])


def test_unknown_law_name_is_an_error_never_clean(check):
    out = check(law_name="없는법률명", article=1)
    assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR" and "decision_status" not in out


def test_budget_unread_candidates_make_it_incomplete(check):
    out = check(law_name="형법", article="제241조", max_scan=2)
    sc = out["searched_scope"]
    assert sc["scanned"] == 2 and len(sc["not_scanned"]) == 4 and out["upstream_calls"] == 2 + 2
    assert out["decision_status"] in ("adverse_decision_found", "incomplete_search")
    assert any("읽었습니다" in c for c in out["caveats"])
    LISTS["형법 제999조"] = [row(n) for n in ("2015헌바67", "2014헌마276")]
    ORDERS_TITLE = {"형법 제999조": "형법 제999조 위헌소원"}
    try:
        for r in LISTS["형법 제999조"]:
            r["사건명"] = ORDERS_TITLE["형법 제999조"]
        none_found = check(law_name="형법", article=999, max_scan=1)
    finally:
        del LISTS["형법 제999조"]
    assert none_found["decision_status"] == "incomplete_search" and "판단할 수 없습니다" in none_found["statement"]


def test_truncated_search_list_is_incomplete(check):
    FakeClient.totals["민법 제1조"] = 250
    out = check(law_name="민법", article=1)
    assert out["decision_status"] == "incomplete_search" and out["searched_scope"]["list_truncated"] is True


def test_no_candidates_complete_search_is_not_a_clean_bill(check):
    out = check(law_name="민법", article=1)
    assert out["decision_status"] == "no_adverse_decision_in_searched_set"
    assert "뜻이 아닙니다" in out["statement"]


def test_unreadable_body_is_an_error(check):
    FakeClient.bad_body = {by_case("2009헌바17")[0]}
    out = check(law_name="형법", article=241)
    assert out["status"] == "error" and "decision_status" not in out


def test_upstream_failure_is_error(check):
    FakeClient.fail = {"status": "error", "error_code": "TIMEOUT", "message": "x", "request_id": "r"}
    out = check(law_name="형법", article=241)
    assert out["status"] == "error" and out["error_code"] == "TIMEOUT" and "decision_status" not in out


def test_validation(check):
    assert check(law_name="", article=1)["error_code"] == "VALIDATION_ERROR"
    assert check(law_name="형법", article="")["error_code"] == "VALIDATION_ERROR"


def test_policy():
    from lexlink.tool_policy import TOOL_POLICIES
    assert TOOL_POLICIES["law_constitutional_check"]["category"] == "constitutional"


# ---- 2009헌바106 (민법 제1008조): old 전문 without brackets (integration review M3) ----

OLD_JEONMUN = (
    "사      건      2009헌바106  민법 제1008조 등 위헌소원청  구  인      김○갑당해사건      "
    "대전지방법원 서산지원 2005가단9038 소유권이전등기주           문이 사건 심판청구를 각하한다.이           유"
    "기록에 의하면, 청구인은 변호사를 대리인으로 선임하지 아니한 채 이 사건 심판청구를 하였고 ..."
)


def test_extract_order_spaced_old_form():
    assert cn.extract_order({"전문": OLD_JEONMUN}) == "이 사건 심판청구를 각하한다."
    rec = cn.decision_record({"사건번호": "2009헌바106", "사건명": "민법 제1008조 등 위헌소원"},
                             {"전문": OLD_JEONMUN, "사건번호": "2009헌바106"}, 1008, 0, "민법")
    assert rec["outcome"] == "각하" and not rec["needs_review"]


def test_unreadable_order_is_never_clean():
    row = {"헌재결정례일련번호": "1", "사건번호": "2000헌바1", "사건명": "민법 제1008조 위헌소원", "종국일자": "2000.01.01"}
    res = cn.check_article(
        law_name="민법", article=1008, branch=0,
        search=lambda p: {"total": 1, "rows": [row]},
        service=lambda i: {"전문": "본문 없음", "사건번호": "2000헌바1", "사건명": row["사건명"]})
    assert res["decisions"][0]["outcome"] == "불명"
    assert res["decision_status"] == cn.NEEDS_REVIEW
