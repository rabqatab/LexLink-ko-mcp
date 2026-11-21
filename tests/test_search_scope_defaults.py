"""detc/expc/decc_search default to full-text scope (search=2) like prec_search, plus detc case-number routing.

Rows are SYNTHETIC (invented ids and titles, same field layout as the live upstream).
"""

import json

import pytest

import lexlink.server as server_mod
from lexlink.cache import get_cache

FAKE_OC = "unit-test-oc"

ROOTS = {"prec": ("PrecSearch", "prec", "사건명"),
         "detc": ("DetcSearch", "Detc", "사건명"),
         "expc": ("ExpcSearch", "Expc", "안건명"),
         "decc": ("DeccSearch", "Decc", "사건명")}


def mkrow(tool, i, title, no="2024헌바1"):
    key = ROOTS[tool][2]
    return {"id": str(i), key: title, "사건번호": no}


class Rec:
    calls: list = []
    rows: list = []
    root = ("DetcSearch", "Detc")

    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        Rec.calls.append(dict(params))
        raw = json.dumps({Rec.root[0]: {"totalCnt": str(len(Rec.rows)), "page": "1", Rec.root[1]: Rec.rows}},
                         ensure_ascii=False)
        return {"status": "ok", "request_id": "fake", "upstream_type": response_type, "raw_content": raw}


@pytest.fixture
def tool(monkeypatch):
    get_cache().invalidate()
    monkeypatch.setattr(server_mod, "LawAPIClient", Rec)
    monkeypatch.setenv("OC", FAKE_OC)
    Rec.calls, Rec.rows = [], []
    server = server_mod.create_server()

    def call(name, **kw):
        t = name.split("_")[0]
        Rec.root = ROOTS[t][:2]
        if not Rec.rows:
            Rec.rows = [mkrow(t, 1, "임의 사건")]
        return server._tool_manager.get_tool(name).fn(**kw)

    yield call
    get_cache().invalidate()


def titles(out, tool):
    rows = out["ranked_data"][tool.capitalize()]
    rows = [rows] if isinstance(rows, dict) else rows
    return [r[ROOTS[tool][2]] for r in rows]


TOOLS = [("detc_search", "detc", "사건명"), ("expc_search", "expc", "안건명"), ("decc_search", "decc", "사건명")]


@pytest.mark.unit
@pytest.mark.parametrize("name,t,label", TOOLS)
def test_keyword_defaults_to_full_text(tool, name, t, label):
    out = tool(name, query="재판청구권 제척기간")
    assert str(Rec.calls[-1]["search"]) == "2"
    assert out["search_applied"] == {"search": 2, "scope": "본문 전문검색", "defaulted": True}


@pytest.mark.unit
@pytest.mark.parametrize("name,t,label", TOOLS)
def test_star_query_sends_no_search(tool, name, t, label):
    out = tool(name, query="*")
    assert "search" not in Rec.calls[-1] and "search_applied" not in out


@pytest.mark.unit
@pytest.mark.parametrize("name,t,label", TOOLS)
def test_explicit_search_kept_and_title_rerank_only_for_search_1(tool, name, t, label):
    Rec.rows = [mkrow(t, 1, "임금"), mkrow(t, 2, "담보권 실행")]
    full = tool(name, query="담보권")
    assert titles(full, t) == ["임금", "담보권 실행"]
    get_cache().invalidate()
    named = tool(name, query="담보권", search=1)
    assert str(Rec.calls[-1]["search"]) == "1"
    assert named["search_applied"] == {"search": 1, "scope": label, "defaulted": False}
    assert titles(named, t)[0] == "담보권 실행"
    get_cache().invalidate()
    explicit2 = tool(name, query="담보권", search=2)
    assert explicit2["search_applied"]["defaulted"] is False
    assert titles(explicit2, t) == ["임금", "담보권 실행"]


@pytest.mark.unit
@pytest.mark.parametrize("name,t,label", TOOLS)
def test_invalid_search_rejected(tool, name, t, label):
    out = tool(name, query="x", search=3)
    assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR"
    assert not Rec.calls


# --- detc case-number routing ---------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("q,nb", [("2013헌바1", "2013헌바1"), ("2022헌마1312", "2022헌마1312"),
                                  (" 2022 헌마 1312 ", "2022헌마1312")])
def test_detc_sole_case_number_is_routed_to_nb(tool, q, nb):
    out = tool("detc_search", query=q)
    p = Rec.calls[-1]
    assert p["nb"] == nb and "query" not in p and "search" not in p
    assert out["query_routed_to_nb"] is True and out["routed_nb"] == nb
    assert "search_applied" not in out
    assert any("nb" in n for n in out["notes"])


@pytest.mark.unit
@pytest.mark.parametrize("kw", [{"query": '"2013헌바1"'}, {"query": "2013헌바1 위헌"},
                                {"query": "2013헌바1", "search": 2}])
def test_detc_not_routed(tool, kw):
    out = tool("detc_search", **kw)
    assert "nb" not in Rec.calls[-1]
    assert "query_routed_to_nb" not in out
    assert str(Rec.calls[-1]["search"]) == "2"


@pytest.mark.unit
def test_detc_explicit_nb_is_not_rerouted(tool):
    out = tool("detc_search", query="*", nb="2013헌바1")
    assert Rec.calls[-1]["nb"] == "2013헌바1" and "query_routed_to_nb" not in out
    out = tool("detc_search", query="2014헌바9", nb="2013헌바1")
    assert out["status"] == "error"


@pytest.mark.unit
def test_detc_routed_zero_rows_gets_hints(tool, monkeypatch):
    monkeypatch.setattr(Rec, "rows", [])
    monkeypatch.setattr(Rec, "root", ROOTS["detc"][:2])
    out = server_mod.create_server()._tool_manager.get_tool("detc_search").fn(query="2099헌바1")
    assert out["query_routed_to_nb"] is True
    assert out["hints"] and "0건" in out["hints"][0]


@pytest.mark.unit
def test_detc_routed_exact_row_has_no_zero_hint_and_uses_display_100(tool):
    Rec.rows = [mkrow("detc", 1, "가", no="2022헌마13120"), mkrow("detc", 2, "나", no="2022헌마1312")]
    out = tool("detc_search", query="2022헌마1312", display=5, page=3)
    p = Rec.calls[-1]
    assert str(p["display"]) == "100" and str(p["page"]) == "1" and p["nb"] == "2022헌마1312"
    assert "hints" not in out
    assert [r["사건번호"] for r in out["ranked_data"]["Detc"]] == ["2022헌마1312"]
    assert any("display=100, page=1" in n and "nb=" in n for n in out["notes"])
    assert len(out["notes"]) == 1


@pytest.mark.unit
def test_detc_routed_exact_absent_gets_note_not_zero_hint(tool):
    Rec.rows = [mkrow("detc", 1, "가", no="2013헌바178"), mkrow("detc", 2, "나", no="2013헌바191")]
    out = tool("detc_search", query="2013헌바1")
    assert "hints" not in out
    assert any("100건" in n for n in out["notes"])


@pytest.mark.unit
def test_detc_routed_xml_has_no_false_hint(tool):
    out = tool("detc_search", query="2013헌바1", type="XML")
    assert "hints" not in out


@pytest.mark.unit
@pytest.mark.parametrize("q", ["2022헌마1312", "2013 헌바 1", "２０１３헌바１"])
def test_prec_search_does_not_route_constitutional_numbers(tool, q):
    out = tool("prec_search", query=q)
    p = Rec.calls[-1]
    assert "nb" not in p and "query_routed_to_nb" not in out
    assert any("헌법재판소" in n for n in out["notes"])


@pytest.mark.unit
def test_prec_search_court_case_number_still_routed(tool):
    out = tool("prec_search", query="2013다61381")
    assert Rec.calls[-1]["nb"] == "2013다61381" and out["query_routed_to_nb"] is True


@pytest.mark.unit
def test_detc_routed_has_no_display_cap_warning(tool):
    out = tool("detc_search", query="2013헌바1", display=500)
    assert str(Rec.calls[-1]["display"]) == "100"
    from lexlink.guards import DISPLAY_CAPPED_WARNING
    assert DISPLAY_CAPPED_WARNING.format(d=500) not in out.get("warnings", [])
