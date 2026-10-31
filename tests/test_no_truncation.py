"""Offline tests: already-fetched content is not cut by default.

``compact_limit(n)`` returns ``n`` only under ``SLIM_RESPONSE`` (PlayMCP) and
``None`` (no cap) otherwise. Each cut that used a fixed slice must keep the
full data by default and the old limit with ``SLIM_RESPONSE=true``.
"""

import asyncio
import copy
import json
import time
from pathlib import Path

import pytest

import lexlink.server as server_mod
from lexlink._helpers import (
    compact_limit,
    extract_key_factors,
    extract_legal_terms,
    extract_outcome,
    slim_enabled,
)
from lexlink.article_text import compact_delegation_tree, strip_html
from lexlink.cache import get_cache

FIXTURES = Path(__file__).parent / "fixtures"

LONG_ARTICLE = "제1항 " + "가나다라마바사 " * 400          # ~2.8K chars
LONG_HOLDING_SENT = "원고의 청구가 신의칙에 반하는지 여부 "  # prefix; callers add a distinct >100-char tail
N_CASES = 6


@pytest.fixture(autouse=True)
def _fresh_cache():
    get_cache().invalidate()
    yield
    get_cache().invalidate()


@pytest.fixture
def default_env(monkeypatch):
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)


@pytest.fixture
def slim_env(monkeypatch):
    monkeypatch.setenv("SLIM_RESPONSE", "true")


# ---------------------------------------------------------------- fake upstream

def _prec_rows(n=N_CASES):
    return [
        {"판례일련번호": str(1000 + i), "사건명": f"손해배상({i})", "사건번호": f"2024다{i}",
         "선고일자": "2024.01.11", "법원명": "대법원"}
        for i in range(n)
    ]


def _prec_body():
    # outcome keyword sits far beyond char 500 and 인용 (first in keyword order) is absent
    holding = "<br/>".join(f"[{i}] {_factor(i)}" for i in range(15))
    summary = "가" * 900 + " 원심판결을 파기환송한다."
    return {"PrecService": {"사건명": "x", "판시사항": holding, "판결요지": summary, "판례내용": "본문"}}


def _ai_rows():
    return [
        {"법령명": "저작권법", "법령ID": "000798", "조문번호": "35", "조문제목": f"제목{i}",
         "조문내용": LONG_ARTICLE}
        for i in range(5)
    ]


def _delegation_body(n_entries=400, refs_per_entry=5):
    infos = []
    for i in range(n_entries):
        infos.append({
            "조정보": {"조문번호": str(i + 1), "조문제목": f"조{i + 1}"},
            "위임정보": {
                "위임법령제목": f"시행령{i}",
                "위임법령일련번호": str(5000 + i),
                "위임구분": "시행령",
                "위임법령조문정보": [
                    {"조항호목": f"제{i + 1}조제{j}항", "링크텍스트": f"링크{j}"}
                    for j in range(refs_per_entry)
                ],
            },
        })
    return {"lsDelegated": {"법령": {
        "법령정보": {"법령ID": "000798", "법령일련번호": "283335", "법령명": "저작권법", "시행일자": "20260811"},
        "위임조문정보": infos,
    }}}


class FakeClient:
    delegation = _delegation_body()

    def __init__(self, *a, **k):
        pass

    @staticmethod
    def _ok(body):
        return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                "raw_content": json.dumps(body, ensure_ascii=False)}

    def get(self, endpoint, params, response_type="JSON"):
        target = params.get("target")
        if endpoint == "/DRF/lawSearch.do":
            if target == "aiSearch":
                return self._ok({"aiSearch": {"totalCnt": "5", "법령조문": _ai_rows()}})
            if target == "prec":
                return self._ok({"PrecSearch": {"totalCnt": str(N_CASES), "page": "1", "prec": _prec_rows()}})
            if target == "expc":
                return self._ok({"Expc": {"totalCnt": "3", "expc": [
                    {"법령해석례일련번호": str(i), "안건명": f"해석{i}", "회신일자": "20240101"} for i in range(3)]}})
            if target == "eflaw":
                rows = json.loads((FIXTURES / "eflaw_search_copyright.json").read_text(encoding="utf-8"))["LawSearch"]["law"]
                return self._ok({"LawSearch": {"totalCnt": str(len(rows)), "page": "1", "law": rows}})
            return self._ok({"Empty": {"totalCnt": "0"}})
        if target == "prec":
            return self._ok(_prec_body())
        if target == "lsDelegated":
            return self._ok(FakeClient.delegation)
        return self._ok({})


async def _fake_citations(mst, law_name, article, article_branch=0):
    return {"citations": [
        {"target_law": f"법{i}", "target_article": i + 1, "citation_type": "external"} for i in range(25)
    ]}


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", FakeClient)
    monkeypatch.setattr("lexlink.citation.extract_article_citations", _fake_citations)
    monkeypatch.setenv("OC", "unit-test-oc")
    FakeClient.delegation = _delegation_body()
    asyncio.set_event_loop(asyncio.new_event_loop())
    server = server_mod.create_server()

    def call(name, **kwargs):
        return server._tool_manager.get_tool(name).fn(**kwargs)
    return call


# ---------------------------------------------------------------- compact_limit

@pytest.mark.unit
def test_compact_limit_reads_env_at_call_time(monkeypatch):
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    assert compact_limit(7) is None
    assert list(range(20))[:compact_limit(7)] == list(range(20))
    monkeypatch.setenv("SLIM_RESPONSE", "true")
    assert compact_limit(7) == 7
    assert list(range(20))[:compact_limit(7)] == list(range(7))
    monkeypatch.delenv("SLIM_RESPONSE")
    assert compact_limit(7) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),  # unset
        ("", False),
        ("false", False),
        ("0", False),
        ("no", False),
        ("true", True),
        ("1", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_slim_enabled_truthy_values(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    else:
        monkeypatch.setenv("SLIM_RESPONSE", value)
    assert slim_enabled() is expected
    assert (compact_limit(7) == 7) is expected


# ---------------------------------------------------------------- extract_key_factors

def _factor(i):
    return f"{LONG_HOLDING_SENT}{i}번 " + "상세한사유" * 30


def _holding_text(n=15):
    return ". ".join(_factor(i) for i in range(n))


@pytest.mark.unit
def test_extract_key_factors_default_keeps_all(default_env):
    factors = extract_key_factors(_holding_text())
    assert len(factors) == 15
    assert all(len(f) > 100 for f in factors)


@pytest.mark.unit
def test_extract_key_factors_slim_keeps_old_limits(slim_env):
    factors = extract_key_factors(_holding_text())
    assert len(factors) == 10 and all(len(f) == 100 for f in factors)


# ---------------------------------------------------------------- check_precedent_odds

@pytest.mark.unit
def test_check_precedent_odds_default_full(default_env, tools):
    out = tools("check_precedent_odds", query="손해배상", display=20, top_n=5)
    assert out["status"] == "ok" and out["analyzed"] == 5
    case = out["representative_cases"][0]
    assert len(case["holding"]) > 500 and len(case["summary"]) > 500
    assert case["summary"].endswith("파기환송한다.")
    # outcome comes from the full text, past char 500
    assert case["outcome"] == "파기환송"
    assert len(out["key_factors"]) == 15
    json.dumps(out, ensure_ascii=False)


@pytest.mark.unit
def test_check_precedent_odds_slim_old_limits(slim_env, tools):
    out = tools("check_precedent_odds", query="손해배상", display=20, top_n=5)
    case = out["representative_cases"][0]
    assert len(case["holding"]) == 500 and len(case["summary"]) == 500
    assert case["outcome"] == "파기환송"          # same outcome: computed before the cap
    assert len(out["key_factors"]) == 10


# ---------------------------------------------------------------- legal_resolver

@pytest.mark.unit
def test_legal_resolver_default_full(default_env, tools):
    out = tools("legal_resolver", situation="저작권 침해", display=5)
    assert out["status"] == "ok" and len(out["applicable_laws"]) == 5
    assert all(a["article_text"] == LONG_ARTICLE for a in out["applicable_laws"])
    assert len(out["citations"]) == 25
    assert len(out["legal_interpretations"]) == 3          # display=3 sub-search, retained
    json.dumps(out, ensure_ascii=False)


@pytest.mark.unit
def test_legal_resolver_slim_old_limits(slim_env, tools):
    out = tools("legal_resolver", situation="저작권 침해", display=5)
    assert all(len(a["article_text"]) == 500 for a in out["applicable_laws"])
    assert len(out["citations"]) == 10


# ---------------------------------------------------------------- chain_full_research

@pytest.mark.unit
def test_chain_full_research_default_composite(default_env, tools):
    out = tools("chain_full_research", query="저작권 침해", display=5)
    assert out["status"] == "ok"
    assert len(out["precedent_analysis"]["representative_cases"]) == 5
    assert len(out["precedent_analysis"]["key_factors"]) == 15
    assert len(out["citations"]) == 25
    assert all(len(a["article_text"]) > 500 for a in out["applicable_laws"])
    json.dumps(out, ensure_ascii=False)


@pytest.mark.unit
def test_chain_full_research_slim_old_limits(slim_env, tools):
    out = tools("chain_full_research", query="저작권 침해", display=5)
    assert 1 <= len(out["precedent_analysis"]["representative_cases"]) <= 3  # size guard may trim more
    assert len(out["precedent_analysis"]["key_factors"]) == 10
    assert len(out["citations"]) == 10
    assert all(len(a["article_text"]) == 500 for a in out["applicable_laws"])


# ---------------------------------------------------------------- chain_law_system / compact_delegation_tree

@pytest.mark.unit
def test_chain_law_system_default_full_tree(default_env, tools):
    out = tools("chain_law_system", law_name="저작권법")
    tree = out["delegation_tree"]
    assert tree["entry_count"] == 400 and len(tree["entries"]) == 400
    assert tree["truncated"] is False and "note" not in tree
    assert all(len(e["references"]) == 5 for e in tree["entries"])
    json.dumps(out, ensure_ascii=False)


@pytest.mark.unit
def test_chain_law_system_slim_old_limits(slim_env, tools):
    tree = tools("chain_law_system", law_name="저작권법")["delegation_tree"]
    assert tree["entry_count"] == 400 and 0 < len(tree["entries"]) <= 80  # size guard may trim more
    assert tree["truncated"] is True and "80건" in tree["note"]
    assert all(len(e["references"]) == 3 for e in tree["entries"])


@pytest.mark.unit
def test_compact_delegation_tree_max_entries_semantics(default_env):
    raw = json.dumps(_delegation_body(10), ensure_ascii=False)
    assert compact_delegation_tree(raw)["truncated"] is False
    capped = compact_delegation_tree(raw, max_entries=4)
    assert len(capped["entries"]) == 4 and capped["truncated"] is True and "note" in capped
    exact = compact_delegation_tree(raw, max_entries=10)
    assert exact["truncated"] is False and "note" not in exact


# ---------------------------------------------------------------- the cut values were never fed downstream

@pytest.mark.unit
def test_downstream_helpers_handle_large_text_fast(default_env):
    sentence = "원고의 청구가 신의칙에 반하는지 여부를 판단한다. 피고는 손해배상 책임을 부담한다. "
    body = sentence * (200_000 // len(sentence) + 1) + " 원심판결을 파기환송한다."
    assert len(body) >= 200_000
    t0 = time.perf_counter()
    assert extract_outcome(body) in ("파기환송", "파기")
    factors = extract_key_factors(body)
    terms = extract_legal_terms(body)
    stripped = strip_html(body.replace(". ", ".<br/>"))
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, elapsed
    assert len(factors) == 1  # identical sentences de-duplicate
    assert len(terms) >= 2 and len(stripped) > 100_000


@pytest.mark.unit
def test_extract_legal_terms_still_capped_fan_out(default_env):
    # simplify_article makes up to 2 upstream calls per term: this cap stays
    text = " ".join(f"가나{chr(0xAC00 + i)}행위" for i in range(60))
    assert len(extract_legal_terms(text)) == 20
