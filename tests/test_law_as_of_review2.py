"""Second review round: same-name predecessor, NOT_CURRENT_UPSTREAM, statements, id+mst+ef_yd,
period truncation, future D, 부칙 scan precision/recall, input checks, SLIM markers."""

import pytest

import lexlink.server as server_mod
from lexlink._helpers import slim_hint
from lexlink.article_text import normalize_article
from lexlink.as_of import expired_unknown, scan_bupchik
from test_law_as_of import FakeClient, T, as_of  # noqa: F401  (as_of is a fixture)


def _tools():
    return {t.name: t for t in server_mod.create_server()._tool_manager.list_tools()}


# ---- 1. same-name predecessor with another 법령ID
def test_same_name_predecessor_with_other_law_id_is_used(as_of):
    out = as_of(law_name="연속법", as_of="1995-01-01", article=1)
    assert out["in_force"] is True and out["law"]["law_id"] == "005555"
    assert out["version"]["mst"] == "51" and out["article"]["text"].endswith("구법")
    assert out["same_name_predecessor"] == {"law_id": "005555", "replaced_law_id": "005556", "law_name": "연속법"}
    assert any("구법" in c and "005555" in c for c in out["caveats"])
    assert out["comparison"]["current_state"] == "in_force"            # compared with the current law's LID
    assert out["comparison"]["differs_from_current"] is True
    now = as_of(law_name="연속법", as_of="1997-01-01", article=1)
    assert now["law"]["law_id"] == "005556" and "same_name_predecessor" not in now


def test_predecessor_repeal_and_unknown_before_both(as_of):
    gap = as_of(law_name="연속법", as_of="19970101")
    assert gap["law"]["law_id"] == "005556"
    early = as_of(law_name="연속법", as_of="1980-01-01")
    assert early["in_force"] is False and early["reason"] == "BEFORE_EARLIEST_AVAILABLE_VERSION"
    assert early["same_name_other_law_ids"] == ["005555"]                # never asserts "not in force"
    assert "BEFORE_FIRST_ENFORCEMENT" != early["reason"]


def test_predecessor_lookup_failure_is_not_definitive(as_of, monkeypatch):
    real_get = FakeClient.get

    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == "/DRF/lawSearch.do" and params.get("efYd"):
            FakeClient.calls.append((endpoint, dict(params)))
            return {"status": "error", "error_code": "TIMEOUT", "message": "x", "request_id": "r"}
        return real_get(self, endpoint, params, response_type)

    monkeypatch.setattr(FakeClient, "get", get)
    out = as_of(law_name=T, as_of="2009-12-31")
    assert out["reason"] == "BEFORE_EARLIEST_AVAILABLE_VERSION"
    assert any("확정할 수 없습니다" in c for c in out["caveats"])


# ---- 2. all-연혁 law: unknown, not "in force"
def test_all_history_law_after_last_version_is_not_current_upstream(as_of):
    for d in ("20240101", "19950101"):
        out = as_of(law_name="004444", as_of=d)
        assert out["in_force"] is None and out["reason"] == "NOT_CURRENT_UPSTREAM"
        assert out["last_version"]["mst"] == "62" and "확인할 수 없습니다" in out["statement"]
    inside = as_of(law_name="004444", as_of="19920101")
    assert inside["in_force"] is True and inside["version"]["mst"] == "61"
    assert inside["comparison"]["current_state"] == "not_current_upstream"
    assert inside["comparison"]["differs_from_current"] is None
    assert as_of(law_name="한시법", as_of="20240101")["reason"] == "NOT_CURRENT_UPSTREAM"  # by name too


def test_expired_unknown_rule():
    rows = lambda *st: [{"row": {"현행연혁코드": s, "제개정구분명": k}} for s, k in st]
    assert expired_unknown(rows(("연혁", "제정"), ("연혁", "일부개정")))
    assert not expired_unknown(rows(("연혁", "제정"), ("현행", "일부개정")))
    assert not expired_unknown(rows(("연혁", "제정"), ("연혁", "폐지")))
    assert not expired_unknown(rows(("연혁", "제정"), ("시행예정", "일부개정")))


# ---- 3 + 5. statements
def test_period_statement_reflects_article_status(as_of):
    out = as_of(law_name=T, as_of="20180301", as_of_end="20181231", article="3의2")
    st = out["statement"]
    assert out["article_status"] == "ARTICLE_NOT_FOUND"
    assert "해당 조문(제3조의2)이 없습니다" in st and "시행 중인 버전은 MST 300" in st
    assert "MST 300(시행 20180301): 조문 없음" in st and "MST 300(시행 20180901): 있음" in st


def test_period_truncation_is_stated(as_of):
    out = as_of(law_name="다개정법", as_of="20000101", as_of_end="20201231")
    p = out["period"]
    assert p["truncated"] is True and p["total_revisions_in_period"] == 14 and p["revision_count"] == 12
    assert "14개" in out["statement"] and "처음 12개만 조회" in out["statement"]


# ---- 4. id + mst + ef_yd
@pytest.mark.parametrize("tool", ["eflaw_service", "eflaw_josub"])
def test_id_is_dropped_when_mst_and_ef_yd_are_given(as_of, tool):
    fn = server_mod.create_server()._tool_manager.get_tool(tool).fn
    fn(id="009999", mst="200", ef_yd="20150101", jo=1)
    sent = FakeClient.calls[-1][1]
    assert sent["MST"] == "200" and str(sent["efYd"]) == "20150101" and "ID" not in sent
    fn(id="009999", mst="200", jo=1, **({"ef_yd": None}))   # without ef_yd the id is left alone
    assert FakeClient.calls[-1][1].get("ID") == "009999"
    assert fn(id="009999", ef_yd="20150101", jo=1)["error_code"] == "VALIDATION_ERROR"


# ---- 6. future D
def test_future_date_caveat(as_of):
    out = as_of(law_name=T, as_of="20300101", article=1)
    assert any("미래 날짜" in c and "알려진 개정만 반영" in c for c in out["caveats"])
    assert not any("미래 날짜" in c for c in as_of(law_name=T, as_of="20200101", article=1)["caveats"])


# ---- 7. 부칙 scan precision and recall
def _unit(*lines):
    return {"부칙공포일자": "20180320", "부칙공포번호": "1", "부칙내용": [["부칙 <제1호,2018.3.20>", *lines]]}


def test_scan_ignores_other_laws_articles():
    u = _unit("제1조(시행일) 이 법은 2019년 1월 1일부터 시행한다. 다만, 「공공기관의 운영에 관한 법률」 제4조에 따른 "
              "기관은 2025년 1월 1일부터 시행한다.",
              "제2조 「지방공기업법」 제49조의 개정규정은 2026년 1월 1일부터 시행한다.",
              "제3조 같은 법 제5조의 개정규정은 2027년 1월 1일부터 시행한다.")
    for art in (4, 49, 5):
        assert scan_bupchik([u], art, 0, "20190101") == [], art


def test_scan_binds_dates_to_the_clause_naming_the_article():
    u = _unit("제1조(시행일) 이 법은 공포한 날부터 시행한다. 다만, 제12조제4호의 개정규정은 공포한 날부터 시행하고, "
              "제94조제1항제3호의 개정규정은 2009년 2월 4일부터 시행하며, 제21조의 개정규정은 2011년 1월 1일부터 시행한다.")
    assert scan_bupchik([u], 94, 0, "20100630") == []
    hit = scan_bupchik([u], 21, 0, "20100630")
    assert len(hit) == 1 and hit[0]["later_dates"] == ["20110101"]
    assert "제94조" not in hit[0]["text"]


def test_scan_ranges_start_of_line_and_dotted_dates():
    u = _unit("제1조 (시행일) 이 법은 공포한 날부터 시행한다.",
              "제5조부터 제8조까지의 개정규정은 2022. 1. 1.부터 시행한다.",
              "제3조 제5조의2부터 제5조의5까지의 개정규정은 2023년 7월 1일부터 시행한다.")
    assert [h["later_dates"] for h in scan_bupchik([u], 6, 0, "20200101")] == [["20220101"]]
    assert scan_bupchik([u], 9, 0, "20200101") == []
    # 제5조의3 lies in both ranges (제5조..제8조 and 제5조의2..제5조의5); plain 제5조 only in the first
    assert [h["later_dates"] for h in scan_bupchik([u], 5, 3, "20200101")] == [["20220101"], ["20230701"]]
    assert [h["later_dates"] for h in scan_bupchik([u], 5, 0, "20200101")] == [["20220101"]]
    assert [h["later_dates"] for h in scan_bupchik([u], 5, 6, "20200101")] == [["20220101"]]
    assert scan_bupchik([u], 6, 0, "20220101") == []


def test_scan_gak_ho_items_belong_to_the_naming_sentence():
    u = _unit("④ 제55조제2항의 개정규정은 다음 각 호의 구분에 따른 날부터 시행한다.", "1. 300명 이상: 2020년 1월 1일",
              "2. 그 밖: 2021년 1월 1일", "⑤ 제56조의 개정규정은 2030년 1월 1일부터 시행한다.")
    assert scan_bupchik([u], 55, 0, "20191231")[0]["later_dates"] == ["20200101", "20210101"]
    assert [h["later_dates"] for h in scan_bupchik([u], 56, 0, "20191231")] == [["20300101"]]


# ---- 8/9 are covered in test_law_as_of_review.py (count excluding the selected MST, own later dates)
def test_pending_excludes_selected_versions_own_staged_dates(as_of):
    out = as_of(law_name=T, as_of="20180301", article=2)       # MST 300 is staged: 20180301 and 20180901
    assert out["selected_version_later_effective_dates"] == ["20180901"]
    assert all(v["mst"] != "300" for v in out.get("promulgated_not_yet_effective", []))


# ---- 10. input checks and name matching
def test_article_code_and_branch_conflict_is_an_error(as_of):
    with pytest.raises(ValueError):
        normalize_article("007602", 5)
    assert normalize_article("007602", 2) == (76, 2)
    out = as_of(law_name=T, as_of="20200101", article="000302", article_branch=5)
    assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR"


def test_partial_name_is_flagged(as_of):
    exact = as_of(law_name=T, as_of="20200101")
    assert exact["name_match"] == "exact"
    part = as_of(law_name="테스", as_of="20200101")
    assert part["name_match"] == "partial" and part["law"]["law_name"] == T
    assert any("정확히 일치하지 않아" in c for c in part["caveats"])
    assert as_of(law_name="9999", as_of="20200101")["name_match"] == "id"


def test_docstring_example_is_consistent():
    doc = _tools()["law_as_of"].description
    assert 'as_of="2019-07-16", article=76, article_branch=2' in doc and "2019-07-15" not in doc


# ---- 11. neutral wording
def test_statements_have_no_particle_placeholders(as_of):
    outs = [as_of(law_name=T, as_of="20200101", article=1), as_of(law_name=T, as_of="20200101"),
            as_of(law_name=T, as_of="20091231"), as_of(law_name="폐지법", as_of="20100101"),
            as_of(law_name="004444", as_of="20240101"), as_of(law_name="개명법", as_of="20050101")]
    for o in outs:
        text = o["statement"] + " ".join(o.get("caveats", []))
        assert "은(는)" not in text and "이(가)" not in text and "을(를)" not in text, text


# ---- 12. SLIM markers and hints
def test_slim_reports_truncated_fields(as_of, monkeypatch):
    full = as_of(law_name=T, as_of="20160101", article=1)
    assert "truncated_fields" not in full
    monkeypatch.setenv("SLIM_RESPONSE", "1")
    slim = as_of(law_name=T, as_of="20160101", article=1)
    for k in ("neighbors", "scheduled_versions", "comparison.current_article_text"):
        assert k in slim["truncated_fields"], slim["truncated_fields"]
        assert k.split(".")[0] not in slim or k.startswith("comparison")
    assert "neighbors" not in slim


def test_slim_hint_for_sections_tools_does_not_point_to_summary_as_more():
    hint = slim_hint({"id": 1, "sections": 1})
    assert "받을 수 없습니다" in hint and 'sections="summary"로' not in hint and 'sections="summary"(으)로' not in hint
    assert "jo로 조문 지정" in slim_hint({"jo": 1})


def test_chain_amendment_track_date_schema_is_described(as_of):
    props = _tools()["chain_amendment_track"].parameters["properties"]
    assert "공포일" in props["date_from"]["description"] and "공포일" in props["date_to"]["description"]
