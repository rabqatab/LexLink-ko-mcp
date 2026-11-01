"""law_constitutional_check: 헌재 decisions naming a law article, outcome from the 주문 (offline).

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
    ("형법 제2410조 위헌소원", "형법", 241, 0, False),
    ("형법 제241조의2 위헌소원", "형법", 241, 0, False),
    ("형법 제241조의2 위헌소원", "형법", 241, 2, True),
    ("민법 제847조 제1항 위헌제청", "형법", 847, 0, False),
])
def test_title_names_article(title, law, art, branch, expected):
    assert cn.title_names_article(title, law, art, branch) is expected


@pytest.mark.parametrize("case,article,branch,outcome,specific", [
    ("2009헌바17", 241, 0, "위헌", True),                 # 형법 제241조(간통) 2015-02-26
    ("2007헌가17", 241, 0, "합헌", True),                 # 2008-10-30
    ("2015헌바67", 241, 0, "각하", False),
    ("95헌가14", 847, 0, "헌법불합치", True),             # 민법 제847조 제1항 1997-03-27
    ("2012헌바357", 847, 0, "합헌", True),                # 2015-03-26, rewritten provision
    ("95헌가6", 809, 0, "헌법불합치", True),              # 민법 제809조 제1항 (동성동본 금혼) 1997-07-16
    ("2018헌바115", 809, 0, "합헌", True),                # same 주문: 제809조 합헌, 제815조 헌법불합치
    ("2018헌바115", 815, 0, "헌법불합치", True),
    ("2013헌마623", 844, 0, "헌법불합치", True),
])
def test_classify_real_orders(case, article, branch, outcome, specific):
    i, v = by_case(case)
    got = cn.classify_order(v["order"], article, branch)
    assert [o["outcome"] for o in got["outcomes"]] == [outcome]
    assert got["article_specific"] is specific


def test_extract_order_both_bracket_styles():
    for i in ("44928", "137419"):
        fields = TRIMMED[i]["DetcService"]
        order = cn.extract_order(fields)
        assert order and "헌법에" in order and "이유" not in order[:5]


# ---- tool ------------------------------------------------------------------------------------

ROWS_241 = [row(n) for n in ("2015헌바67", "2009헌바17", "2014헌마276", "2013헌바357", "2013헌마362", "2007헌가17")]
ROWS_241.insert(0, {"헌재결정례일련번호": "999", "사건번호": "2022헌바187", "종국일자": "2025.10.23",
                    "사건명": "특정범죄 가중처벌 등에 관한 법률 제6조 제5항 등 위헌소원"})
ROWS_241.append({"헌재결정례일련번호": "998", "사건번호": "2013헌바388", "종국일자": "2015.10.21",
                 "사건명": "관세법 제241조 제1항 등 위헌소원"})
LISTS = {"형법 제241조": ROWS_241, "민법 제847조": [row("2012헌바357"), row("95헌가14")], "민법 제1조": []}


class FakeClient:
    calls: list = []
    fail = None

    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        FakeClient.calls.append((endpoint, dict(params)))
        if FakeClient.fail:
            return dict(FakeClient.fail)
        if endpoint == "/DRF/lawSearch.do":
            rows = LISTS.get(params["query"], [])
            raw = {"DetcSearch": {"totalCnt": str(len(rows)), "Detc": rows}}
            return {"status": "ok", "request_id": "f", "upstream_type": "JSON", "raw_content": json.dumps(raw, ensure_ascii=False)}
        i = str(params["ID"])
        if i not in ORDERS:
            return {"status": "error", "error_code": "NOT_FOUND", "message": "일치하는 헌재결정례가 없습니다", "request_id": "f"}
        return {"status": "ok", "request_id": "f", "upstream_type": "JSON",
                "raw_content": json.dumps({"DetcService": body(ORDERS[i]["case_number"])}, ensure_ascii=False)}


@pytest.fixture
def check(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", FakeClient)
    monkeypatch.setenv("OC", "test")
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    FakeClient.calls, FakeClient.fail = [], None
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
    # other articles' decisions (특가법, 관세법 제241조) never become candidates; 합헌/각하 ones are listed but not adverse
    assert {d["case_number"] for d in out["decisions"]} == {"2015헌바67", "2009헌바17", "2014헌마276", "2013헌바357", "2013헌마362", "2007헌가17"}
    assert next(d for d in out["decisions"] if d["case_number"] == "2007헌가17")["outcome"] == "합헌"
    assert out["upstream_calls"] == 1 + 6 and any("in_force는 바꾸지 않습니다" in c for c in out["caveats"])


def test_budget_and_not_scanned(check):
    out = check(law_name="형법", article="제241조", max_scan=2)
    sc = out["searched_scope"]
    assert sc["scanned"] == 2 and len(sc["not_scanned"]) == 4 and out["upstream_calls"] == 3
    assert any("읽었습니다" in c for c in out["caveats"])


def test_no_adverse_is_not_a_clean_bill(check):
    out = check(law_name="민법", article=1)
    assert out["decision_status"] == "no_adverse_decision_in_searched_set"
    assert "뜻이 아닙니다" in out["statement"]


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
