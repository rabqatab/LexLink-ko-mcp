"""prec_search defaults (full-text scope), case-number routing, case_type post-filter, duplicate grouping,
date sanity warnings.

Rows are SYNTHETIC (invented ids, same field layout as the live upstream, checked 2026-11-20) except the
public case numbers/dates in the duplicate and date tests, which are taken from live public rows
(92므68 -> 602511/123909, 2024므14761 id 609449 dated 2023.12.26) and carry no body text.
"""

import json

import pytest

import lexlink.server as server_mod
from lexlink import prec_extras
from lexlink.cache import get_cache

FAKE_OC = "unit-test-oc"


def row(i, no, date="2024.01.01", court="대법원", kind="민사", code="400101", name="손해배상(기)", seq=None):
    return {"id": str(i), "판례일련번호": str(seq or 900000 + i), "사건번호": no, "선고일자": date, "법원명": court,
            "사건종류명": kind, "사건종류코드": code, "사건명": name}


class Rec:
    calls: list = []
    rows: list = []

    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        Rec.calls.append(dict(params))
        raw = json.dumps({"PrecSearch": {"totalCnt": str(len(Rec.rows)), "page": "1", "prec": Rec.rows}}, ensure_ascii=False)
        return {"status": "ok", "request_id": "fake", "upstream_type": response_type, "raw_content": raw}


@pytest.fixture
def tool(monkeypatch):
    get_cache().invalidate()
    monkeypatch.setattr(server_mod, "LawAPIClient", Rec)
    monkeypatch.setenv("OC", FAKE_OC)
    Rec.calls, Rec.rows = [], [row(1, "2024다1")]
    server = server_mod.create_server()
    yield lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)
    get_cache().invalidate()


# --- 1. default scope -----------------------------------------------------------

@pytest.mark.unit
def test_keyword_query_defaults_to_full_text(tool):
    out = tool("prec_search", query="재산분할 기여도")
    assert str(Rec.calls[-1]["search"]) == "2"
    assert out["search_applied"] == {"search": 2, "scope": "본문 전문검색", "defaulted": True}


@pytest.mark.unit
@pytest.mark.parametrize("s,scope", [(1, "사건명"), (2, "본문 전문검색"), (3, "참조판례")])
def test_explicit_search_is_kept(tool, s, scope):
    out = tool("prec_search", query="담보권", search=s)
    assert str(Rec.calls[-1]["search"]) == str(s)
    assert out["search_applied"] == {"search": s, "scope": scope, "defaulted": False}


@pytest.mark.unit
def test_star_query_sends_no_search_scope(tool):
    out = tool("prec_search", query="*", curt="대법원")
    assert "search" not in Rec.calls[-1] and "search_applied" not in out


@pytest.mark.unit
def test_full_text_keeps_upstream_order_but_case_name_search_still_reranks(tool):
    Rec.rows = [row(1, "2024다1", name="임금"), row(2, "2024다2", name="담보권 실행")]
    full = tool("prec_search", query="담보권")
    assert [r["사건명"] for r in full["ranked_data"]["prec"]] == ["임금", "담보권 실행"]
    get_cache().invalidate()
    named = tool("prec_search", query="담보권", search=1)
    assert named["ranked_data"]["prec"][0]["사건명"] == "담보권 실행"


# --- 2. case number as query ------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("q", ["63다131", "2013다61381", "4294민상1350", "2024므14761", " 92므68 "])
def test_sole_case_number_is_routed_to_nb(tool, q):
    out = tool("prec_search", query=q)
    p = Rec.calls[-1]
    assert p["nb"] == q.strip() and p["query"] == "*" and "search" not in p
    assert out["query_routed_to_nb"] is True and out["routed_nb"] == q.strip()
    assert any("nb=" in n for n in out["notes"])


@pytest.mark.unit
@pytest.mark.parametrize("q,kw", [
    ("63다131 손해배상", {}), ('"63다131"', {"search": 2}), ("63다131", {"search": 2}),
    ("94므1713, 1720", {}), ("손해배상", {}), ("63다131", {"nb": "2020다1"}),
])
def test_other_queries_are_not_routed(tool, q, kw):
    out = tool("prec_search", query=q, **kw)
    assert "query_routed_to_nb" not in out
    assert Rec.calls[-1]["query"] != "*" or kw.get("nb")


# --- 3/4. case_type post-filter ---------------------------------------------------

MIXED = lambda: [row(1, "2024다1"), row(2, "2024므2", kind="가사", code="400103"),
                 row(3, "2024도3", kind="형사", code="400102"), row(4, "2023르4", kind="가사", code="400103")]


@pytest.mark.unit
@pytest.mark.parametrize("ct", ["가사", "400103", " 가 사 "])
def test_case_type_filters_ranked_and_raw_rows_and_reports_counts(tool, ct):
    Rec.rows = MIXED()
    out = tool("prec_search", query="재산분할", case_type=ct, display=2)
    assert str(Rec.calls[-1]["display"]) == "100"          # a whole upstream window, display ignored
    assert [r["사건번호"] for r in out["ranked_data"]["prec"]] == ["2024므2", "2023르4"]
    f = out["case_type_filter"]
    assert (f["rows_before_filter"], f["rows_after_filter"], f["upstream_total"], f["code"]) == (4, 2, "4", "400103")
    raw = json.loads(out["raw_content"])["PrecSearch"]["prec"]
    assert [r["사건번호"] for r in raw] == ["2024므2", "2023르4"]


@pytest.mark.unit
def test_case_type_alias_unknown_and_xml(tool):
    Rec.rows = MIXED()
    assert tool("prec_search", query="x", case_type="행정")["case_type_filter"]["code"] == "400107"
    out = tool("prec_search", query="x", case_type="노동")
    assert out["case_type_filter"]["rows_after_filter"] == 0
    assert any(w.startswith("case_type_unknown") for w in out["warnings"])
    err = tool("prec_search", query="x", case_type="가사", type="XML")
    assert err["error_code"] == "VALIDATION_ERROR"


@pytest.mark.unit
def test_no_case_type_means_no_filter(tool):
    Rec.rows = MIXED()
    out = tool("prec_search", query="x")
    assert "case_type_filter" not in out and len(out["ranked_data"]["prec"]) == 4


# --- (a) duplicate groups ---------------------------------------------------------

@pytest.mark.unit
def test_duplicates_are_grouped_not_dropped(tool):
    Rec.rows = [row(1, "92므68", "1992.11.10", kind="가사", code="400103", seq=602511),
                row(2, "93스6", "1993.01.01", kind="가사", code="400103", seq=604435),
                row(3, "92므68", "1992.11.10", kind="가사", code="400103", seq=123909),
                row(4, "93스6", "1993.01.01", kind="가사", code="400103", seq=189896),
                row(5, "93스6", "1993.01.01", kind="가사", code="400103", seq=603259),
                row(6, "92므68", "1992.11.10", court="서울고등법원", kind="가사", code="400103", seq=777)]
    out = tool("prec_search", query="이혼")
    rows = out["ranked_data"]["prec"]
    assert [r["판례일련번호"] for r in rows] == ["602511", "604435", "777"]
    assert rows[0]["same_case_ids"] == ["123909"] and rows[1]["same_case_ids"] == ["189896", "603259"]
    assert "same_case_ids" not in rows[2]
    assert out["rows_before_grouping"] == 6
    assert {g["사건번호"]: g["판례일련번호"] for g in out["duplicate_groups"]} == {
        "92므68": ["602511", "123909"], "93스6": ["604435", "189896", "603259"]}
    # upstream rows stay untouched in raw_content (compatibility)
    raw = json.loads(out["raw_content"])["PrecSearch"]["prec"]
    assert len(raw) == 6 and all("same_case_ids" not in r for r in raw)


@pytest.mark.unit
def test_no_duplicates_adds_nothing(tool):
    Rec.rows = [row(1, "2024다1"), row(2, "2024다2")]
    out = tool("prec_search", query="x")
    assert "duplicate_groups" not in out and "rows_before_grouping" not in out


# --- (b) date sanity --------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("no,date,warns", [
    ("2024므14761", "2023.12.26", True),     # live row 609449
    ("2024므14761", "2024.07.25", False),
    ("63다131", "1963.05.09", False),         # two-digit year = 1963
    ("63다131", "1962.05.09", True),
    ("4294민상1350", "1961.03.01", False),    # 단기 4294 = 1961
    ("4294민상1350", "1960.03.01", True),
    ("2024므14761, 14778", "20231226", True),
    ("2013헌바1", "2013.01.01", False),
    ("", "2013.01.01", False),
])
def test_date_warning_table(no, date, warns):
    assert bool(prec_extras.date_warning(no, date)) is warns


@pytest.mark.unit
def test_search_row_gets_date_warning_without_changing_date(tool):
    Rec.rows = [row(1, "2024므14761", "2023.12.26", kind="가사", code="400103", seq=609449)]
    out = tool("prec_search", query="2024므14761")
    r = out["ranked_data"]["prec"][0]
    assert r["선고일자"] == "2023.12.26" and r["date_warning"].startswith("date_before_case_year")
    assert out["date_warning_rows"] == 1


def _svc(date, case_no, body):
    return {"status": "ok", "raw_content": json.dumps({"PrecService": {
        "사건번호": case_no, "선고일자": date, "판례내용": body}}, ensure_ascii=False)}


@pytest.mark.unit
def test_service_warns_on_case_year_and_on_lower_court_date():
    # synthetic body in the live layout (【원심판결】 court date docket 판결)
    body = "【원심판결】  전주지법 2024. 7. 25. 선고 2023르10710 판결<br/>【주 문】 상고를 기각한다."
    w = prec_extras.service_date_warnings(_svc("20231226", "2024므14761, 14778", body))
    assert [x.split(":")[0] for x in w] == ["date_before_case_year", "date_before_lower_court"]
    # consistent data: nothing
    assert prec_extras.service_date_warnings(_svc("20241226", "2024므14761", body)) == []
    # no 원심판결 / unparsable payloads never raise
    assert prec_extras.service_date_warnings(_svc("20241226", "2024므1", "본문")) == []
    assert prec_extras.service_date_warnings({"raw_content": "not json"}) == []
    assert prec_extras.service_date_warnings({}) == []


# --- review follow-ups (all rows SYNTHETIC) ------------------------------------------

def _src(i, seq, src, head="", kind="일반행정", code="400107", jud="판결"):
    r = row(i, "2024두1", "2025.10.16", kind=kind, code=code, seq=seq)
    r.update({"데이터출처명": src, "판결유형": jud, "판시사항": head})
    return r


@pytest.mark.unit
def test_representative_prefers_court_source_then_headnote_then_order(tool):
    Rec.rows = [_src(1, 11, "지방세법령정보시스템", kind="세무", code="400108", jud="파기환송"), _src(2, 12, "대법원")]
    out = tool("prec_search", query="x")
    r = out["ranked_data"]["prec"]
    assert len(r) == 1 and r[0]["판례일련번호"] == "12" and r[0]["same_case_ids"] == ["11"]
    g = out["duplicate_groups"][0]
    assert g["representative"] == "12" and [m["판례일련번호"] for m in g["members"]] == ["11", "12"]
    m11 = g["members"][0]
    assert (m11["데이터출처명"], m11["판결유형"], m11["사건종류명"]) == ("지방세법령정보시스템", "파기환송", "세무")
    assert set(m11["differs_from_representative"]) == {"데이터출처명", "판결유형", "사건종류명"}
    assert "differs_from_representative" not in g["members"][1]
    assert "서로 다를 수 있" in out["duplicate_groups_note"] and "같은 판결" not in out["duplicate_groups_note"]


@pytest.mark.unit
def test_representative_same_source_prefers_filled_headnote_else_first(tool):
    Rec.rows = [_src(1, 21, "대법원", head=""), _src(2, 22, "대법원", head="판시")]
    assert tool("prec_search", query="x")["ranked_data"]["prec"][0]["판례일련번호"] == "22"
    get_cache().invalidate()
    Rec.rows = [_src(1, 31, "대법원", head=""), _src(2, 32, "대법원", head="")]
    assert tool("prec_search", query="x")["ranked_data"]["prec"][0]["판례일련번호"] == "31"


@pytest.mark.unit
def test_source_order_court_over_unknown_over_other_system():
    from lexlink.prec_extras import _pick_representative
    a, b, c = {"판례일련번호": "a", "데이터출처명": "근로복지공단산재판례"}, {"판례일련번호": "b"}, {"판례일련번호": "c", "데이터출처명": "대법원"}
    assert _pick_representative([a, b, c])["판례일련번호"] == "c"
    assert _pick_representative([a, b])["판례일련번호"] == "b"


@pytest.mark.unit
def test_two_digit_years_are_1900s():
    assert prec_extras.case_number_year("49다1") == 1949
    assert prec_extras.case_number_year("99다1") == 1999
    assert prec_extras.case_number_year("2000다1") == 2000
    assert prec_extras.date_warning("49다1", "1949.03.01") is None
    assert prec_extras.date_warning("49다1", "1948.03.01")


@pytest.mark.unit
def test_constitutional_numbers_not_routed_but_hinted(tool):
    out = tool("prec_search", query="2013헌바1")
    assert "query_routed_to_nb" not in out and "nb" not in Rec.calls[-1]
    assert any("detc_search" in n for n in out["notes"])


@pytest.mark.unit
def test_routed_zero_rows_gets_specific_hints(tool):
    Rec.rows = []
    out = tool("prec_search", query="2013므3963")
    assert out["query_routed_to_nb"] is True
    assert any("결합사건" in h for h in out["hints"]) and not any("줄이거나" in h for h in out["hints"])


@pytest.mark.unit
def test_lowercase_type_accepted_for_case_type(tool):
    Rec.rows = MIXED()
    out = tool("prec_search", query="x", case_type="가사", type="json")
    assert out["case_type_filter"]["rows_after_filter"] == 2


@pytest.mark.unit
def test_single_row_dict_shape_is_kept():
    resp = {"status": "ok", "ranked_data": {"prec": row(1, "2024므1", kind="가사", code="400103")}}
    prec_extras.apply_case_type_filter(resp, ("가사", "400103", None))
    assert isinstance(resp["ranked_data"]["prec"], dict)
    prec_extras.group_duplicate_rows(resp)
    assert isinstance(resp["ranked_data"]["prec"], dict)
    resp2 = {"status": "ok", "ranked_data": {"prec": row(1, "2024도1")}}
    prec_extras.apply_case_type_filter(resp2, ("가사", "400103", None))
    assert resp2["ranked_data"]["prec"] == []


@pytest.mark.unit
def test_case_type_scope_present_with_zero_rows():
    resp = {"status": "ok", "ranked_data": {}}
    prec_extras.apply_case_type_filter(resp, ("가사", "400103", None))
    assert resp["case_type_filter"]["rows_before_filter"] == 0 and resp["case_type_filter"]["scope"]


@pytest.mark.unit
def test_constitutional_note_follows_applied_search(tool):
    default = tool("prec_search", query="2013헌바1")
    assert any("search=2" in n and "기본값" in n for n in default["notes"])
    get_cache().invalidate()
    explicit = tool("prec_search", query="2013헌바1", search=1)
    note = next(n for n in explicit["notes"] if "detc_search" in n)
    assert "search=1" in note and "search=2" not in note
