"""Adversarial-review fixes: 폐지제정, 부칙 staged enforcement, counts, renamed laws, 삭제 articles."""

from test_law_as_of import FakeClient, T, as_of  # noqa: F401  (as_of is a fixture)
from lexlink.as_of import is_deleted_article, is_repeal, scan_bupchik


def test_is_repeal_exact_kinds_only():
    assert is_repeal({"제개정구분명": "폐지"}) and is_repeal({"제개정구분명": "타법폐지"})
    assert not is_repeal({"제개정구분명": "폐지제정"})
    assert not is_repeal({"제개정구분명": "일부개정"})


def test_repeal_and_reenact_is_in_force(as_of):
    out = as_of(law_name="폐지제정법", as_of="20050601", article=1)
    assert out["in_force"] is True and out["version"]["revision_type"] == "폐지제정"
    assert out["version"]["mst"] == "22" and "reason" not in out
    assert as_of(law_name="폐지제정법", as_of="20050531")["version"]["mst"] == "21"


def test_later_amendments_count_is_distinct_revisions(as_of):
    out = as_of(law_name=T, as_of="20180301")  # later: 300@20180901, 400, 410, 500
    la = out["later_amendments"]
    assert la["count"] == 4 and la["effective_date_count"] == 4
    out = as_of(law_name=T, as_of="20171231")  # MST 300 has two 시행일 among the later ones
    la = out["later_amendments"]
    assert la["count"] == 4 and la["effective_date_count"] == 5


def test_renamed_law_statement_shows_both_names(as_of):
    out = as_of(law_name="개명법", as_of="20050101", article=1)
    assert out["version"]["law_name"] == "옛개명법" and out["law"]["law_name"] == "개명법"
    assert "옛개명법(현행 명칭: 개명법)" in out["statement"]
    now = as_of(law_name="개명법", as_of="20150101", article=1)
    assert "현행 명칭" not in now["statement"]


def test_deleted_article_is_flagged_but_in_force(as_of):
    out = as_of(law_name=T, as_of="20200101", article=9)
    assert out["in_force"] is True and out["article_deleted"] is True
    assert out["article"]["deleted"] is True and "삭제" in out["statement"]
    normal = as_of(law_name=T, as_of="20200101", article=1)
    assert "article_deleted" not in normal
    assert is_deleted_article("제241조 삭제 <2016.1.6>") and is_deleted_article("제9조(간통) 삭제")
    assert not is_deleted_article("제9조(목적) 이 법은 삭제하지 않는다")


def test_bupchik_staged_enforcement_is_reported_with_quote(as_of):
    out = as_of(law_name=T, as_of="20181001", article=1)
    pe = out["partial_effect"]
    assert pe["possible"] is True and pe["article_scan"]["article_staged_enforcement_found"] is True
    match = pe["article_scan"]["matches"][0]
    assert match["later_dates"] == ["20190101", "20210101"] and "상시 300명 이상" in match["text"]
    assert any("부칙 원문" in c and "2019년 1월 1일" in c for c in out["caveats"])
    assert "단정할 수 없습니다" in out["statement"]
    # D after every date in the passage, other article, other law's article: no hit
    late = as_of(law_name=T, as_of="20210101", article=1)
    assert late["partial_effect"]["article_scan"]["article_staged_enforcement_found"] is False
    other = as_of(law_name=T, as_of="20181001", article=2)  # only "형법 제2조" is mentioned
    assert other["partial_effect"]["article_scan"]["article_staged_enforcement_found"] is False
    assert "단정할 수 없습니다" not in other["statement"]
    assert as_of(law_name=T, as_of="20210101", article=2)["partial_effect"]["possible"] is False
    assert any("조문별 개별 시행일은 따로 검증하지 않았습니다" in c for c in other["caveats"])


def test_bupchik_scan_failure_is_a_caveat_not_an_error(as_of, monkeypatch):
    real_get = FakeClient.get

    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == "/DRF/lawService.do" and not params.get("JO"):
            FakeClient.calls.append((endpoint, dict(params)))
            return {"status": "error", "error_code": "TIMEOUT", "message": "x", "request_id": "r"}
        return real_get(self, endpoint, params, response_type)

    monkeypatch.setattr(FakeClient, "get", get)
    out = as_of(law_name=T, as_of="20181001", article=1)
    assert out["status"] == "ok" and out["partial_effect"]["article_scan"]["checked"] is False
    assert any("부칙 전문을 조회하지 못해" in c for c in out["caveats"])


def test_scan_bupchik_unit_cases():
    unit = {"부칙공포일자": "20180320", "부칙공포번호": "15513", "부칙내용": [[
        "부칙 <제15513호,2018.3.20>",
        "제1조(시행일) 이 법은 공포한 날부터 시행한다. 다만, 제53조제3항의 개정규정은 2021년 7월 1일부터 시행한다.",
        "제2조(특례) 부칙 제53조는 2030년 1월 1일부터 시행한다.",
        "제3조 이 법 제55조의 개정규정은 2022년 1월 1일부터 시행한다.",
    ]]}
    hits = scan_bupchik([unit], 53, 0, "20200601")
    assert len(hits) == 1 and hits[0]["later_dates"] == ["20210701"]
    assert scan_bupchik([unit], 53, 0, "20210701") == []          # date no longer later than D
    assert scan_bupchik([unit], 53, 2, "20200601") == []          # 제53조의2 is another article
    assert len(scan_bupchik([unit], 55, 0, "20200601")) == 1
    assert scan_bupchik([unit], 5, 0, "20200601") == []           # 제5조 must not match 제53조
