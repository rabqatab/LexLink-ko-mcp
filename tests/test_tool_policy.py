"""Tool policy metadata (`_meta["lexlink/policy"]`, contract v1).

Offline checks of the table and of FastMCP registration, plus real MCP clients over stdio and
Streamable HTTP (the server runs as a subprocess; no network, no OC needed).
"""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time

import jsonschema
import pytest

from lexlink import tool_policy
from lexlink.server import create_server
from lexlink.tool_policy import META_KEY, TOOL_POLICIES, validate_policy

pytestmark = pytest.mark.unit

# Independent of tool_policy.validate_policy: the published shape, written out once more.
POLICY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "category", "evidence", "size", "upstream_calls", "may_expose_credential"],
    "properties": {
        "version": {"const": 1},
        "category": {"enum": [
            "law", "law_history", "law_compare", "admin_rule", "ordinance", "treaty", "precedent",
            "constitutional", "interpretation", "admin_appeal", "committee", "knowledge", "chain",
            "assist", "meta"]},
        "evidence": {"enum": ["primary", "derived", "heuristic", "none"]},
        "size": {"enum": ["normal", "large"]},
        "upstream_calls": {"type": "integer", "minimum": 0},
        "may_expose_credential": {"type": "boolean"},
        "notes": {"type": "string", "minLength": 1},
    },
}


def _check_listed(tools) -> None:
    """`tools`: Tool objects or dicts as returned by listTools."""
    assert len(tools) >= 66
    for t in tools:
        name = t["name"] if isinstance(t, dict) else t.name
        meta = t.get("_meta") if isinstance(t, dict) else t.meta
        assert meta and META_KEY in meta, f"{name}: no _meta[{META_KEY!r}]"
        policy = meta[META_KEY]
        jsonschema.validate(policy, POLICY_SCHEMA)
        assert policy == TOOL_POLICIES[name], name


# ---- offline: table and registration ---------------------------------------------------

def test_every_registered_tool_has_a_valid_policy():
    tools = asyncio.run(create_server().list_tools())
    _check_listed(tools)


def test_table_has_no_stale_entries():
    names = {t.name for t in asyncio.run(create_server().list_tools())}
    assert set(TOOL_POLICIES) == names


def test_fastmcp_meta_survives_guarded_tool_and_leaves_tool_otherwise_unchanged():
    tools = {t.name: t for t in asyncio.run(create_server().list_tools())}
    assert len(tools) >= 66
    for t in tools.values():
        dumped = t.model_dump(by_alias=True, exclude_none=True)
        assert dumped["_meta"][META_KEY]["version"] == 1
        # annotations and input schema are untouched by the policy
        assert t.annotations.readOnlyHint is True and t.annotations.idempotentHint is True
        assert t.annotations.destructiveHint is False
        assert t.inputSchema["type"] == "object"


def test_tool_without_policy_fails_registration():
    server = create_server()  # server.tool is the guarded wrapper

    with pytest.raises(KeyError, match="no entry in lexlink.tool_policy"):
        @server.tool()
        def brand_new_tool_without_policy() -> dict:
            return {}


def test_explicit_meta_is_merged_not_replaced():
    server = create_server()
    TOOL_POLICIES["_tmp_tool"] = tool_policy._p("meta", "none", "normal", 0)
    try:
        @server.tool(meta={"other": 1})
        def _tmp_tool() -> dict:
            return {}

        tool = next(t for t in asyncio.run(server.list_tools()) if t.name == "_tmp_tool")
        assert tool.meta["other"] == 1 and META_KEY in tool.meta
    finally:
        del TOOL_POLICIES["_tmp_tool"]


GOOD = {"version": 1, "category": "law", "evidence": "primary", "size": "normal",
        "upstream_calls": 1, "may_expose_credential": False}


def test_validate_accepts_good_and_optional_notes():
    assert validate_policy(dict(GOOD)) == GOOD
    assert validate_policy({**GOOD, "notes": "주의"})["notes"] == "주의"


@pytest.mark.parametrize("change", [
    {"version": 2}, {"version": True}, {"category": "laws"}, {"category": None},
    {"evidence": "guess"}, {"size": "huge"}, {"upstream_calls": -1}, {"upstream_calls": "1"},
    {"upstream_calls": 1.0}, {"upstream_calls": True}, {"may_expose_credential": "no"},
    {"may_expose_credential": 0}, {"notes": ""}, {"notes": 5}, {"notes": "x" * 301},
    {"unknown": 1},
])
def test_validate_rejects_bad_values(change):
    with pytest.raises(ValueError):
        validate_policy({**GOOD, **change})


@pytest.mark.parametrize("drop", ["version", "category", "evidence", "size", "upstream_calls",
                                  "may_expose_credential"])
def test_validate_rejects_missing_fields(drop):
    bad = dict(GOOD)
    del bad[drop]
    with pytest.raises(ValueError):
        validate_policy(bad)


def test_table_matches_documented_cases():
    assert TOOL_POLICIES["law_as_of"]["upstream_calls"] == 5
    assert TOOL_POLICIES["oldAndNew_service"]["evidence"] == "derived"
    assert TOOL_POLICIES["check_precedent_odds"]["evidence"] == "heuristic"
    assert TOOL_POLICIES["simplify_article"]["evidence"] == "heuristic"
    assert TOOL_POLICIES["cache_stats"]["evidence"] == "none"
    # evidence: primary = upstream text fields unchanged (lists, sorted/filtered/repaged rows and
    # LexLink-computed side fields included); derived = wording edited or reconstructed
    assert TOOL_POLICIES["law_as_of"]["evidence"] == "primary"
    assert TOOL_POLICIES["eflaw_search"]["evidence"] == "primary"
    assert TOOL_POLICIES["thdCmp_service"]["evidence"] == "derived"
    assert TOOL_POLICIES["article_citation"]["evidence"] == "derived"
    assert TOOL_POLICIES["elaw_search"]["evidence"] == "derived"
    # size: large = representative size ~100KB or more and no control brings it below
    assert TOOL_POLICIES["lsDelegated_service"]["size"] == "large"
    assert TOOL_POLICIES["elaw_service"]["size"] == "large"
    assert TOOL_POLICIES["lstrm_rlt_jo_search"]["size"] == "large"
    for name in ("eflaw_service", "law_service", "thdCmp_service", "ordin_service", "lsJoHstInf_search"):
        assert TOOL_POLICIES[name]["size"] == "normal"


# ---- real clients ------------------------------------------------------------------------

def _env(extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("LEXLINK_")}
    env["OC"] = "fake-oc-for-tests"
    env.update(extra or {})
    return env


async def _list_stdio():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "lexlink.stdio_server"], env=_env())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return (await session.list_tools()).tools


def test_list_tools_over_stdio_returns_policy_meta():
    tools = asyncio.run(asyncio.wait_for(_list_stdio(), timeout=60))
    assert len(tools) >= 66
    _check_listed(tools)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def http_server(tmp_path):
    port, token = _free_port(), secrets.token_hex(16)
    env = _env({"TRANSPORT": "http", "HOST": "127.0.0.1", "PORT": str(port),
                "LEXLINK_AUTH_TOKENS": f"test:{token}", "LEXLINK_LOG_DIR": str(tmp_path / "logs")})
    proc = subprocess.Popen([sys.executable, "-m", "lexlink.http_server"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.fail(f"HTTP server exited with {proc.returncode}")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("HTTP server did not start")
        yield f"http://127.0.0.1:{port}/mcp", token
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


async def _list_http(url, token):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url, headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return (await session.list_tools()).tools


def test_list_tools_over_streamable_http_returns_policy_meta(http_server):
    url, token = http_server
    tools = asyncio.run(asyncio.wait_for(_list_http(url, token), timeout=60))
    assert len(tools) >= 66
    _check_listed(tools)


def test_http_policy_is_json_serialisable_on_the_wire(http_server):
    """Raw JSON-RPC: the key is literally `_meta` on each tool entry."""
    import httpx

    url, token = http_server
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream",
         "Content-Type": "application/json"}
    with httpx.Client(timeout=30) as c:
        r = c.post(url, headers=h, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "0"}}})
        r.raise_for_status()
        sid = r.headers.get("mcp-session-id")
        h2 = {**h, **({"mcp-session-id": sid} if sid else {})}
        c.post(url, headers=h2, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = c.post(url, headers=h2, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        r.raise_for_status()
        body = r.text
        data = json.loads(body) if body.lstrip().startswith("{") else json.loads(
            next(line[5:] for line in body.splitlines() if line.startswith("data:")))
    tools = data["result"]["tools"]
    assert len(tools) >= 66
    _check_listed(tools)
