"""Low-relevance warning for aiSearch / legal_resolver / chain_full_research (issue #15)."""

import asyncio
import json

import pytest

import lexlink.citation as citation_mod
import lexlink.server as server_mod
from lexlink._helpers import LOW_RELEVANCE_WARNING, low_relevance_warning
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
    assert low_relevance_warning("", [PLEDGE]) is None
    assert low_relevance_warning("zzxxcc", []) is None


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
