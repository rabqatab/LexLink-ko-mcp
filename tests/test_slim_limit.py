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


def _wire(out) -> int:
    text = json.dumps(out, ensure_ascii=False, indent=2)
    return len(json.dumps(text, ensure_ascii=False).encode("utf-8"))


@pytest.mark.unit
def test_raw_content_stays_a_json_string(slim_env):
    rows = [{"조문번호": str(i), "조문내용": "제" + "가나다 \"인용\" " * 60} for i in range(400)]
    big = {"status": "ok", "request_id": "r1", "raw_content": json.dumps({"법령": {"조문": rows}}, ensure_ascii=False)}
    out = enforce_slim_limit(big)
    assert isinstance(out["raw_content"], str) and "content" not in out
    parsed = json.loads(out["raw_content"])  # still valid JSON
    assert 0 < len(parsed["법령"]["조문"]) < 400
    assert out["truncated"] is True and _wire(out) <= SLIM_MAX_BYTES
    assert "raw_content_partial" not in out


@pytest.mark.unit
def test_xml_raw_content_cut_at_closing_tag(slim_env):
    xml = "<법령>" + "".join(f"<조문><내용>{'가' * 100}</내용></조문>" for i in range(2000)) + "</법령>"
    out = enforce_slim_limit({"status": "ok", "raw_content": xml})
    assert out["raw_content_partial"] is True
    assert out["raw_content"].endswith("</조문>") or out["raw_content"].endswith("</내용>")
    assert _wire(out) <= SLIM_MAX_BYTES


@pytest.mark.unit
def test_flat_dict_of_scalar_strings_fits(slim_env):
    big = {"status": "ok", "id": "42", "request_id": "r"}
    big.update({f"k{i}": "가" * 201 for i in range(400)})
    out = enforce_slim_limit(big)
    assert _wire(out) <= SLIM_MAX_BYTES and out["truncated"] is True
    assert (out["status"], out["id"], out["request_id"]) == ("ok", "42", "r")


@pytest.mark.unit
def test_budget_counts_wire_escaping(slim_env):
    big = {"status": "ok", "rows": [{"t": '"' * 300} for _ in range(100)]}
    assert _wire(enforce_slim_limit(big)) <= SLIM_MAX_BYTES


@pytest.mark.unit
def test_note_names_only_real_params(slim_env):
    import inspect
    import lexlink.server as server_mod
    from lexlink._helpers import slim_hint
    server = server_mod.create_server()

    def hint(name):
        return slim_hint(inspect.signature(server._tool_manager.get_tool(name).fn).parameters)

    assert "jo" in hint("law_service")
    assert "jo" not in hint("trty_service") and "SLIM_RESPONSE 해제" in hint("trty_service")
    assert 'sections="summary"' in hint("prec_service")
