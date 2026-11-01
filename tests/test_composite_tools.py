"""Composite tools: relevance flags, precedent carry-through, sample statements, XML text,
glossary safety, dispute-prep dedupe, prompt article numbers (issue #31 and the composite-tools group)."""

import asyncio
import json

import pytest

import lexlink.citation as citation_mod
import lexlink.server as server_mod
from lexlink._helpers import counts_as_overlap, distinctive_terms, matched_query_terms, query_terms
from lexlink.article_text import strip_html
from lexlink.cache import get_cache

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




def _prec_row(pid, name, no, court="대법원"):
    return {"판례일련번호": pid, "사건명": name, "사건번호": no, "선고일자": "2025.05.15", "법원명": court}


# ------------------------------------------------------------------ term matching (real queries)

@pytest.mark.unit
def test_query_terms_cut_verb_endings_and_particles():
    assert query_terms("남편이 외도를 해서 이혼하고 싶어요") == ["남편", "외도", "이혼"]
    assert query_terms("아이 양육권") == ["아이", "양육권"]
    assert query_terms("집주인이 보증금을 안 돌려줘요") == ["집주인", "보증금"]
    assert query_terms("교통사고 합의금 과실비율") == ["교통사고", "합의금", "과실비율"]
    assert query_terms("ㅋㅋㅋㅋㅋ") == [] and query_terms("a 1 23") == []
    assert query_terms("관련 법률 경우") == []          # words in every statute prove nothing


@pytest.mark.unit
def test_matching_uses_stems_both_ways_and_aliases():
    assert matched_query_terms(["양육권"], "양육에 관한 사항") == ["양육권"]
    assert matched_query_terms(["퇴직금"], "퇴직급여 제도") == ["퇴직금"]
    assert matched_query_terms(["이혼"], "재판상 이혼의 원인") == ["이혼"]
    assert matched_query_terms(["공정이용"], "저작물의 공정한 이용") == ["공정이용"]
    assert matched_query_terms(["집주인"], "임대인은 보증금을") == ["집주인"]
    assert matched_query_terms(["과실비율"], "대손충당금 설정 비율") == []
    assert matched_query_terms(["보증금"], "임대차 보증 금") == ["보증금"]   # spaces ignored
    assert matched_query_terms(["교통사고"], "") == []


@pytest.mark.unit
def test_generic_terms_alone_do_not_count():
    terms = query_terms("집주인이 보증금을 안 돌려줘요")
    assert distinctive_terms(terms) == ["집주인"]
    assert not counts_as_overlap(terms, ["보증금"]) and counts_as_overlap(terms, ["집주인"])
    # a query made only of generic words compares on all of them
    assert distinctive_terms(["손해배상", "청구"]) == ["손해배상", "청구"]
    # 재산분할 is not the generic word 재산
    assert distinctive_terms(query_terms("이혼 재산분할")) == ["이혼", "재산분할"]


# ------------------------------------------------------------------ 1. legal_resolver: advisory flag only

CHILD = [
    {"법령명": "민법", "법령ID": "001706", "조문번호": "0837", "조문제목": "이혼과 자의 양육책임",
     "조문내용": "제837조(이혼과 자의 양육책임) 당사자는 그 자의 양육에 관한 사항을 협의로 정한다."},
    {"법령명": "민법", "법령ID": "001706", "조문번호": "0864", "조문제목": "인지",
     "조문내용": "제864조 부 또는 모의 양육권 ..."},
    {"법령명": "민법", "법령ID": "001706", "조문번호": "0909", "조문제목": "친권자",
     "조문내용": "제909조(친권자) 부모는 미성년자인 자의 친권자가 된다. 양육"},
]


@pytest.mark.unit
def test_resolver_keeps_upstream_order_and_looks_up_everything_for_양육권(tools, monkeypatch):
    seen = []

    async def cites(**kwargs):
        seen.append(kwargs["law_name"])
        return {"success": True, "citations": [{"target_law_name": "가사소송법", "target_article": "2", "type": "external"}]}

    monkeypatch.setattr(citation_mod, "extract_article_citations", cites)
    GroupFake.ai_rows = [dict(r, 법령명="저작권법") for r in CHILD]   # 저작권법 resolves to an MST in the fake
    GroupFake.prec_by_query = {"아이 양육권": [_prec_row("11", "양육권자변경", "2023스1")]}
    out = tools("legal_resolver", situation="아이 양육권")
    assert [l["upstream_rank"] for l in out["applicable_laws"]] == [1, 2, 3]
    assert all(not l["low_relevance"] for l in out["applicable_laws"])     # 양육권 ~ 양육
    assert "low_relevance" not in out
    assert seen == ["저작권법"] and out["citations"]                       # citations run on the top result
    prec = out["related_precedents"][0]
    assert prec["search_basis"] == "situation_terms" and prec["matched_query_terms"] == ["양육권"]
    assert "relevance_unverified" not in prec
    assert _prec_calls()[0] == "아이 양육권"


@pytest.mark.unit
def test_resolver_retries_the_case_name_search_with_the_stem_of_the_longest_word(tools):
    GroupFake.ai_rows = [CHILD[0]]
    GroupFake.prec_by_query = {"양육": [_prec_row("5", "양육비", "2019스621"), _prec_row("6", "이혼및양육자지정", "2020므1")]}
    out = tools("legal_resolver", situation="아이 양육권")
    assert _prec_calls()[:2] == ["아이 양육권", "양육"]
    precs = out["related_precedents"]
    assert [p["case_number"] for p in precs] == ["2019스621", "2020므1"]
    assert all(p["search_basis"] == "situation_terms" and "relevance_unverified" not in p for p in precs)
    assert not any(w.startswith("relevance_unverified:") for w in out.get("warnings", []))


@pytest.mark.unit
def test_resolver_does_not_push_840_behind_836(tools):
    GroupFake.ai_rows = [
        {"법령명": "민법", "법령ID": "1", "조문번호": "0836", "조문제목": "이혼의 성립과 신고방식",
         "조문내용": "제836조 협의상 이혼은 가정법원의 확인을 받아"},
        {"법령명": "민법", "법령ID": "1", "조문번호": "0840", "조문제목": "재판상 이혼원인",
         "조문내용": "제840조 부부의 일방은 다음 각호의 사유가 있는 경우에는 가정법원에 이혼을 청구할 수 있다. 배우자에 부정한 행위"},
    ]
    out = tools("legal_resolver", situation="남편이 외도를 해서 이혼하고 싶어요")
    assert [l["article"] for l in out["applicable_laws"]] == ["0836", "0840"]
    assert "이혼" in out["applicable_laws"][1]["matched_query_terms"]
    assert not any(l["low_relevance"] for l in out["applicable_laws"])
    assert "query_terms_not_found" in out
    assert not {"해서", "싶어요", "이혼하고"} & set(out["query_terms_not_found"])


@pytest.mark.unit
def test_resolver_flags_without_reordering_or_skipping_lookups(tools, monkeypatch):
    seen = []

    async def cites(**kwargs):
        seen.append(kwargs["law_name"])
        return {"success": True, "citations": []}

    monkeypatch.setattr(citation_mod, "extract_article_citations", cites)
    GroupFake.ai_rows = [dict(TAX, 법령명="저작권법", 조문번호="0035"), CAR]
    out = tools("legal_resolver", situation="교통사고 합의금 과실비율")
    laws = out["applicable_laws"]
    assert [l["upstream_rank"] for l in laws] == [1, 2]                 # order is the upstream order
    assert [l["low_relevance"] for l in laws] == [True, False]
    assert any(w.startswith("low_relevance:") and "관련성 판단이 아니며" in w for w in out["warnings"])
    assert "low_relevance" not in out and out["relevance_basis"].startswith("term_overlap")
    assert seen == ["저작권법"]                                          # top result keeps its citation lookup
    assert out["query_terms_not_found"] == ["합의금", "과실비율"]


@pytest.mark.unit
def test_resolver_all_flagged_sets_result_flag_but_keeps_everything(tools):
    GroupFake.ai_rows = [TAX]
    out = tools("legal_resolver", situation="교통사고 합의금 과실비율")
    assert out["low_relevance"] is True and out["applicable_laws"][0]["low_relevance"] is True
    assert out["applicable_laws"][0]["article"] == "0061"


@pytest.mark.unit
def test_resolver_law_name_precedents_are_labelled_unverified_and_deduped(tools):
    GroupFake.ai_rows = [dict(CAR, 법령명="가사소송법")]
    GroupFake.prec_by_query = {   # the term search finds nothing; the bare law name finds an unrelated case twice
        "가사소송법": [_prec_row("1", "국세환급금양도", "2024노3424"), _prec_row("2", "국세환급금양도", "2024노3424"),
                    _prec_row("3", "양육비", "2023스9")],
    }
    out = tools("legal_resolver", situation="남편이 외도를 해서 이혼하고 싶어요")
    precs = {p["case_number"]: p for p in out["related_precedents"]}
    assert list(precs) == ["2024노3424", "2023스9"]                      # same 사건번호 once
    assert precs["2024노3424"]["relevance_unverified"] is True and precs["2024노3424"]["search_basis"] == "law_name"
    assert precs["2023스9"]["relevance_unverified"] is True              # 양육비 shares no word with 남편/외도/이혼
    assert any(w.startswith("relevance_unverified:") for w in out["warnings"])
    assert _prec_calls()[0] == "남편 외도 이혼"                            # situation terms first


# ------------------------------------------------------------------ 2. chain_full_research

@pytest.mark.unit
def test_chain_full_research_carries_related_precedents_and_counts_calls(tools):
    GroupFake.ai_rows = [dict(CAR, 법령명="자동차손해배상 보장법")]
    GroupFake.prec_by_query = {"자동차손해배상 보장법": [_prec_row("7", "구상금", "2022다7")]}
    out = tools("chain_full_research", query="교통사고 합의금 과실비율")
    assert [p["id"] for p in out["related_precedents"]] == ["7"]
    assert out["precedent_analysis"]["total_found"] == 0
    assert "sample" in out["precedent_analysis"]
    requests = [c for c in GroupFake.calls if c[0] in (SEARCH, SERVICE)]
    assert out["api_calls_made"] == len(requests)        # every request, odds searches included


@pytest.mark.unit
def test_chain_full_research_passes_flags(tools):
    GroupFake.ai_rows = [TAX]
    out = tools("chain_full_research", query="교통사고 합의금 과실비율")
    assert out["low_relevance"] is True and out["applicable_laws"][0]["low_relevance"] is True
    assert any(w.startswith("low_relevance:") for w in out["warnings"])


# ------------------------------------------------------------------ 3. check_precedent_odds

DIVORCE_BODY = {"사건명": "x", "판시사항": "[1] 이혼에 따른 위자료 청구", "판결요지": "위자료를 지급하라",
                "판례내용": "【주    문】<br/>원심판결을 파기하고, 사건을 서울고등법원에 환송한다.<br/>【이    유】<br/>이혼 위자료"}
MURDER_BODY = {"사건명": "x", "판시사항": "[1] 살인죄의 고의", "판결요지": "살인",
               "판례내용": "【주    문】<br/>상고를 기각한다.<br/>【이    유】<br/>피고인은 이혼 위자료 문제로 다투었다"}


def _mixed_cases():
    GroupFake.prec_all_rows = [
        _prec_row("1", "이혼및위자료", "2021므1"),
        _prec_row("2", "살인", "2021도2"),
        _prec_row("3", "공직선거법위반", "2021도3"),
    ]
    GroupFake.prec_bodies = {"1": DIVORCE_BODY, "2": MURDER_BODY, "3": MURDER_BODY}


@pytest.mark.unit
def test_odds_counts_only_cases_with_a_distinctive_word_in_name_or_holding(tools):
    _mixed_cases()    # the 본문 of the 살인 case contains 이혼 위자료 (as every 본문-search hit would)
    out = tools("check_precedent_odds", query="이혼 위자료")
    assert [c["case_number"] for c in out["representative_cases"]] == ["2021므1"]
    assert out["outcome_summary"] == {"파기환송": 1}
    assert sorted(c["case_number"] for c in out["uncounted_cases"]) == ["2021도2", "2021도3"]
    assert all("outcome" not in c and c["low_relevance"] for c in out["uncounted_cases"])
    sample = out["sample"]
    assert sample["counted_in_outcome_summary"] == 1 and sample["uncounted"] == 2 and sample["small_sample"] is True
    assert any(w.startswith("small_sample:") for w in out["warnings"])
    assert any(w.startswith("low_relevance:") for w in out["warnings"])
    assert "승소 확률도 아닙니다" in out["statistics_note"]


@pytest.mark.unit
def test_odds_title_matches_are_analyzed_first_and_fetches_are_capped(tools):
    GroupFake.prec_all_rows = [_prec_row(str(i), f"무관한사건{i}", f"2021도{i}") for i in range(1, 15)]
    GroupFake.prec_all_rows.append(_prec_row("99", "이혼및위자료", "2021므99"))
    GroupFake.prec_bodies = {"99": DIVORCE_BODY}
    out = tools("check_precedent_odds", query="이혼 위자료", top_n=5)
    assert [c["case_number"] for c in out["representative_cases"]] == ["2021므99"]   # title match fetched first
    fetches = [c for c in GroupFake.calls if c[0] == SERVICE and c[1] == "prec"]
    assert len(fetches) <= 5 + 4
    assert out["api_calls_made"] == len([c for c in GroupFake.calls if c[0] == SEARCH and c[1] == "prec"]) + len(fetches)


@pytest.mark.unit
@pytest.mark.parametrize("query", ["ㅋㅋㅋㅋㅋ", "부동산 경매 배당"])
def test_odds_gibberish_or_unrelated_query_shows_no_representative_cases(tools, query):
    _mixed_cases()
    out = tools("check_precedent_odds", query=query)
    assert out["low_relevance"] is True
    assert out["outcome_summary"] == {} and out["key_factors"] == []
    assert out["representative_cases"] == [] and out["uncounted_cases"]
    assert out["warnings"][0].startswith("low_relevance:")


@pytest.mark.unit
def test_odds_html_is_fetched_as_json_and_all_unclear_is_warned(tools):
    _mixed_cases()
    out = tools("check_precedent_odds", query="이혼 위자료", type="HTML")
    assert out["outcome_summary"] == {"파기환송": 1}                       # HTML request still parsed
    assert {c[2].get("type") for c in GroupFake.calls if c[0] == SERVICE and c[1] == "prec"} == {"JSON"}
    GroupFake.prec_bodies["1"] = dict(DIVORCE_BODY, 판례내용="주문 섹션 없음")
    get_cache().invalidate()
    out = tools("check_precedent_odds", query="이혼 위자료")
    assert out["outcome_summary"] == {"불명": 1}
    assert any(w.startswith("outcome_unclear:") for w in out["warnings"])


@pytest.mark.unit
def test_odds_output_never_offers_a_percentage_or_probability(tools):
    _mixed_cases()
    text = json.dumps(tools("check_precedent_odds", query="이혼 위자료"), ensure_ascii=False)
    assert "%" not in text and "승소 확률도 아닙니다" in text


# ------------------------------------------------------------------ 4. issue #31 XML CDATA + strip_html

XML_BODY = (
    '<?xml version="1.0" encoding="UTF-8"?><PrecService>'
    "<판시사항><![CDATA[[1] 이혼에 따른 위자료 청구가 인정되는지 여부<br/>[2] 손해배상 범위]]></판시사항>"
    "<판결요지><![CDATA[위자료는 인정되지 않는다.<br/>원심판결을 파기환송한다.]]></판결요지>"
    "<판례내용><![CDATA[【주    문】<br/>원심판결을 파기하고, 사건을 서울고등법원에 환송한다.<br/>【이    유】<br/>위자료]]></판례내용>"
    "</PrecService>"
)


@pytest.mark.unit
def test_strip_html_unwraps_cdata_and_keeps_text_that_only_looks_like_a_tag():
    assert strip_html("<![CDATA[가<br/>나]]>") == "가\n나"
    assert strip_html("<![CDATA[]]>") == ""
    assert strip_html("<p>x</p><br/>y") == "x\ny"
    assert strip_html("a < b 이고 c > d 이다") == "a < b 이고 c > d 이다"
    assert strip_html("<![CDATA[매출이 a < b ... c > d 일 때]]>") == "매출이 a < b ... c > d 일 때"


@pytest.mark.unit
def test_odds_xml_keeps_holding_summary_and_key_factors(tools):
    GroupFake.prec_all_rows = [_prec_row("1", "이혼및위자료", "2021므1")]
    GroupFake.xml_bodies = {"1": XML_BODY}
    out = tools("check_precedent_odds", query="이혼 위자료", type="XML")
    case = out["representative_cases"][0]
    assert "CDATA" not in json.dumps(out, ensure_ascii=False) and "<br" not in case["holding"]
    assert case["holding"].startswith("[1] 이혼에 따른 위자료 청구가 인정되는지 여부")
    assert "원심판결을 파기환송한다" in case["summary"]
    assert out["key_factors"], out
    assert case["outcome"] == "파기환송"


# ------------------------------------------------------------------ 5. simplify_article

@pytest.mark.unit
def test_simplify_article_returns_text_and_withholds_the_glossary(server):
    out = server._tool_manager.get_tool("simplify_article").fn(law_name="저작권법", article=35, article_branch=5)
    assert out["text_simplified"] is False and out["simplified_text"] == out["original_text"]
    assert out["term_glossary"] == [] and out["glossary_status"] == "withheld" and out["terms_mapped"] == 0
    assert "배우자-반려자" in out["note"] and "lstrm_search" in out["note"]
    # no term lookup at all: neither direction of the knowledge-base link is requested
    assert not [c for c in GroupFake.calls if c[1] in ("lstrmRlt", "dlytrmRlt")]


@pytest.mark.unit
def test_simplify_article_description_says_text_is_not_simplified_and_no_glossary(server):
    tool = server._tool_manager.get_tool("simplify_article")
    assert "NOT simplified" in tool.description and "NO term glossary" in tool.description or "no term glossary" in tool.description.lower()
    assert "NOT simplified" in server._mcp_server.instructions


@pytest.mark.unit
def test_term_extraction_works_on_word_boundaries():
    from lexlink._helpers import extract_legal_terms
    text = "지방자치단체인 임차인은 특별자치시장에게 무주택자가 동시이행 항변권을 행사한다"
    terms = extract_legal_terms(text)
    assert "임차인" in terms and "무주택자" in terms and "항변권" in terms
    assert not {"지방자", "특별자", "지방자치단체인"} & set(terms)


# ------------------------------------------------------------------ 6. chain_dispute_prep

@pytest.mark.unit
def test_chain_dispute_prep_dedupes_and_describes_itself(server, tools):
    GroupFake.prec_all_rows = [
        _prec_row("1", "과징금부과처분취소", "2024구합70753", "서울행정법원"),
        _prec_row("2", "과징금부과처분취소", "2024구합70753", "서울행정법원"),
        _prec_row("3", "과징금부과처분취소", "2024구합70753", "부산지방법원"),
        _prec_row("4", "손해배상", "2024다1"),
    ]
    out = tools("chain_dispute_prep", query="과징금", display=10)
    assert [r["판례일련번호"] for r in out["precedents"]] == ["1", "3", "4"]
    assert out["search_modes"]["precedents"]["duplicates_removed"] == 1
    assert [r["title_matches_query"] for r in out["precedents"]] == [True, True, False]
    assert "메타데이터" in out["content_note"] and "prec_service" in out["content_note"]
    desc = server._tool_manager.get_tool("chain_dispute_prep").description
    assert "metadata only" in desc and "no holdings" in desc


@pytest.mark.unit
def test_title_match_ignores_a_lone_generic_word(tools):
    GroupFake.prec_all_rows = [_prec_row("1", "보증금소송", "2024다1"), _prec_row("2", "반환청구", "2024다2")]
    out = tools("chain_dispute_prep", query="보증금 반환", display=10)
    assert [r["title_matches_query"] for r in out["precedents"]] == [False, True]   # 보증금 alone is generic


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
@pytest.mark.parametrize("value", ["abc", "35의0", "제35조의0", "35-0", "0"])
def test_prompts_reject_unrecognizable_or_branch_zero_articles(server, value):
    for name, args in (("get-law-article", {"law_id": "000001"}), ("get-article-with-citations", {"law_name": "건축법"})):
        with pytest.raises(Exception):
            _prompt_text(server, name, article_number=value, **args)


@pytest.mark.unit
def test_prompt_helper_rejects_bool(server):
    # MCP clients send strings, but a direct call can pass True (an int in Python)
    fn = server._prompt_manager._prompts["get-law-article"].fn
    with pytest.raises(ValueError):
        fn(law_id="000001", article_number=True)
