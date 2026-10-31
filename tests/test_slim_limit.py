"""Offline tests: SLIM_RESPONSE keeps every tool response within the PlayMCP limit.

Default mode must stay untruncated; SLIM shortens with an explicit ``truncated`` flag.
"""

import json

import pytest

from lexlink._helpers import SLIM_MAX_BYTES, enforce_slim_limit
from lexlink.cache import get_cache

from test_no_truncation import default_env, slim_env, tools  # noqa: F401  (fixtures)


def _size(out) -> int:
    return len(json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8"))


@pytest.fixture(autouse=True)
def _fresh_cache():
    get_cache().invalidate()
    yield
    get_cache().invalidate()


@pytest.mark.unit
def test_enforce_noop_by_default(default_env):
    big = {"status": "ok", "items": [{"t": "가" * 500} for _ in range(200)]}
    assert enforce_slim_limit(big) is big


@pytest.mark.unit
def test_enforce_slim_shrinks_valid_json_and_flags(slim_env):
    big = {"status": "ok", "items": [{"t": "가" * 500} for _ in range(200)], "keep": "x"}
    out = enforce_slim_limit(big)
    assert _size(out) <= SLIM_MAX_BYTES
    assert out["truncated"] is True and out["truncated_note"] and out["truncated_fields"]
    assert out["status"] == "ok" and out["keep"] == "x"
    assert out["items"] and all(i["t"] == "가" * 500 for i in out["items"])  # whole items kept
    assert len(big["items"]) == 200  # input untouched
    json.loads(json.dumps(out, ensure_ascii=False))


@pytest.mark.unit
def test_enforce_slim_long_string(slim_env):
    out = enforce_slim_limit({"status": "ok", "raw_content": "나" * 3_000_000})
    assert _size(out) <= SLIM_MAX_BYTES and out["truncated"] is True


@pytest.mark.unit
def test_enforce_slim_small_untouched(slim_env):
    small = {"status": "ok", "items": [1, 2, 3]}
    assert enforce_slim_limit(small) == small and "truncated" not in small


@pytest.mark.unit
def test_chain_law_system_slim_within_limit(slim_env, tools):
    out = tools("chain_law_system", law_name="저작권법")
    assert _size(out) <= SLIM_MAX_BYTES
    assert out["truncated"] is True
    assert out.get("truncated_note") or out.get("truncated_notes")


@pytest.mark.unit
def test_lsdelegated_service_slim_uses_compact_tree(slim_env, tools):
    out = tools("lsDelegated_service", id="000798")
    assert _size(out) <= SLIM_MAX_BYTES
    assert "raw_content" not in out and out["delegation_tree"]["entry_count"] == 400
    assert out["truncated"] is True


@pytest.mark.unit
def test_lsdelegated_service_default_keeps_raw(default_env, tools):
    out = tools("lsDelegated_service", id="000798")
    assert "delegation_tree" not in out and len(out["raw_content"]) > SLIM_MAX_BYTES
    assert "truncated" not in out


@pytest.mark.unit
def test_silent_cuts_flagged_in_slim(slim_env, tools):
    for name, kw in (
        ("check_precedent_odds", dict(query="손해배상", display=20, top_n=5)),
        ("legal_resolver", dict(situation="저작권 침해", display=5)),
        ("chain_full_research", dict(query="저작권 침해", display=5)),
    ):
        out = tools(name, **kw)
        assert out["truncated"] is True, name
        assert out.get("truncated_notes") or out.get("truncated_note"), name
        assert _size(out) <= SLIM_MAX_BYTES, name


@pytest.mark.unit
def test_no_truncated_flag_by_default(default_env, tools):
    for name, kw in (
        ("check_precedent_odds", dict(query="손해배상", display=20, top_n=5)),
        ("legal_resolver", dict(situation="저작권 침해", display=5)),
        ("chain_full_research", dict(query="저작권 침해", display=5)),
        ("chain_law_system", dict(law_name="저작권법")),
    ):
        out = tools(name, **kw)
        assert "truncated" not in out and "truncated_notes" not in out, name
