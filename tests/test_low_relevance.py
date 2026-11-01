"""Low-relevance warning for aiSearch / legal_resolver / chain_full_research (issue #15)."""

import asyncio
import json

import pytest

import lexlink.citation as citation_mod
import lexlink.server as server_mod
from lexlink._helpers import (
    LOW_RELEVANCE_WARNING, RELEVANCE_UNCHECKABLE_WARNING, low_relevance_warning,
)
from lexlink.cache import get_cache

from test_amendment import FakeClient as AmendmentFakeClient

FAKE_OC = "unit-test-oc"
SEARCH = "/DRF/lawSearch.do"

PLEDGE = {"법령명": "민법", "법령ID": "001706", "조문번호": "0329", "조문제목": "동산질권의 내용",
          "조문내용": "제329조(동산질권의 내용) 동산질권자는 채권의 담보로 채무자가 제공한 동산을 점유한다."}
DEPOSIT = {"법령명": "주택임대차보호법", "법령ID": "001234", "조문번호": "0003", "조문제목": "대항력 등",
           "조문내용": "제3조(대항력 등) 임대차보증금의 반환을 청구할 수 있다."}
COPYRIGHT = {"법령명": "저작권법", "법령ID": "000798", "조문번호": "35", "조문제목": "공정이용",
             "조문내용": "저작물의 이용"}  # law known to the shared amendment fake


def _ai_body(rows):
    return json.dumps({"aiSearch": {"법령조문": rows}}, ensure_ascii=False)


class RelevanceFake(AmendmentFakeClient):
    rows = [PLEDGE]

    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == SEARCH and params.get("target") == "aiSearch":
            return self._ok(_ai_body(RelevanceFake.rows))
        return super().get(endpoint, params, response_type)


@pytest.fixture(autouse=True)
def _fresh_cache():
    get_cache().invalidate()
    yield
    get_cache().invalidate()


@pytest.fixture
def tools(monkeypatch):
    async def no_cites(**kwargs):
        return {"success": True, "citations": []}

    monkeypatch.setattr(citation_mod, "extract_article_citations", no_cites)
    monkeypatch.setattr(server_mod, "LawAPIClient", RelevanceFake)
    monkeypatch.setenv("OC", FAKE_OC)
    RelevanceFake.rows = [PLEDGE]
    server = server_mod.create_server()
    return lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)


@pytest.mark.unit
def test_helper_flags_only_zero_overlap():
    assert low_relevance_warning("asdfqwer zxcv", [PLEDGE]) == LOW_RELEVANCE_WARNING
    assert low_relevance_warning("ㅋㅋㅋㅋㅋㅋ", [PLEDGE]) == LOW_RELEVANCE_WARNING
    assert low_relevance_warning("동산 질권", [PLEDGE]) is None
    assert low_relevance_warning("보증금 반환", [DEPOSIT, PLEDGE]) is None
    # digits alone are not evidence (they match dates and article numbers)
    assert low_relevance_warning("qqqqwwww 329", [PLEDGE]) == LOW_RELEVANCE_WARNING
    # nothing to judge -> no warning
    assert low_relevance_warning("", [PLEDGE]) == RELEVANCE_UNCHECKABLE_WARNING
    assert low_relevance_warning("zzxxcc", []) is None


@pytest.mark.unit
def test_metadata_fields_and_single_chars_do_not_count_as_overlap():
    row = dict(PLEDGE, 제개정구분명="일부개정", 소관부처명="재정경제부", 시행일자="20260320", rank="1")
    for q in ("asdfqwer zxcv 개정", "asdfqwer zxcv 재정", "asdfqwer zxcv 시행", "asdfqwer zxcv 이"):
        assert low_relevance_warning(q, [row]) == LOW_RELEVANCE_WARNING, q
    # no usable grams -> honest "cannot check" message, not a guess
    for q in ("x", "이 뭐 야", "123"):
        assert low_relevance_warning(q, [row]) == RELEVANCE_UNCHECKABLE_WARNING, q
    # rows without content fields (appendix searches) are not judged
    assert low_relevance_warning("asdf", [{"별표명": "x"}]) is None


@pytest.mark.unit
def test_warning_is_soft_and_documents_false_positives():
    assert LOW_RELEVANCE_WARNING.startswith("relevance_unverified")
    assert "구어체" in LOW_RELEVANCE_WARNING and "직접 확인" in LOW_RELEVANCE_WARNING


@pytest.mark.unit
def test_aisearch_correct_result_for_abbreviation_still_returns_data(tools):
    RelevanceFake.rows = [{"법령명": "근로기준법", "조문제목": "정의", "조문내용": "제2조 정의"}]
    out = tools("aiSearch", query="근기법")
    assert out["status"] == "ok" and out["ranked_data"]  # data kept even if warned


@pytest.mark.unit
def test_aisearch_gibberish_warns_but_keeps_data(tools):
    out = tools("aiSearch", query="asdfqwer zxcv")
    assert out["status"] == "ok"
    assert LOW_RELEVANCE_WARNING in out["warnings"]
    assert out["ranked_data"]


@pytest.mark.unit
def test_aisearch_real_query_has_no_warning(tools):
    RelevanceFake.rows = [DEPOSIT]
    out = tools("aiSearch", query="보증금 안 돌려줘요")
    assert "warnings" not in out


@pytest.mark.unit
def test_legal_resolver_gibberish_warns_but_keeps_laws(tools):
    out = tools("legal_resolver", situation="asdfqwer zxcv")
    assert out["status"] == "ok"
    assert LOW_RELEVANCE_WARNING in out["warnings"]
    assert out["applicable_laws"][0]["law_name"] == "민법"


@pytest.mark.unit
def test_legal_resolver_real_query_has_no_warning(tools):
    RelevanceFake.rows = [DEPOSIT]
    out = tools("legal_resolver", situation="집주인이 보증금을 안 돌려줘요")
    assert LOW_RELEVANCE_WARNING not in (out.get("warnings") or [])


@pytest.mark.unit
def test_chain_full_research_gibberish_carries_warning(tools):
    out = tools("chain_full_research", query="asdfqwer zxcv")
    assert out["status"] == "ok"
    assert LOW_RELEVANCE_WARNING in out["warnings"]


@pytest.mark.unit
def test_legal_resolver_citations_in_running_loop_and_in_process(monkeypatch, tools):
    """Issue #20 regression: citations are filled both in-process and under a live loop."""
    async def cites(**kwargs):
        return {"success": True, "citations": [
            {"type": "external", "target_law_name": "민법", "target_article": 3}]}

    monkeypatch.setattr(citation_mod, "extract_article_citations", cites)
    RelevanceFake.rows = [COPYRIGHT]
    sync_out = tools("legal_resolver", situation="저작물 이용")
    assert [c["to_law"] for c in sync_out["citations"]] == ["민법"]

    async def run():
        return tools("legal_resolver", situation="저작물 이용")

    loop_out = asyncio.run(run())
    assert [c["to_law"] for c in loop_out["citations"]] == ["민법"]
    assert "warnings" not in loop_out


# ---- word-start matching and odds counting (integration review M1/M2, real strings) ----

def test_term_must_start_a_word_not_sit_inside_one():
    from lexlink._helpers import matched_query_terms, query_terms
    terms = query_terms("남편 외도")
    assert matched_query_terms(terms, "특정경제범죄가중처벌등에관한법률위반 재산국외도피") == []
    assert "외도" in matched_query_terms(terms, "배우자의 외도로 인한 위자료")
    # the forms that must keep matching
    assert matched_query_terms(["양육권"], "양육비 청구") == ["양육권"]
    assert matched_query_terms(["이혼"], "이혼하고 싶다") == ["이혼"]
    assert matched_query_terms(["퇴직금"], "퇴직급여 지급") == ["퇴직금"]
    assert matched_query_terms(["공정이용"], "공정한 이용") == ["공정이용"]


def test_criminal_case_numbers():
    from lexlink._helpers import is_criminal_case_number
    assert is_criminal_case_number("2012도14788") and is_criminal_case_number("2024고합143")
    assert not is_criminal_case_number("2024므15467") and not is_criminal_case_number("2018스5")


def test_odds_needs_strong_term_in_name_or_holding_for_multi_term_query():
    from lexlink._helpers import counts_for_odds, query_terms, matched_query_terms
    terms = query_terms("아이 양육권")
    # 미성년자입양허가: 양육권 only in the 판결요지
    head = matched_query_terms(terms, "미성년자입양허가", "입양 허가 요건")
    full = matched_query_terms(terms, "미성년자입양허가", "입양 허가 요건", "양육권 포기")
    assert head == [] and not counts_for_odds(terms, full, head)
    head = matched_query_terms(terms, "이혼 및 친권자·양육자 지정", "양육권 귀속")
    assert counts_for_odds(terms, head, head)
    # a single-term query keeps the old rule (any of the three fields)
    one = query_terms("위자료")
    assert counts_for_odds(one, ["위자료"], [])


def test_nb_four_digit_pre_2000_year_gets_the_two_digit_hint():
    from lexlink import guards
    empty = {"status": "ok", "ranked_data": {"키워드": "", "totalCnt": "0", "target": "prec"}}
    hint = guards.nb_year_form_hint("1994므1713", empty)
    assert hint and "nb_year_form" in hint and "'94므1713'" in hint
    found = {"status": "ok", "ranked_data": {"prec": [{"사건번호": "94므1713"}], "totalCnt": "1"}}
    assert guards.nb_year_form_hint("1994므1713", found) is None
    assert guards.nb_year_form_hint("2013므3963", empty) is None
    assert guards.nb_year_form_hint("94므1713", empty) is None
