"""HTTP-mode hardening: auth, logging, rate limit, host validation, app factory."""

import asyncio
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from lexlink import http_server
from lexlink.http_security import (
    BearerAuthMiddleware,
    RateLimitMiddleware,
    SessionBindingMiddleware,
    parse_auth_tokens,
    resolve_client_ip,
    token_id_for,
)
from lexlink.params import resolve_oc, set_ignore_oc_override
from lexlink.raw_logger import LoggingMiddleware, LogWriter, build_entry

pytestmark = pytest.mark.unit

TOKEN = "fake-token-aaaaaaaaaaaa"
TOKEN2 = "fake-token-bbbbbbbbbbbb"
INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
               "clientInfo": {"name": "t", "version": "0"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream",
               "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.startswith("LEXLINK_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("LEXLINK_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("OC", "fake-oc-env-1234")
    yield
    set_ignore_oc_override(False)


def auth_headers(token=TOKEN):
    return {**MCP_HEADERS, "Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- ASGI helpers

def make_scope(method="POST", headers=(), client=("203.0.113.9", 1234), state=None):
    return {
        "type": "http", "method": method, "path": "/mcp", "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": client, "state": state if state is not None else {"token_id": "tid"},
    }


async def call(app, scope, body=b""):
    sent = []
    done = False

    async def receive():
        nonlocal done
        if done:
            await asyncio.sleep(3600)
        done = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(m):
        sent.append(m)

    await app(scope, receive, send)
    return sent


def json_app(payload, status=200, ctype="application/json", extra=()):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", ctype.encode()), *extra]})
        await send({"type": "http.response.body", "body": raw})
    return app


def tool_result(payload: dict, is_error=False):
    return {"jsonrpc": "2.0", "id": 7, "result": {
        "content": [{"type": "text", "text": json.dumps(payload)}], "isError": is_error}}


def tool_call_body(args=None):
    return json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                       "params": {"name": "law_search",
                                  "arguments": args or {"query": "SECRET-QUERY", "oc": "fake-oc-arg-9999"}}}
                      ).encode()


SCHEMAS = {"law_search": {"query", "oc", "display"}}


def run_logged(app, body, tmp_path, **kw):
    kw.setdefault("tool_schemas", SCHEMAS)
    writer = LogWriter(tmp_path / "w")
    mw = LoggingMiddleware(app, writer=writer, **kw)
    scope = make_scope(headers=[("authorization", f"Bearer {TOKEN}")])
    asyncio.run(call(mw, scope, body))
    writer.flush()
    lines = (tmp_path / "w" / f"{datetime.now().date()}.jsonl").read_text().splitlines()
    return [json.loads(x) for x in lines], "\n".join(lines)


# ------------------------------------------------------------------------ auth

def test_token_parsing_and_malformed():
    assert parse_auth_tokens("a:t1, b:t2") == ["t1", "t2"]
    for bad in ("nocolon", ":tok", "name:", "a:t,a:u", "a:t,b:t", " , "):
        with pytest.raises(RuntimeError):
            parse_auth_tokens(bad)


def test_fail_closed_without_tokens():
    with pytest.raises(RuntimeError, match="LEXLINK_AUTH_TOKENS"):
        http_server.create_app()


def test_fail_closed_on_malformed_and_nonexact_allow(monkeypatch):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", "garbage")
    with pytest.raises(RuntimeError):
        http_server.create_app()
    monkeypatch.delenv("LEXLINK_AUTH_TOKENS")
    monkeypatch.setenv("LEXLINK_ALLOW_NO_AUTH", "TRUE")
    with pytest.raises(RuntimeError):
        http_server.create_app()


def test_auth_401_and_200_multi_token(monkeypatch):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN},b:{TOKEN2}")
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "testserver")
    with TestClient(http_server.create_app()) as c:
        r = c.post("/mcp", json=INIT, headers=MCP_HEADERS)
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
        assert r.json()["error"] == "unauthorized"
        assert c.post("/mcp", json=INIT, headers=auth_headers("wrong")).status_code == 401
        h = {**MCP_HEADERS, "Authorization": f"Basic {TOKEN}"}
        assert c.post("/mcp", json=INIT, headers=h).status_code == 401
        assert c.post("/mcp", json=INIT, headers=auth_headers(TOKEN)).status_code == 200
        assert c.post("/mcp", json=INIT, headers=auth_headers(TOKEN2)).status_code == 200


def test_allow_no_auth(monkeypatch, caplog):
    monkeypatch.setenv("LEXLINK_ALLOW_NO_AUTH", "true")
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "testserver")
    with caplog.at_level("WARNING"):
        app = http_server.create_app()
    assert any("WITHOUT" in r.message for r in caplog.records)
    with TestClient(app) as c:
        assert c.post("/mcp", json=INIT, headers=MCP_HEADERS).status_code == 200


def test_token_id_is_hash_prefix():
    seen = {}

    async def inner(scope, receive, send):
        seen.update(scope["state"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    mw = BearerAuthMiddleware(inner, [TOKEN])
    asyncio.run(call(mw, make_scope(headers=[("authorization", f"Bearer {TOKEN}")], state={})))
    assert seen["token_id"] == token_id_for(TOKEN)
    assert len(seen["token_id"]) == 12 and TOKEN not in seen["token_id"]


def test_lifespan_passthrough():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    mw = BearerAuthMiddleware(inner, [TOKEN])
    asyncio.run(mw({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


# ------------------------------------------------------------------- streaming

def streaming_app(release: asyncio.Event):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/event-stream"),
                                (b"set-cookie", b"a=1"), (b"set-cookie", b"b=2")]})
        await send({"type": "http.response.body", "body": b"data: one\n\n", "more_body": True})
        await release.wait()
        await send({"type": "http.response.body", "body": b"data: two\n\n"})
    return app


async def _prove_streaming(build, scope, tmp_path):
    release = asyncio.Event()
    got_first = asyncio.Event()
    sent = []

    async def receive():
        await asyncio.sleep(3600)

    async def send(m):
        sent.append(m)
        if m["type"] == "http.response.body" and m["body"] == b"data: one\n\n":
            got_first.set()

    app = build(streaming_app(release))
    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(got_first.wait(), 2)
    assert not task.done()  # chunk 1 reached client while app still running
    release.set()
    await asyncio.wait_for(task, 2)
    return sent


def test_logging_streams_chunk_before_app_finishes(tmp_path):
    w = LogWriter(tmp_path / "w")
    sent = asyncio.run(_prove_streaming(
        lambda a: LoggingMiddleware(a, writer=w), make_scope(method="GET"), tmp_path))
    assert [m.get("body") for m in sent[1:]] == [b"data: one\n\n", b"data: two\n\n"]
    # multi-value headers preserved unchanged
    assert [v for k, v in sent[0]["headers"] if k == b"set-cookie"] == [b"a=1", b"b=2"]
    w.flush()
    entry = json.loads(next((tmp_path / "w").glob("*.jsonl")).read_text())
    assert entry["method"] == "GET" and entry["response_bytes"] == 22


def test_full_stack_streams(tmp_path):
    w = LogWriter(tmp_path / "w")

    def build(app):
        return BearerAuthMiddleware(
            LoggingMiddleware(RateLimitMiddleware(app, 2, 10), writer=w), [TOKEN])

    scope = make_scope(method="POST", headers=[("authorization", f"Bearer {TOKEN}")], state={})
    sent = asyncio.run(_prove_streaming(build, scope, tmp_path))
    assert sent[0]["status"] == 200
    assert [v for k, v in sent[0]["headers"] if k == b"set-cookie"] == [b"a=1", b"b=2"]


# --------------------------------------------------------------------- logging

def test_default_log_has_no_values_or_secrets(tmp_path):
    app = json_app(tool_result({"status": "ok", "raw_content": "SECRET-BODY"}))
    entries, text = run_logged(app, tool_call_body(), tmp_path)
    e = entries[0]
    assert e["tool_name"] == "law_search" and e["method"] == "tools/call"
    assert e["arguments_keys"] == ["oc", "query"]
    assert e["status"] == "ok" and e["http_status"] == 200
    assert e["response_bytes"] > 0 and e["client_ip"] == "203.0.113.9"
    for forbidden in ("SECRET-QUERY", "SECRET-BODY", TOKEN, "fake-oc-arg-9999", "uthorization"):
        assert forbidden not in text


def test_log_bodies_opt_in_drops_oc(monkeypatch, tmp_path):
    monkeypatch.setenv("LEXLINK_LOG_BODIES", "true")
    body = tool_call_body({"query": "Q1", "OC": "fake-oc-arg-9999", "Token": "tk", "n": 3})
    app = json_app(tool_result({"status": "ok", "url": "http://x/y?OC=fake-oc-env-1234&a=1"}))
    entries, text = run_logged(app, body, tmp_path)
    assert entries[0]["arguments"] == {"query": "Q1", "n": 3}
    assert "fake-oc-env-1234" not in text and "fake-oc-arg-9999" not in text
    assert "a=1" in text


def test_result_parsed_from_plain_json_and_sse(tmp_path):
    err = tool_result({"status": "error", "error_code": "NOT_FOUND", "message": "m"}, True)
    entries, _ = run_logged(json_app(err), tool_call_body(), tmp_path)
    assert entries[0]["status"] == "error" and entries[0]["error_code"] == "NOT_FOUND"

    sse = ("event: message\ndata: " + json.dumps(err) + "\n\n").encode()
    entries, _ = run_logged(json_app(sse, ctype="text/event-stream"), tool_call_body(), tmp_path / "s")
    assert entries[0]["status"] == "error" and entries[0]["error_code"] == "NOT_FOUND"


def test_capture_cap(tmp_path):
    big = tool_result({"status": "ok", "raw_content": "x" * 5000})
    entries, _ = run_logged(json_app(big), tool_call_body(), tmp_path, capture_max_bytes=200)
    assert entries[0]["truncated_capture"] is True
    assert entries[0]["response_bytes"] > 5000  # total counted past cap
    assert entries[0]["method"] == "tools/call"


def test_non_mcp_post_not_logged(tmp_path):
    w = LogWriter(tmp_path / "w")
    mw = LoggingMiddleware(json_app({"x": 1}), writer=w)
    asyncio.run(call(mw, make_scope(), b"not json"))
    w.flush()
    assert not list((tmp_path / "w").glob("*.jsonl"))


def test_retention_deletes_only_old_dated_files(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    old = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d.jsonl")
    new = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d.jsonl")
    for n in (old, new, "notes.jsonl", "2020-01-01.txt", "keep.log"):
        (d / n).write_text("x")
    w = LogWriter(d, retention_days=30)
    w.write({"a": 1})
    w.flush()
    names = {p.name for p in d.iterdir()}
    assert old not in names
    assert {new, "notes.jsonl", "2020-01-01.txt", "keep.log"} <= names


def test_xff_trusted_vs_untrusted():
    hdr = [("x-forwarded-for", "198.51.100.7, 10.0.0.2"), ("x-forwarded-for", "10.0.0.3")]
    scope = make_scope(headers=hdr, client=("10.0.0.3", 1))
    assert resolve_client_ip(scope, frozenset()) == "10.0.0.3"
    assert resolve_client_ip(scope, frozenset({"10.0.0.3"})) == "10.0.0.2"
    assert resolve_client_ip(scope, frozenset({"10.0.0.3", "10.0.0.2"})) == "198.51.100.7"
    spoof = make_scope(headers=[("x-forwarded-for", "1.2.3.4")], client=("203.0.113.9", 1))
    assert resolve_client_ip(spoof, frozenset({"10.0.0.3"})) == "203.0.113.9"


def test_build_entry_get_stream():
    e = build_entry(req_body=b"", resp_body=b"", content_type="text/event-stream",
                    http_method="GET", http_status=200, response_bytes=0, duration_ms=1.0,
                    token_id="t", client_ip=None, truncated_capture=False, log_bodies=False)
    assert e["method"] == "GET" and e["status"] == "ok"


# ------------------------------------------------------------------ rate limit

def test_per_minute_429_with_retry_after_and_get_unlimited():
    now = [100.0]
    app = RateLimitMiddleware(json_app({}), 5, 2, clock=lambda: now[0])
    for _ in range(2):
        assert asyncio.run(call(app, make_scope()))[0]["status"] == 200
    third = asyncio.run(call(app, make_scope()))
    assert third[0]["status"] == 429
    assert int(dict(third[0]["headers"])[b"retry-after"]) >= 1
    # other token unaffected; GET never limited
    assert asyncio.run(call(app, make_scope(state={"token_id": "other"})))[0]["status"] == 200
    for _ in range(5):
        assert asyncio.run(call(app, make_scope(method="GET")))[0]["status"] == 200
    now[0] += 61
    assert asyncio.run(call(app, make_scope()))[0]["status"] == 200


def test_concurrency_429_and_release_after_exception():
    async def scenario():
        gate = asyncio.Event()

        async def slow(scope, receive, send):
            await gate.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = RateLimitMiddleware(slow, 2, 1000)
        t1 = asyncio.create_task(call(mw, make_scope()))
        t2 = asyncio.create_task(call(mw, make_scope()))
        await asyncio.sleep(0.05)
        third = await call(mw, make_scope())
        assert third[0]["status"] == 429 and dict(third[0]["headers"])[b"retry-after"]
        gate.set()
        await asyncio.gather(t1, t2)
        assert (await call(mw, make_scope()))[0]["status"] == 200

        async def boom(scope, receive, send):
            raise ValueError("x")

        mw2 = RateLimitMiddleware(boom, 1, 1000)
        for _ in range(3):  # slot released each time
            with pytest.raises(ValueError):
                await call(mw2, make_scope())

        mw3 = RateLimitMiddleware(slow, 1, 1000)  # cancel (client disconnect) frees slot
        gate.clear()
        t = asyncio.create_task(call(mw3, make_scope()))
        await asyncio.sleep(0.05)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        gate.set()
        assert (await call(mw3, make_scope()))[0]["status"] == 200

    asyncio.run(scenario())


# ------------------------------------------------------- host validation / app

def test_host_validation_through_create_app(monkeypatch):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "mcp.example.test")
    monkeypatch.setenv("LEXLINK_ALLOWED_ORIGINS", "https://mcp.example.test")
    with TestClient(http_server.create_app()) as c:
        ok = c.post("/mcp", json=INIT, headers={**auth_headers(), "Host": "mcp.example.test"})
        assert ok.status_code == 200
        bad = c.post("/mcp", json=INIT, headers={**auth_headers(), "Host": "evil.test"})
        assert bad.status_code in (400, 421)
        badorigin = c.post("/mcp", json=INIT, headers={
            **auth_headers(), "Host": "mcp.example.test", "Origin": "https://evil.test"})
        assert badorigin.status_code in (400, 403)


def test_default_hosts_keep_localhost_protection(monkeypatch, caplog):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    with caplog.at_level("WARNING"):
        app = http_server.create_app()
    assert any("LEXLINK_ALLOWED_HOSTS" in r.message for r in caplog.records)
    with TestClient(app) as c:
        r = c.post("/mcp", json=INIT, headers={**auth_headers(), "Host": "evil.test"})
        assert r.status_code in (400, 421)


def test_create_server_called_once(monkeypatch):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    with patch.object(http_server, "create_server",
                      wraps=http_server.create_server) as m:
        http_server.create_app()
    assert m.call_count == 1
    assert not hasattr(http_server, "_server") and not hasattr(http_server, "app")


def test_oc_arg_ignored_in_http_mode_honoured_by_default(monkeypatch):
    assert resolve_oc("fake-oc-arg-9999") == "fake-oc-arg-9999"
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    http_server.create_app()
    assert resolve_oc("fake-oc-arg-9999") == "fake-oc-env-1234"
    set_ignore_oc_override(False)
    assert resolve_oc("fake-oc-arg-9999") == "fake-oc-arg-9999"


def test_tools_list_over_http(monkeypatch):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "testserver")
    with TestClient(http_server.create_app()) as c:
        r = c.post("/mcp", json=INIT, headers=auth_headers())
        sid = r.headers["mcp-session-id"]
        h = {**auth_headers(), "mcp-session-id": sid}
        c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h)
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=h)
        assert r.status_code == 200 and "law_search" in r.text


# ------------------------------------------------- hardening round 2 (PR #8)

def test_default_log_never_contains_client_controlled_strings(tmp_path):
    def body(name, args, method="tools/call"):
        return json.dumps({"jsonrpc": "2.0", "id": 7, "method": method,
                           "params": {"name": name, "arguments": args}}).encode()

    app = json_app(tool_result({"status": "ok"}))
    e, text = run_logged(app, body("my secret 900101-1234567", {"SECRETKEY-abc": "v", "query": "q"}),
                         tmp_path / "a")
    assert e[0]["tool_name"] == "<unknown>"
    assert e[0].get("arguments_keys") == [] and e[0]["unknown_arg_keys"] == 2
    e, text = run_logged(app, body({"leak": "SECRETNAME-dict"}, {}), tmp_path / "b")
    assert e[0]["tool_name"] == "<unknown>" and "SECRETNAME" not in text
    e, text = run_logged(app, body("law_search", {"query": "x", "BADKEY": 1}), tmp_path / "c")
    assert e[0]["tool_name"] == "law_search"
    assert e[0]["arguments_keys"] == ["query"] and e[0]["unknown_arg_keys"] == 1
    assert "BADKEY" not in text
    e, text = run_logged(app, body("x", {}, method="SECRETMETHOD"), tmp_path / "d")
    assert e[0]["method"] == "<unknown>" and "SECRETMETHOD" not in text
    e, text = run_logged(app, b'{"method":"BADJSON-METHOD" oops', tmp_path / "e")
    assert e[0]["method"] == "<unknown>" and "BADJSON" not in text
    e, _ = run_logged(app, body("x", {}, method="tools/list"), tmp_path / "f")
    assert e[0]["method"] == "tools/list" and "tool_name" not in e[0]


def test_create_app_passes_registered_tools_to_logger(monkeypatch):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    app = http_server.create_app()
    logger_mw = app.app
    assert isinstance(logger_mw, LoggingMiddleware)
    assert "oc" in logger_mw.tool_schemas["law_search"]
    assert "query" in logger_mw.tool_schemas["law_search"]
    assert len(logger_mw.tool_schemas) >= 50


def test_log_bodies_scrubs_nested_sensitive_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("LEXLINK_LOG_BODIES", "true")
    args = {"query": "q", "filters": {"oc": "NESTEDOC123456"},
            "nested": {"authorization": "Bearer SECRETTOK", "Token": "TOK2", "ok": 1},
            "list": [{"OC": "INLIST"}, {"api_token": "T3", "keep": "yes"}]}
    res = tool_result({"status": "ok", "inner": {"oc": "RESOC", "x": [{"authorization": "A"}]}})
    entries, text = run_logged(json_app(res), tool_call_body(args), tmp_path)
    for secret in ("NESTEDOC123456", "SECRETTOK", "TOK2", "INLIST", "T3", "RESOC", '"A"'):
        assert secret not in text, secret
    assert entries[0]["arguments"]["nested"] == {"ok": 1}
    assert entries[0]["arguments"]["list"][1] == {"keep": "yes"}


def test_uvicorn_run_disables_proxy_headers(monkeypatch):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    import uvicorn
    for fn in (http_server.run_http_server, http_server.run_sse_server):
        with patch.object(uvicorn, "run") as run:
            fn(host="127.0.0.1", port=1)
        assert run.call_args.kwargs["proxy_headers"] is False


def test_sse_startup_warning(monkeypatch, caplog):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    with caplog.at_level("WARNING"):
        http_server.create_app("sse")
    assert any("TRANSPORT=sse" in r.message for r in caplog.records)
    caplog.clear()
    with caplog.at_level("WARNING"):
        http_server.create_app("http")
    assert not any("TRANSPORT=sse" in r.message for r in caplog.records)


def test_websocket_scope_closed_unless_authorised():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    mw = BearerAuthMiddleware(inner, [TOKEN])
    sent = []

    async def send(m):
        sent.append(m)

    asyncio.run(mw({"type": "websocket", "headers": [], "path": "/x"}, None, send))
    assert sent == [{"type": "websocket.close", "code": 1008}] and seen == []
    asyncio.run(mw({"type": "lifespan"}, None, send))
    assert seen == ["lifespan"]


def test_origins_without_hosts_fails_startup(monkeypatch):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    monkeypatch.setenv("LEXLINK_ALLOWED_ORIGINS", "https://mcp.example.test")
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        http_server.create_app()


def test_retention_runs_at_writer_start_without_writes(tmp_path):
    d = tmp_path / "r2"
    d.mkdir()
    old = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d.jsonl")
    (d / old).write_text("x")
    w = LogWriter(d, retention_days=30)
    for _ in range(100):
        if not (d / old).exists():
            break
        import time as _t; _t.sleep(0.02)
    assert not (d / old).exists()
    w.flush()


def test_log_file_and_dir_permissions(tmp_path):
    import stat
    old_umask = os.umask(0o022)
    try:
        d = tmp_path / "perm" / "logs"
        w = LogWriter(d)
        w.write({"a": 1})
        w.flush()
    finally:
        os.umask(old_umask)
    f = next(d.glob("*.jsonl"))
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_dropped_entries_counted_and_warned_once_a_minute(tmp_path, caplog):
    import threading
    w = LogWriter(tmp_path / "drop", maxsize=1)
    gate = threading.Event()
    orig = w._write_entry
    w._write_entry = lambda e: gate.wait(5) or orig(e)
    with caplog.at_level("WARNING"):
        for i in range(30):
            w.write({"i": i})
    gate.set()
    w.flush()
    assert w.dropped >= 20
    warns = [r for r in caplog.records if "entries dropped" in r.message]
    assert len(warns) == 1


# ------------------------------------------------------- session binding
def _two_token_env(monkeypatch, **extra):
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN},b:{TOKEN2}")
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "testserver")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


def _new_session(c, token=TOKEN):
    r = c.post("/mcp", json=INIT, headers=auth_headers(token))
    assert r.status_code == 200
    h = {**auth_headers(token), "mcp-session-id": r.headers["mcp-session-id"]}
    c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h)
    return r.headers["mcp-session-id"]


LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


def test_session_foreign_token_gets_404_owner_unaffected(monkeypatch):
    _two_token_env(monkeypatch)
    with TestClient(http_server.create_app()) as c:
        sid = _new_session(c)
        hb = {**auth_headers(TOKEN2), "mcp-session-id": sid}
        assert c.post("/mcp", json=LIST, headers=hb).status_code == 404
        assert c.get("/mcp", headers=hb).status_code == 404
        assert c.delete("/mcp", headers=hb).status_code == 404
        ha = {**auth_headers(), "mcp-session-id": sid}
        r = c.post("/mcp", json=LIST, headers=ha)
        assert r.status_code == 200 and "law_search" in r.text


def test_session_owner_delete_removes_binding(monkeypatch):
    _two_token_env(monkeypatch)
    with TestClient(http_server.create_app()) as c:
        sid = _new_session(c)
        ha = {**auth_headers(), "mcp-session-id": sid}
        assert c.delete("/mcp", headers=ha).status_code in (200, 204)
        assert c.post("/mcp", json=LIST, headers=ha).status_code == 404


def test_session_binding_table_released_on_delete_and_404():
    def fake(status_for):
        async def app(scope, receive, send):
            hdrs = [] if scope["method"] != "POST" else [(b"mcp-session-id", b"s1")]
            if any(k == b"mcp-session-id" for k, _ in scope["headers"]):
                hdrs = []
            await send({"type": "http.response.start", "status": status_for(scope), "headers": hdrs})
            await send({"type": "http.response.body", "body": b""})
        return app

    def scope(method, sid=None):
        h = [("mcp-session-id", sid)] if sid else []
        return make_scope(method=method, headers=h, state={"token_id": "A"})

    mw = SessionBindingMiddleware(fake(lambda s: 200), 10)
    asyncio.run(call(mw, scope("POST")))
    assert mw._bindings == {"s1": "A"}
    asyncio.run(call(mw, scope("DELETE", "s1")))
    assert mw._bindings == {}
    asyncio.run(call(mw, scope("POST")))
    mw.app = fake(lambda s: 404)  # session crashed/terminated inside the app
    asyncio.run(call(mw, scope("POST", "s1")))
    assert mw._bindings == {}


def test_session_unknown_and_foreign_bodies_identical(monkeypatch):
    _two_token_env(monkeypatch)
    with TestClient(http_server.create_app()) as c:
        sid = _new_session(c)
        unknown = c.post("/mcp", json=LIST, headers={
            **auth_headers(TOKEN2), "mcp-session-id": "0" * 32})
        foreign = c.post("/mcp", json=LIST, headers={
            **auth_headers(TOKEN2), "mcp-session-id": sid})
        assert unknown.status_code == foreign.status_code == 404
        assert unknown.content == foreign.content
        assert unknown.headers["content-type"] == foreign.headers["content-type"]


def test_session_cap_refuses_new_sessions_without_eviction(monkeypatch):
    _two_token_env(monkeypatch, LEXLINK_MAX_SESSIONS="2")
    with TestClient(http_server.create_app()) as c:
        s1 = _new_session(c)
        s2 = _new_session(c)
        r = c.post("/mcp", json=INIT, headers=auth_headers(TOKEN2))
        assert r.status_code == 503 and "mcp-session-id" not in r.headers
        # existing sessions stay bound (not evicted) and still work for the owner
        hb = {**auth_headers(TOKEN2), "mcp-session-id": s1}
        assert c.post("/mcp", json=LIST, headers=hb).status_code == 404
        ha = {**auth_headers(), "mcp-session-id": s1}
        assert c.post("/mcp", json=LIST, headers=ha).status_code == 200
        # freeing a slot admits a new session
        assert c.delete("/mcp", headers={**auth_headers(), "mcp-session-id": s2}).status_code in (200, 204)
        assert c.post("/mcp", json=INIT, headers=auth_headers(TOKEN2)).status_code == 200


def test_session_binding_streams_unbuffered():
    def build(app):
        return BearerAuthMiddleware(SessionBindingMiddleware(app, 10), [TOKEN])

    scope = make_scope(method="GET", headers=[("authorization", f"Bearer {TOKEN}")], state={})
    sent = asyncio.run(_prove_streaming(build, scope, None))
    assert [m.get("body") for m in sent[1:]] == [b"data: one\n\n", b"data: two\n\n"]
    assert [v for k, v in sent[0]["headers"] if k == b"set-cookie"] == [b"a=1", b"b=2"]


SSE_SID = "a" * 32


def sse_app(release: asyncio.Event):
    async def app(scope, receive, send):
        if scope["path"] == "/sse":
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/event-stream")]})
            await send({"type": "http.response.body", "more_body": True,
                        "body": f"event: endpoint\r\ndata: /messages/?session_id={SSE_SID}\r\n\r\n".encode()})
            await release.wait()
            await send({"type": "http.response.body", "body": b""})
        else:
            await send({"type": "http.response.start", "status": 202, "headers": []})
            await send({"type": "http.response.body", "body": b"Accepted"})
    return app


def _sse_scope(method, path, token, query=b""):
    s = make_scope(method=method, headers=[("authorization", f"Bearer {token}")], state={})
    s.update(path=path, query_string=query)
    return s


def test_sse_session_bound_to_token_and_released_on_close():
    async def run():
        release = asyncio.Event()
        got = asyncio.Event()
        chunks = []
        app = BearerAuthMiddleware(
            SessionBindingMiddleware(sse_app(release), 10), [TOKEN, TOKEN2])

        async def receive():
            await asyncio.sleep(3600)

        async def send(m):
            if m["type"] == "http.response.body":
                chunks.append(m["body"])
                got.set()

        task = asyncio.create_task(app(_sse_scope("GET", "/sse", TOKEN), receive, send))
        await asyncio.wait_for(got.wait(), 2)
        assert chunks[0].startswith(b"event: endpoint")  # forwarded unaltered
        q = f"session_id={SSE_SID}".encode()
        post_b = await call(app, _sse_scope("POST", "/messages/", TOKEN2, q), b"{}")
        post_a = await call(app, _sse_scope("POST", "/messages/", TOKEN, q), b"{}")
        post_u = await call(app, _sse_scope("POST", "/messages/", TOKEN2, b"session_id=" + b"b" * 32), b"{}")
        post_dup = await call(app, _sse_scope(
            "POST", "/messages/", TOKEN2, b"session_id=" + b"b" * 32 + b"&" + q), b"{}")
        post_up = await call(app, _sse_scope(
            "POST", "/messages/", TOKEN2, f"session_id={SSE_SID.upper()}".encode()), b"{}")
        release.set()
        await asyncio.wait_for(task, 2)
        after = await call(app, _sse_scope("POST", "/messages/", TOKEN2, q), b"{}")
        return post_b, post_a, post_u, post_dup, post_up, after

    post_b, post_a, post_u, post_dup, post_up, after = asyncio.run(run())
    assert post_b[0]["status"] == 404 and post_b[1]["body"] == b"Could not find session"
    assert post_dup[0]["status"] == 404 and post_up[0]["status"] == 404
    assert post_a[0]["status"] == 202
    assert post_u[0]["status"] == 202  # unknown id passes through to the app
    assert after[0]["status"] == 202  # binding gone once the stream ended


def test_noauth_sessions_unaffected(monkeypatch):
    monkeypatch.setenv("LEXLINK_ALLOW_NO_AUTH", "true")
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "testserver")
    with TestClient(http_server.create_app()) as c:
        r = c.post("/mcp", json=INIT, headers=MCP_HEADERS)
        sid = r.headers["mcp-session-id"]
        h = {**MCP_HEADERS, "mcp-session-id": sid}
        c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h)
        assert c.post("/mcp", json=LIST, headers=h).status_code == 200


# ------------------------------------------------------- idle session expiry
class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _capture_manager(monkeypatch):
    """Capture the FastMCP instance create_app builds (to inspect its manager)."""
    box = {}
    real = http_server.create_server

    def wrapper(*a, **kw):
        box["mcp"] = real(*a, **kw)
        return box["mcp"]

    monkeypatch.setattr(http_server, "create_server", wrapper)
    return box


def _idle_env(monkeypatch, ttl="100", **extra):
    _two_token_env(monkeypatch, LEXLINK_SESSION_IDLE_TTL_SEC=ttl, **extra)


def _hdr(sid, token=TOKEN):
    return {**auth_headers(token), "mcp-session-id": sid}


def test_idle_session_expires_owner_gets_unknown_404_then_new_session(monkeypatch):
    _idle_env(monkeypatch)
    box = _capture_manager(monkeypatch)
    clock = FakeClock()
    with TestClient(http_server.create_app(clock=clock)) as c:
        mgr = box["mcp"].session_manager
        sid = _new_session(c)
        assert sid in mgr._server_instances
        clock.t += 101
        unknown = c.post("/mcp", json=LIST, headers=_hdr("0" * 32))
        r = c.post("/mcp", json=LIST, headers=_hdr(sid))
        assert r.status_code == unknown.status_code == 404
        assert r.content == unknown.content
        assert r.headers["content-type"] == unknown.headers["content-type"]
        # the underlying session is gone and memory is released
        assert sid not in mgr._server_instances
        assert c.app.session_binding._bindings == {}
        assert c.app.session_binding._meta == {}
        # repeated requests, GET and DELETE too, stay identical 404s
        for call in (lambda: c.get("/mcp", headers=_hdr(sid)),
                     lambda: c.delete("/mcp", headers=_hdr(sid))):
            again = call()
            assert again.status_code == 404
        assert c.post("/mcp", json=LIST, headers=_hdr(sid)).content == unknown.content
        # client flow: new initialize works and the new session is usable
        sid2 = _new_session(c)
        assert sid2 != sid
        assert "law_search" in c.post("/mcp", json=LIST, headers=_hdr(sid2)).text


def test_idle_expired_session_foreign_token_same_404(monkeypatch):
    _idle_env(monkeypatch)
    clock = FakeClock()
    with TestClient(http_server.create_app(clock=clock)) as c:
        sid = _new_session(c)
        clock.t += 101
        c.portal.call(c.app.session_binding.sweep)
        owner = c.post("/mcp", json=LIST, headers=_hdr(sid))
        other = c.post("/mcp", json=LIST, headers=_hdr(sid, TOKEN2))
        unknown = c.post("/mcp", json=LIST, headers=_hdr("1" * 32, TOKEN2))
        assert owner.status_code == other.status_code == unknown.status_code == 404
        assert owner.content == other.content == unknown.content


def test_active_session_not_expired(monkeypatch):
    _idle_env(monkeypatch)
    clock = FakeClock()
    with TestClient(http_server.create_app(clock=clock)) as c:
        sid = _new_session(c)
        for _ in range(3):  # each request resets the idle timer
            clock.t += 60
            assert c.post("/mcp", json=LIST, headers=_hdr(sid)).status_code == 200
            c.portal.call(c.app.session_binding.sweep)
        assert sid in c.app.session_binding._bindings


def _blocking_stack(release, terminated, status=204):
    async def app(scope, receive, send):
        if scope["method"] == "POST" and not any(
                k == b"mcp-session-id" for k, _ in scope["headers"]):
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"mcp-session-id", b"s1")]})
            await send({"type": "http.response.body", "body": b""})
            return
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": True})
        await release.wait()
        await send({"type": "http.response.body", "body": b""})

    async def terminate(sid, host):
        terminated.append(sid)
        return status

    return app, terminate


def test_in_flight_request_and_open_stream_not_expired():
    async def run():
        clock = FakeClock()
        release, terminated = asyncio.Event(), []
        app, terminate = _blocking_stack(release, terminated)
        mw = SessionBindingMiddleware(app, 10, idle_ttl=100, clock=clock, terminate=terminate)
        await call(mw, make_scope("POST", state={"token_id": "A"}))
        assert "s1" in mw._bindings and mw._meta["s1"].active == 0
        for method in ("POST", "GET"):  # in-flight request / open GET stream
            sc = make_scope(method, headers=[("mcp-session-id", "s1")], state={"token_id": "A"})
            task = asyncio.create_task(call(mw, sc))
            await asyncio.sleep(0.01)
            assert mw._meta["s1"].active == 1
            clock.t += 1000
            assert await mw.sweep() == 0 and terminated == []
            release.set()
            await task
            release.clear()
            assert mw._meta["s1"].active == 0
            clock.t += 1  # activity at request end restarts the timer
            assert await mw.sweep() == 0
        clock.t += 101
        assert await mw.sweep() == 1 and terminated == ["s1"]
    asyncio.run(run())


def test_active_counter_decremented_when_app_raises():
    async def run():
        async def boom(scope, receive, send):
            raise RuntimeError("x")

        mw = SessionBindingMiddleware(boom, 10, idle_ttl=100, terminate=None)
        mw._bindings["s1"] = "A"
        from lexlink.http_security import _SessionMeta
        mw._meta["s1"] = _SessionMeta(last=0.0)
        mw.idle_ttl = 100
        with pytest.raises(RuntimeError):
            await call(mw, make_scope("POST", headers=[("mcp-session-id", "s1")],
                                      state={"token_id": "A"}))
        assert mw._meta["s1"].active == 0
    asyncio.run(run())


def test_failed_terminate_keeps_binding_and_retries():
    async def run():
        clock = FakeClock()
        calls, outcomes = [], iter([500, RuntimeError("boom"), 404])

        async def terminate(sid, host):
            calls.append(sid)
            o = next(outcomes)
            if isinstance(o, Exception):
                raise o
            return o

        released = []
        app, _ = _blocking_stack(asyncio.Event(), [])
        mw = SessionBindingMiddleware(app, 10, idle_ttl=100, clock=clock,
                                      terminate=terminate, release=released.append)
        await call(mw, make_scope("POST", state={"token_id": "A"}))
        clock.t += 101
        assert await mw.sweep() == 0 and mw._bindings == {"s1": "A"}   # 500
        assert not mw._meta["s1"].expiring
        assert await mw.sweep() == 0 and mw._bindings == {"s1": "A"}   # exception
        assert released == []
        assert await mw.sweep() == 1 and mw._bindings == {}            # 404 counts
        assert calls == ["s1"] * 3 and released == ["s1"]
    asyncio.run(run())


def test_requests_during_expiry_get_404_and_never_reach_app():
    async def run():
        clock = FakeClock()
        gate, reached = asyncio.Event(), []

        async def terminate(sid, host):
            await gate.wait()
            return 200

        async def app(scope, receive, send):
            if any(k == b"mcp-session-id" for k, _ in scope["headers"]):
                reached.append(1)
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"mcp-session-id", b"s1")]})
            await send({"type": "http.response.body", "body": b""})

        mw = SessionBindingMiddleware(app, 10, idle_ttl=100, clock=clock, terminate=terminate)
        await call(mw, make_scope("POST", state={"token_id": "A"}))
        clock.t += 101
        sweep = asyncio.create_task(mw.sweep())
        await asyncio.sleep(0.01)
        assert mw._meta["s1"].expiring
        for tok in ("A", "B"):
            out = await call(mw, make_scope("POST", headers=[("mcp-session-id", "s1")],
                                            state={"token_id": tok}))
            assert out[0]["status"] == 404
        assert reached == []
        gate.set()
        assert await sweep == 1
    asyncio.run(run())


def test_ttl_zero_disables_expiry(monkeypatch):
    _idle_env(monkeypatch, ttl="0")
    clock = FakeClock()
    with TestClient(http_server.create_app(clock=clock)) as c:
        sid = _new_session(c)
        clock.t += 10**7
        assert c.app.session_binding.sweep_task is None
        assert c.portal.call(c.app.session_binding.sweep) == 0
        assert c.post("/mcp", json=LIST, headers=_hdr(sid)).status_code == 200


def test_expiry_frees_slot_at_cap(monkeypatch):
    _idle_env(monkeypatch, LEXLINK_MAX_SESSIONS="1")
    clock = FakeClock()
    with TestClient(http_server.create_app(clock=clock)) as c:
        _new_session(c)
        assert c.post("/mcp", json=INIT, headers=auth_headers(TOKEN2)).status_code == 503
        clock.t += 101
        r = c.post("/mcp", json=INIT, headers=auth_headers(TOKEN2))
        assert r.status_code == 200 and "mcp-session-id" in r.headers


def test_noauth_session_expires(monkeypatch):
    monkeypatch.setenv("LEXLINK_ALLOW_NO_AUTH", "true")
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("LEXLINK_SESSION_IDLE_TTL_SEC", "100")
    box = _capture_manager(monkeypatch)
    clock = FakeClock()
    with TestClient(http_server.create_app(clock=clock)) as c:
        r = c.post("/mcp", json=INIT, headers=MCP_HEADERS)
        sid = r.headers["mcp-session-id"]
        h = {**MCP_HEADERS, "mcp-session-id": sid}
        assert c.post("/mcp", json=LIST, headers=h).status_code == 200
        clock.t += 101
        assert c.post("/mcp", json=LIST, headers=h).status_code == 404
        assert sid not in box["mcp"].session_manager._server_instances
        assert c.post("/mcp", json=INIT, headers=MCP_HEADERS).status_code == 200


def test_sweep_task_runs_and_is_cancelled_on_shutdown(monkeypatch):
    _idle_env(monkeypatch, ttl="0.2")  # interval 0.05 s, real clock
    app = http_server.create_app()
    with TestClient(app) as c:
        task = app.session_binding.sweep_task
        assert task is not None and not task.done()
        sid = _new_session(c)
        for _ in range(40):  # background sweep alone must expire it
            if sid not in app.session_binding._bindings:
                break
            import time as _t
            _t.sleep(0.05)
        assert sid not in app.session_binding._bindings
    assert task.done() and task.cancelled()
