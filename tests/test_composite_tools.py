"""Composite tools: relevance flags, precedent carry-through, sample statements, XML text,
glossary safety, dispute-prep dedupe, prompt article numbers (issue #31 and the composite-tools group)."""

import asyncio
import json

import pytest

import lexlink.citation as citation_mod
import lexlink.server as server_mod
from lexlink._helpers import matched_query_terms, query_terms
from lexlink.article_text import strip_html
from lexlink.cache import get_cache
from lexlink.linkage import gloss_problem

from test_amendment import FakeClient as AmendmentFakeClient

SEARCH = "/DRF/lawSearch.do"
SERVICE = "/DRF/lawService.do"

TAX = {"법령명": "법인세법 시행령", "법령ID": "003608", "조문번호": "0061", "조문제목": "대손충당금의 손금산입",
       "조문내용": "제61조(대손충당금의 손금산입) 채권의 범위는 외상매출금 및 대여금으로 한다."}
CAR = {"법령명": "자동차손해배상 보장법", "법령ID": "001746", "조문번호": "0024", "조문제목": "계약의 체결 의무",
       "조문내용": "제24조(계약의 체결 의무) 교통사고로 인한 손해배상책임 보험계약을 체결하여야 한다."}


def _prec_search(rows):
    return {"PrecSearch": {"totalCnt": str(len(rows)), "page": "1", "prec": rows}}


class GroupFake(AmendmentFakeClient):
    """Shared fake: aiSearch rows, precedent search by query, per-id precedent bodies, term links."""

    ai_rows: list = []
    prec_by_query: dict = {}      # query -> rows (searches whose query is not listed return none)
    prec_all_rows: list = []      # rows for every precedent search (overrides prec_by_query when set)
    prec_bodies: dict = {}        # id -> PrecService dict (JSON) ; default = amendment fixture
    xml_bodies: dict = {}         # id -> raw XML text served when type is XML
    term_links: dict = {}         # 법령용어 -> 일상용어 for lstrmRlt
    calls: list = []

    def get(self, endpoint, params, response_type="JSON"):
        target = params.get("target")
        GroupFake.calls.append((endpoint, target, dict(params)))
        if endpoint == SEARCH and target == "aiSearch":
            return self._ok(json.dumps({"aiSearch": {"법령조문": GroupFake.ai_rows}}, ensure_ascii=False))
        if endpoint == SEARCH and target == "prec" and (GroupFake.prec_all_rows or GroupFake.prec_by_query):
            rows = GroupFake.prec_all_rows or GroupFake.prec_by_query.get(params.get("query"), [])
            if response_type == "XML":
                items = "".join(
                    f'<prec id="{i + 1}">' + "".join(f"<{k}>{v}</{k}>" for k, v in row.items()) + "</prec>"
                    for i, row in enumerate(rows))
                xml = f'<?xml version="1.0" encoding="UTF-8"?><PrecSearch><totalCnt>{len(rows)}</totalCnt>{items}</PrecSearch>'
                return {"status": "ok", "request_id": "f", "upstream_type": "XML", "raw_content": xml}
            return self._ok(json.dumps(_prec_search(rows), ensure_ascii=False))
        if endpoint == SEARCH and target in ("decc", "detc", "ttSpecialDecc") and GroupFake.prec_all_rows:
            return self._ok(json.dumps({"X": {"totalCnt": "0"}}))
        if endpoint == SERVICE and target == "prec":
            pid = str(params.get("id") or params.get("ID"))
            if response_type == "XML" and pid in GroupFake.xml_bodies:
                return {"status": "ok", "request_id": "f", "upstream_type": "XML", "raw_content": GroupFake.xml_bodies[pid]}
            if pid in GroupFake.prec_bodies:
                return self._ok(json.dumps({"PrecService": GroupFake.prec_bodies[pid]}, ensure_ascii=False))
        if endpoint == SERVICE and target == "lstrmRlt":
            plain = GroupFake.term_links.get(params.get("query"))
            if plain:
                body = {"LsTrmRlt": {"법령용어": {"법령용어명": params["query"],
                                                 "연계용어": {"일상용어명": plain, "용어관계": "동의어"}}}}
                return self._ok(json.dumps(body, ensure_ascii=False))
            return self._ok(json.dumps({"LsTrmRlt": {}}))
        return super().get(endpoint, params, response_type)


@pytest.fixture(autouse=True)
def _fresh_state():
    get_cache().invalidate()
    GroupFake.ai_rows, GroupFake.prec_by_query, GroupFake.prec_all_rows = [], {}, []
    GroupFake.prec_bodies, GroupFake.xml_bodies, GroupFake.term_links, GroupFake.calls = {}, {}, {}, []
    yield
    get_cache().invalidate()


@pytest.fixture
def server(monkeypatch):
    async def no_cites(**kwargs):
        return {"success": True, "citations": []}

    monkeypatch.setattr(citation_mod, "extract_article_citations", no_cites)
    monkeypatch.setattr(server_mod, "LawAPIClient", GroupFake)
    monkeypatch.setenv("OC", "unit-test-oc")
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    asyncio.set_event_loop(asyncio.new_event_loop())
    return server_mod.create_server()


@pytest.fixture
def tools(server):
    return lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)


def _prec_calls():
    return [p["query"] for _, t, p in GroupFake.calls if t == "prec" and p.get("query")]


# ------------------------------------------------------------------ helpers

@pytest.mark.unit
def test_query_terms_strip_particles_and_ignore_filler():
    assert query_terms("집주인이 보증금을 안 돌려줘요") == ["집주인", "보증금", "돌려줘요"]
    assert query_terms("교통사고 합의금 과실비율") == ["교통사고", "합의금", "과실비율"]
    assert query_terms("ㅋㅋㅋㅋㅋ") == [] and query_terms("a 1 23") == []
    assert query_terms("관련 법률 경우") == []          # words in every statute prove nothing


@pytest.mark.unit
def test_matched_terms_are_literal_with_compound_halves():
    assert matched_query_terms(["공정이용"], "저작물의 공정한 이용") == ["공정이용"]
    assert matched_query_terms(["과실비율"], "대손충당금 설정 비율") == []
    assert matched_query_terms(["보증금"], "임대차 보증 금") == ["보증금"]   # spaces ignored
    assert matched_query_terms(["교통사고"], "") == []


# ------------------------------------------------------------------ 1. legal_resolver relevance

@pytest.mark.unit
def test_resolver_moves_irrelevant_law_back_and_flags_it(tools):
    GroupFake.ai_rows = [TAX, CAR]
    GroupFake.prec_by_query = {"자동차손해배상 보장법": [
        {"판례일련번호": "1", "사건명": "구상금", "사건번호": "2022다1", "선고일자": "2025.05.15", "법원명": "대법원"}]}
    out = tools("legal_resolver", situation="교통사고 합의금 과실비율")
    laws = out["applicable_laws"]
    assert [l["law_name"] for l in laws] == ["자동차손해배상 보장법", "법인세법 시행령"]
    assert [l["low_relevance"] for l in laws] == [False, True]
    assert [l["upstream_rank"] for l in laws] == [2, 1]
    assert laws[0]["matched_query_terms"] == ["교통사고"] and laws[1]["matched_query_terms"] == []
    assert any(w.startswith("low_relevance:") for w in out["warnings"])
    assert "low_relevance" not in out        # one relevant article remains
    assert out["query_terms_not_found"] == ["합의금", "과실비율"]   # words no returned article contains
    # no precedent lookup for the irrelevant law, provenance on each precedent
    assert _prec_calls() == ["자동차손해배상 보장법"]
    assert out["related_precedents"][0]["found_via_law"] == "자동차손해배상 보장법"


@pytest.mark.unit
def test_resolver_all_irrelevant_flags_result_and_skips_precedents(tools):
    GroupFake.ai_rows = [TAX]
    out = tools("legal_resolver", situation="교통사고 합의금 과실비율")
    assert out["low_relevance"] is True
    assert out["applicable_laws"][0]["low_relevance"] is True
    assert out["related_precedents"] == [] and _prec_calls() == []
    assert out["citations"] == []


@pytest.mark.unit
def test_resolver_uncheckable_query_is_flagged_not_trusted(tools):
    GroupFake.ai_rows = [CAR]
    out = tools("legal_resolver", situation="ㅋㅋㅋㅋ")
    assert out["low_relevance"] is True and out["applicable_laws"][0]["low_relevance"] is True


# ------------------------------------------------------------------ 2. chain_full_research carries precedents

@pytest.mark.unit
def test_chain_full_research_carries_related_precedents(tools):
    GroupFake.ai_rows = [CAR]
    rows = [{"판례일련번호": "7", "사건명": "구상금", "사건번호": "2022다7", "선고일자": "2025.05.15", "법원명": "대법원"}]
    GroupFake.prec_by_query = {"자동차손해배상 보장법": rows}   # the colloquial query itself finds nothing
    out = tools("chain_full_research", query="교통사고 합의금 과실비율")
    assert out["precedent_analysis"]["total_found"] == 0
    assert [p["id"] for p in out["related_precedents"]] == ["7"]
    assert out["related_precedents"][0]["found_via_law"] == "자동차손해배상 보장법"


@pytest.mark.unit
def test_chain_full_research_passes_relevance_flags_and_sample(tools):
    GroupFake.ai_rows = [TAX]
    out = tools("chain_full_research", query="교통사고 합의금 과실비율")
    assert out["low_relevance"] is True
    assert out["applicable_laws"][0]["low_relevance"] is True
    assert any(w.startswith("low_relevance:") for w in out["warnings"])
    assert "sample" in out["precedent_analysis"]


# ------------------------------------------------------------------ 3. check_precedent_odds relevance + sample

COPY_BODY = {"사건명": "x", "판시사항": "[1] 저작물의 공정한 이용에 해당하는지 여부", "판결요지": "원심판결을 파기환송한다.",
             "판례내용": "【주    문】<br/>원심판결을 파기하고, 사건을 서울고등법원에 환송한다.<br/>【이    유】<br/>저작물"}
DRUNK_BODY = {"사건명": "x", "판시사항": "[1] 음주운전 처벌", "판결요지": "음주운전",
              "판례내용": "【주    문】<br/>상고를 기각한다.<br/>【이    유】<br/>음주운전"}


def _two_cases():
    GroupFake.prec_all_rows = [
        {"판례일련번호": "1", "사건명": "저작권침해", "사건번호": "2021다1", "선고일자": "2025.09.18", "법원명": "대법원"},
        {"판례일련번호": "2", "사건명": "도로교통법위반", "사건번호": "2021도2", "선고일자": "2025.09.19", "법원명": "대법원"},
    ]
    GroupFake.prec_bodies = {"1": COPY_BODY, "2": DRUNK_BODY}


@pytest.mark.unit
def test_odds_excludes_irrelevant_cases_and_states_the_sample(tools):
    _two_cases()
    out = tools("check_precedent_odds", query="저작물 공정한 이용", top_n=5)
    cases = {c["case_number"]: c for c in out["representative_cases"]}
    assert cases["2021다1"]["low_relevance"] is False and cases["2021다1"]["matched_query_terms"]
    assert cases["2021도2"]["low_relevance"] is True and cases["2021도2"]["matched_query_terms"] == []
    assert out["outcome_summary"] == {"파기환송": 1}        # the unrelated 상고기각 is not counted
    sample = out["sample"]
    assert sample["analyzed"] == 2 and sample["counted_in_outcome_summary"] == 1
    assert sample["excluded_low_relevance"] == 1 and "무작위·전수 표본이 아닙니다" in sample["selection"]
    assert "승소 확률도 아닙니다" in out["statistics_note"] and "표본 1건" in out["statistics_note"]
    assert any(w.startswith("low_relevance:") for w in out["warnings"])
    assert "low_relevance" not in out


@pytest.mark.unit
def test_odds_title_matches_are_analyzed_first(tools):
    _two_cases()
    GroupFake.prec_all_rows.reverse()   # unrelated case listed first upstream
    out = tools("check_precedent_odds", query="저작권침해", top_n=1)
    assert [c["case_number"] for c in out["representative_cases"]] == ["2021다1"]


@pytest.mark.unit
@pytest.mark.parametrize("query", ["ㅋㅋㅋㅋㅋ", "부동산 경매 배당"])
def test_odds_gibberish_or_unrelated_query_gives_no_statistics(tools, query):
    _two_cases()
    out = tools("check_precedent_odds", query=query)
    assert out["low_relevance"] is True
    assert out["outcome_summary"] == {} and out["key_factors"] == []
    assert out["representative_cases"] and all(c["low_relevance"] for c in out["representative_cases"])
    assert out["warnings"][0].startswith("low_relevance:")
    assert out["sample"]["counted_in_outcome_summary"] == 0


@pytest.mark.unit
def test_odds_output_never_offers_a_percentage_or_probability(tools):
    _two_cases()
    text = json.dumps(tools("check_precedent_odds", query="저작물 공정한 이용"), ensure_ascii=False)
    assert "%" not in text.replace("%s", "") and "확률" in text and "승소 확률도 아닙니다" in text


# ------------------------------------------------------------------ 4. issue #31 XML CDATA

XML_BODY = (
    '<?xml version="1.0" encoding="UTF-8"?><PrecService>'
    "<판시사항><![CDATA[[1] 저작물의 공정한 이용에 해당하는지 여부<br/>[2] 손해배상 범위]]></판시사항>"
    "<판결요지><![CDATA[공정한 이용은 인정되지 않는다.<br/>원심판결을 파기환송한다.]]></판결요지>"
    "<판례내용><![CDATA[【주    문】<br/>원심판결을 파기하고, 사건을 서울고등법원에 환송한다.<br/>【이    유】<br/>저작물]]></판례내용>"
    "</PrecService>"
)


@pytest.mark.unit
def test_strip_html_unwraps_cdata():
    assert strip_html("<![CDATA[가<br/>나]]>") == "가\n나"
    assert strip_html("<![CDATA[]]>") == ""


@pytest.mark.unit
def test_odds_xml_keeps_holding_summary_and_key_factors(tools):
    GroupFake.prec_all_rows = [
        {"판례일련번호": "1", "사건명": "저작권침해", "사건번호": "2021다1", "선고일자": "2025.09.18", "법원명": "대법원"}]
    GroupFake.xml_bodies = {"1": XML_BODY}
    out = tools("check_precedent_odds", query="저작물 공정한 이용", type="XML")
    case = out["representative_cases"][0]
    assert "CDATA" not in json.dumps(out, ensure_ascii=False) and "<br" not in case["holding"]
    assert case["holding"].startswith("[1] 저작물의 공정한 이용")
    assert "원심판결을 파기환송한다" in case["summary"]
    assert out["key_factors"], out
    assert case["outcome"] == "파기환송"


# ------------------------------------------------------------------ 5. simplify_article glossary

@pytest.mark.unit
def test_gloss_problem_rules():
    assert gloss_problem("손해배상", "손배")                    # abbreviation
    assert gloss_problem("사용자", "경영자") and gloss_problem("채권자", "채급자")
    assert gloss_problem("임차인", "세입자") == ""
    assert gloss_problem("임차인", "") == ""


@pytest.mark.unit
def test_simplify_article_drops_unsafe_links_and_flags_the_rest(server, monkeypatch):
    monkeypatch.setattr(server_mod, "extract_legal_terms", lambda text: ["임차인", "사용자", "손해배상", "채무자"])
    GroupFake.term_links = {"임차인": "세입자", "사용자": "경영자", "손해배상": "손배", "채무자": "부채자"}
    out = server._tool_manager.get_tool("simplify_article").fn(law_name="저작권법", article=35, article_branch=5)
    assert out["text_simplified"] is False and out["simplified_text"] == out["original_text"]
    by_term = {g["term"]: g for g in out["term_glossary"]}
    assert by_term["임차인"]["plain_korean"] == "세입자" and by_term["임차인"]["verified"] is False
    for term in ("사용자", "손해배상", "채무자"):
        assert by_term[term]["plain_korean"] == "" and by_term[term]["source"] == "dropped"
    assert {d["term"] for d in out["terms_dropped"]} == {"사용자", "손해배상", "채무자"}
    assert out["terms_mapped"] == 1 and "text_simplified: false" in out["note"]
    # only the 법령용어 -> 일상용어 direction is read; the reverse lookup is gone
    assert not [c for c in GroupFake.calls if c[1] == "dlytrmRlt"]
    assert len([c for c in GroupFake.calls if c[1] == "lstrmRlt"]) == 4


@pytest.mark.unit
def test_simplify_article_description_says_text_is_not_simplified(server):
    tool = server._tool_manager.get_tool("simplify_article")
    assert "NOT simplified" in tool.description and "verified" in tool.description
    assert "NOT simplified" in server._mcp_server.instructions


# ------------------------------------------------------------------ 6. chain_dispute_prep

@pytest.mark.unit
def test_chain_dispute_prep_dedupes_and_describes_itself(server, tools):
    GroupFake.prec_all_rows = [
        {"판례일련번호": "1", "사건명": "과징금부과처분취소", "사건번호": "2024구합70753", "선고일자": "2025.08.14", "법원명": "서울행정법원"},
        {"판례일련번호": "2", "사건명": "과징금부과처분취소", "사건번호": "2024구합70753", "선고일자": "2025.08.14", "법원명": "서울행정법원"},
        {"판례일련번호": "3", "사건명": "과징금부과처분취소", "사건번호": "2024구합70753", "선고일자": "2025.08.14", "법원명": "부산지방법원"},
        {"판례일련번호": "4", "사건명": "손해배상", "사건번호": "2024다1", "선고일자": "2025.01.01", "법원명": "대법원"},
    ]
    out = tools("chain_dispute_prep", query="과징금", display=10)
    assert [r["판례일련번호"] for r in out["precedents"]] == ["1", "3", "4"]
    assert out["search_modes"]["precedents"]["duplicates_removed"] == 1
    assert [r["title_matches_query"] for r in out["precedents"]] == [True, True, False]
    assert out["total_results"] == 3
    assert "메타데이터" in out["content_note"] and "prec_service" in out["content_note"]
    assert any(w.startswith("low_relevance:") for w in out["warnings"])
    desc = server._tool_manager.get_tool("chain_dispute_prep").description
    assert "metadata only" in desc and "no holdings" in desc


# ------------------------------------------------------------------ 8. prompt article numbers

def _prompt_text(server, name, **args):
    result = asyncio.run(server.get_prompt(name, args))
    return result.messages[0].content.text


@pytest.mark.unit
@pytest.mark.parametrize("value,jo,label", [
    (20, "002000", "제20조"), ("20", "002000", "제20조"), ("35의5", "003505", "제35조의5"),
    ("제35조의5", "003505", "제35조의5"), ("35-5", "003505", "제35조의5"),
])
def test_get_law_article_prompt_accepts_jo_forms(server, value, jo, label):
    text = _prompt_text(server, "get-law-article", law_id="000001", article_number=value)
    assert f"jo parameter '{jo}'" in text and label in text


@pytest.mark.unit
def test_get_article_with_citations_prompt_carries_branch(server):
    text = _prompt_text(server, "get-article-with-citations", law_name="저작권법", article_number="35의5")
    assert '"003505"' in text and "제35조의5" in text
    assert "article: 35, article_branch: 5" in text
    plain = _prompt_text(server, "get-article-with-citations", law_name="건축법", article_number=3)
    assert "article: 3, article_branch: 0" in plain and '"000300"' in plain


@pytest.mark.unit
def test_analyze_law_citations_prompt_accepts_branch_articles(server):
    text = _prompt_text(server, "analyze-law-citations", law_name="저작권법", articles="35의5, 3")
    assert "제35조의5 (article=35, article_branch=5)" in text and "제3조 (article=3, article_branch=0)" in text


@pytest.mark.unit
def test_prompt_rejects_unrecognizable_article(server):
    with pytest.raises(Exception):
        _prompt_text(server, "get-law-article", law_id="000001", article_number="abc")
