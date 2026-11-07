"""Operator admin API: auth, runtime token issue/revoke, store, log view, CLI."""

import json
import os
import stat
from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from lexlink import admin_cli, http_server
from lexlink.params import set_ignore_oc_override
from lexlink.raw_logger import flush_all
from lexlink.tokens import TokenRegistry, parse_named_tokens

pytestmark = pytest.mark.unit

USER = "fake-user-token-aaaaaaaaaa"
USER2 = "fake-user-token-bbbbbbbbbb"
ADMIN = "fake-admin-token-cccccccccc"
INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
               "clientInfo": {"name": "lawyer-app", "version": "1"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream",
               "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.startswith("LEXLINK_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("LEXLINK_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LEXLINK_TOKEN_STORE", str(tmp_path / "data" / "tokens.json"))
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"alice:{USER},bob:{USER2}")
    monkeypatch.setenv("LEXLINK_ADMIN_TOKENS", f"ops:{ADMIN}")
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("OC", "fake-oc-env-1234")
    yield
    set_ignore_oc_override(False)


def bearer(token, **extra):
    return {"Authorization": f"Bearer {token}", **extra}


def mcp(token, **extra):
    return {**MCP_HEADERS, **bearer(token), **extra}


def init(c, token):
    return c.post("/mcp", json=INIT, headers=mcp(token))


def issue(c, name):
    return c.post("/admin/tokens", json={"name": name}, headers=bearer(ADMIN))


def log_text(tmp_path):
    flush_all()
    d = tmp_path / "logs"
    return "".join(p.read_text() for p in sorted(d.glob("*.jsonl"))) if d.exists() else ""


# ------------------------------------------------------------------ auth

def test_admin_auth_401_403_200():
    with TestClient(http_server.create_app()) as c:
        assert c.get("/admin/tokens").status_code == 401
        assert c.get("/admin/tokens", headers=bearer("wrong")).status_code == 401
        r = c.get("/admin/tokens", headers=bearer(USER))
        assert r.status_code == 403 and r.json()["error"] == "forbidden"
        assert c.post("/admin/tokens", json={"name": "x"}, headers=bearer(USER)).status_code == 403
        assert c.get("/admin/logs", headers=bearer(USER)).status_code == 403
        assert c.get("/admin/tokens", headers=bearer(ADMIN)).status_code == 200
        assert c.get("/admin/nope", headers=bearer(ADMIN)).status_code == 404
        assert c.put("/admin/tokens", headers=bearer(ADMIN)).status_code == 405


def test_everyone_is_403_without_admin_tokens(monkeypatch):
    monkeypatch.delenv("LEXLINK_ADMIN_TOKENS")
    with TestClient(http_server.create_app()) as c:
        assert c.get("/admin/tokens", headers=bearer(USER)).status_code == 403


def test_admin_only_config_starts_and_admin_token_works_as_mcp_token(monkeypatch):
    monkeypatch.delenv("LEXLINK_AUTH_TOKENS")
    with TestClient(http_server.create_app()) as c:
        assert init(c, ADMIN).status_code == 200
        assert init(c, USER).status_code == 401


def test_admin_host_and_origin_validated():
    with TestClient(http_server.create_app()) as c:
        r = c.get("/admin/tokens", headers=bearer(ADMIN, Host="evil.test"))
        assert r.status_code == 421
        r = c.get("/admin/tokens", headers=bearer(ADMIN, Origin="https://evil.test"))
        assert r.status_code == 403


def test_admin_rate_limited_separately_from_mcp(monkeypatch):
    monkeypatch.setenv("LEXLINK_RATE_LIMIT_PER_MIN", "3")
    with TestClient(http_server.create_app()) as c:
        codes = [c.get("/admin/tokens", headers=bearer(ADMIN)).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        assert init(c, ADMIN).status_code == 200  # MCP bucket untouched


def test_no_auth_mode_has_no_admin(monkeypatch):
    for k in ("LEXLINK_AUTH_TOKENS", "LEXLINK_ADMIN_TOKENS"):
        monkeypatch.delenv(k)
    monkeypatch.setenv("LEXLINK_ALLOW_NO_AUTH", "true")
    with TestClient(http_server.create_app()) as c:
        assert c.get("/admin/tokens").status_code == 404


def test_tool_list_unchanged_by_admin():
    with TestClient(http_server.create_app()) as c:
        h = mcp(USER, **{"mcp-session-id": init(c, USER).headers["mcp-session-id"]})
        c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h)
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=h)
        data = json.loads(r.text.split("data: ", 1)[1])
        names = {t["name"] for t in data["result"]["tools"]}
        assert "law_search" in names and not any("admin" in n or "token" in n for n in names)


# ------------------------------------------------- issue / use / revoke

def test_issue_use_revoke_without_restart():
    with TestClient(http_server.create_app()) as c:
        r = issue(c, "lawyer-kim")
        assert r.status_code == 201
        body = r.json()
        token = body["token"]
        assert body["name"] == "lawyer-kim" and body["source"] == "issued"
        assert len(token) >= 32 and r.headers["cache-control"] == "no-store"
        assert init(c, token).status_code == 200  # effective immediately

        r = c.delete("/admin/tokens/lawyer-kim", headers=bearer(ADMIN))
        assert r.status_code == 200 and r.json()["revoked_at"]
        assert init(c, token).status_code == 401  # and revoked immediately
        # idempotent
        r = c.delete("/admin/tokens/lawyer-kim", headers=bearer(ADMIN))
        assert r.status_code == 200 and r.json()["already_revoked"] is True


def test_revoke_ends_existing_sessions():
    app = http_server.create_app()
    with TestClient(app) as c:
        token = issue(c, "temp").json()["token"]
        sid = init(c, token).headers["mcp-session-id"]
        other = init(c, USER).headers["mcp-session-id"]
        binding = app.session_binding
        assert sid in binding._bindings and other in binding._bindings
        r = c.delete("/admin/tokens/temp", headers=bearer(ADMIN))
        assert r.json()["sessions_ended"] == 1
        assert sid not in binding._bindings and other in binding._bindings
        # the revoked client is out, and the session id is dead for everyone
        ping = {"jsonrpc": "2.0", "id": 5, "method": "ping"}
        assert c.post("/mcp", json=ping, headers=mcp(token, **{"mcp-session-id": sid})
                      ).status_code == 401
        assert c.post("/mcp", json=ping, headers=mcp(USER, **{"mcp-session-id": sid})
                      ).status_code == 404
        # unrelated sessions keep working
        assert c.post("/mcp", json=ping, headers=mcp(USER, **{"mcp-session-id": other})
                      ).status_code == 200


def test_env_tokens_are_not_revocable():
    with TestClient(http_server.create_app()) as c:
        for name in ("ops", "alice"):
            r = c.delete(f"/admin/tokens/{name}", headers=bearer(ADMIN))
            assert r.status_code == 409 and r.json()["error"] == "env_token_not_revocable"
        assert init(c, USER).status_code == 200
        assert c.get("/admin/tokens", headers=bearer(ADMIN)).status_code == 200
        assert c.delete("/admin/tokens/ghost", headers=bearer(ADMIN)).status_code == 404


def test_name_validation_and_uniqueness():
    with TestClient(http_server.create_app()) as c:
        for bad in ("", "Upper", "-lead", "has space", "a" * 64, "한글", "a/b", None, 5):
            r = c.post("/admin/tokens", json={"name": bad}, headers=bearer(ADMIN))
            assert r.status_code == 400 and r.json()["error"] == "invalid_name", bad
        assert issue(c, "a" * 63).status_code == 201
        assert issue(c, "x_y-1").status_code == 201
        assert issue(c, "x_y-1").status_code == 409
        assert issue(c, "alice").status_code == 409  # clashes with an env token
        assert issue(c, "ops").status_code == 409
        c.delete("/admin/tokens/x_y-1", headers=bearer(ADMIN))
        assert issue(c, "x_y-1").status_code == 409  # revoked names stay reserved
        bad = c.post("/admin/tokens", content=b"not json", headers=bearer(ADMIN))
        assert bad.status_code == 400
        big = c.post("/admin/tokens", content=b"{" + b" " * 10000 + b"}", headers=bearer(ADMIN))
        assert big.status_code == 413


def test_list_shows_sources_and_never_values(tmp_path):
    with TestClient(http_server.create_app()) as c:
        token = issue(c, "carol").json()["token"]
        c.delete("/admin/tokens/carol", headers=bearer(ADMIN))
        issue(c, "dave")
        text = c.get("/admin/tokens", headers=bearer(ADMIN)).text
        rows = {r["name"]: r for r in json.loads(text)["tokens"]}
        assert rows["alice"]["source"] == "env" and rows["alice"]["revoked_at"] is None
        assert rows["ops"]["admin"] is True
        assert rows["carol"]["source"] == "issued" and rows["carol"]["revoked_at"]
        assert rows["dave"]["created_at"] and rows["dave"]["revoked_at"] is None
        assert all(len(r["token_id"]) == 12 for r in rows.values())
        for secret in (token, USER, USER2, ADMIN):
            assert secret not in text


# ------------------------------------------------------------------ store

def test_store_persists_across_restart_with_safe_permissions(tmp_path):
    store = tmp_path / "data" / "tokens.json"
    with TestClient(http_server.create_app()) as c:
        keep = issue(c, "keep").json()["token"]
        gone = issue(c, "gone").json()["token"]
        c.delete("/admin/tokens/gone", headers=bearer(ADMIN))
    assert stat.S_IMODE(store.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.parent.stat().st_mode) == 0o700
    raw = store.read_text()
    assert keep not in raw and gone not in raw and "sha256" in raw
    assert not list(store.parent.glob(".tokens-*"))  # no temp leftovers

    with TestClient(http_server.create_app()) as c:  # "restart"
        assert init(c, keep).status_code == 200
        assert init(c, gone).status_code == 401
        rows = {r["name"]: r for r in c.get(
            "/admin/tokens", headers=bearer(ADMIN)).json()["tokens"]}
        assert rows["gone"]["revoked_at"] and rows["keep"]["revoked_at"] is None


def test_corrupt_or_clashing_store_fails_closed(tmp_path):
    store = tmp_path / "data" / "tokens.json"
    store.parent.mkdir()
    store.write_text("{ nope")
    with pytest.raises(RuntimeError, match="token store"):
        http_server.create_app()
    store.write_text(json.dumps({"version": 1, "tokens": [{
        "name": "alice", "sha256": "0" * 64, "created_at": None, "revoked_at": None}]}))
    with pytest.raises(RuntimeError, match="clash"):
        http_server.create_app()


def test_failed_store_write_changes_nothing(tmp_path, monkeypatch):
    with TestClient(http_server.create_app()) as c:
        monkeypatch.setattr(TokenRegistry, "_write_store",
                            lambda self, data: (_ for _ in ()).throw(OSError("disk full")))
        r = issue(c, "zed")
        assert r.status_code == 503
        monkeypatch.undo()
        assert "zed" not in c.get("/admin/tokens", headers=bearer(ADMIN)).text


def test_registry_unit():
    reg = TokenRegistry([("u", "tok-u")], [("a", "tok-a")], None)
    assert reg.authenticate(b"tok-u").admin is False
    assert reg.authenticate(b"tok-a").admin is True
    assert reg.authenticate(b"") is None and reg.authenticate(b"tok") is None
    assert reg.name_for(reg.authenticate(b"tok-u").token_id) == "u"
    with pytest.raises(RuntimeError):
        TokenRegistry([("x", "t")], [("x", "t2")], None)
    with pytest.raises(RuntimeError):
        parse_named_tokens("a:1,b:1", "VAR")


# --------------------------------------------------------------------- logs

def test_logs_filters_and_token_names(tmp_path):
    with TestClient(http_server.create_app()) as c:
        for token in (USER, USER, USER2):
            sid = init(c, token).headers["mcp-session-id"]
            c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                   headers=mcp(token, **{"mcp-session-id": sid}))
        alice_id = next(r["token_id"] for r in c.get(
            "/admin/tokens", headers=bearer(ADMIN)).json()["tokens"] if r["name"] == "alice")

        r = c.get("/admin/logs", headers=bearer(ADMIN))
        assert r.status_code == 200
        body = r.json()
        mcp_rows = [x for x in body["rows"] if not x["method"].startswith("admin:")]
        assert len(mcp_rows) == 6
        assert all(x["token_name"] in ("alice", "bob") for x in mcp_rows)
        ts = [x["timestamp"] for x in body["rows"]]
        assert ts == sorted(ts, reverse=True)

        by_name = c.get("/admin/logs", params={"token": "alice"}, headers=bearer(ADMIN)).json()
        assert by_name["matched"] == 4 and {x["token_id"] for x in by_name["rows"]} == {alice_id}
        by_id = c.get("/admin/logs", params={"token_id": alice_id}, headers=bearer(ADMIN)).json()
        assert by_id["matched"] == 4
        both = c.get("/admin/logs", params={"token": "bob", "method": "tools/list"},
                     headers=bearer(ADMIN)).json()
        assert both["matched"] == 1 and both["rows"][0]["token_name"] == "bob"
        cl = c.get("/admin/logs", params={"client_name": "lawyer-app", "method": "initialize"},
                   headers=bearer(ADMIN)).json()
        assert cl["matched"] == 3
        assert c.get("/admin/logs", params={"client_name": "nobody"},
                     headers=bearer(ADMIN)).json()["rows"] == []
        assert c.get("/admin/logs", params={"token": "ghost"},
                     headers=bearer(ADMIN)).json()["rows"] == []
        st = c.get("/admin/logs", params={"status": "ok", "tool_name": "law_search"},
                   headers=bearer(ADMIN)).json()
        assert st["rows"] == []
        lim = c.get("/admin/logs", params={"limit": 2}, headers=bearer(ADMIN)).json()
        assert lim["returned"] == 2 and lim["matched"] >= 6

        today = date.today().isoformat()
        d = c.get("/admin/logs", params={"date": today, "token": "bob"}, headers=bearer(ADMIN))
        assert d.json()["matched"] == 2
        rng = c.get("/admin/logs", params={
            "from": (date.today() - timedelta(days=3)).isoformat(), "to": today,
            "token": "bob"}, headers=bearer(ADMIN))
        assert rng.json()["matched"] == 2
        old = c.get("/admin/logs", params={"date": "2001-01-01"}, headers=bearer(ADMIN))
        assert old.json()["rows"] == []


def test_logs_bad_params():
    with TestClient(http_server.create_app()) as c:
        for params in ({"date": "yesterday"}, {"limit": 0}, {"limit": 5000}, {"limit": "x"},
                       {"date": "2026-01-01", "from": "2026-01-01"},
                       {"from": "2026-02-01", "to": "2026-01-01"},
                       {"from": "2020-01-01", "to": "2026-01-01"}):
            r = c.get("/admin/logs", params=params, headers=bearer(ADMIN))
            assert r.status_code == 400, params


def test_admin_requests_logged_without_secrets(tmp_path):
    with TestClient(http_server.create_app()) as c:
        token = issue(c, "erin").json()["token"]
        c.get("/admin/tokens", headers=bearer(ADMIN))
        c.delete("/admin/tokens/erin", headers=bearer(ADMIN))
        c.get("/admin/tokens", headers=bearer(USER))  # 403 is logged too
        c.get("/admin/logs", params={"token": "alice"}, headers=bearer(ADMIN))
        init(c, token)  # 401, never logged
    text = log_text(tmp_path)
    rows = [json.loads(line) for line in text.splitlines()]
    methods = [r["method"] for r in rows]
    assert methods == ["admin:issue_token", "admin:list_tokens", "admin:revoke_token",
                       "admin:list_tokens", "admin:logs"]
    assert rows[0]["admin_target"] == "erin" and rows[0]["http_status"] == 201
    assert rows[3]["http_status"] == 403 and rows[3]["status"] == "error"
    for secret in (token, USER, USER2, ADMIN, "fake-oc-env-1234"):
        assert secret not in text
    assert "alice" not in text  # query values are not logged either


def test_admin_listing_and_logs_never_contain_token_values(tmp_path):
    with TestClient(http_server.create_app()) as c:
        token = issue(c, "frank").json()["token"]
        init(c, token)
        out = c.get("/admin/logs", headers=bearer(ADMIN)).text
        out += c.get("/admin/tokens", headers=bearer(ADMIN)).text
    for secret in (token, USER, USER2, ADMIN):
        assert secret not in out and secret not in log_text(tmp_path)


# ---------------------------------------------------------------------- CLI

def test_cli_issue_prints_token_only_on_stdout(monkeypatch, capsys):
    monkeypatch.setenv("LEXLINK_ADMIN_URL", "https://x.test")
    monkeypatch.setenv("LEXLINK_ADMIN_TOKEN", ADMIN)
    seen = {}

    def fake(method, path, **kw):
        seen.update(method=method, path=path, **kw)
        return 201, {"name": "g", "token_id": "abc123abc123", "token": "SECRET-ISSUED"}

    monkeypatch.setattr(admin_cli, "_request", fake)
    assert admin_cli.main(["tokens", "issue", "g"]) == 0
    out, err = capsys.readouterr()
    assert out == "SECRET-ISSUED\n" and "SECRET-ISSUED" not in err
    assert seen == {"method": "POST", "path": "/admin/tokens", "body": {"name": "g"}}


def test_cli_against_live_app(monkeypatch, capsys):
    """Run the CLI's real HTTP code against the app through a stub urlopen."""
    monkeypatch.setenv("LEXLINK_ADMIN_URL", "http://testserver")
    monkeypatch.setenv("LEXLINK_ADMIN_TOKEN", ADMIN)
    import io
    import urllib.error

    with TestClient(http_server.create_app()) as c:
        def fake_urlopen(req, timeout=None):
            r = c.request(req.get_method(), req.full_url.replace("http://testserver", ""),
                          content=req.data, headers=dict(req.header_items()))
            if r.status_code >= 400:
                raise urllib.error.HTTPError(req.full_url, r.status_code, "", {},
                                             io.BytesIO(r.content))

            class Resp:
                status = r.status_code
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self): return r.content
            return Resp()

        monkeypatch.setattr(admin_cli.urllib.request, "urlopen", fake_urlopen)
        assert admin_cli.main(["tokens", "issue", "henry"]) == 0
        token = capsys.readouterr().out.strip()
        assert init(c, token).status_code == 200
        assert admin_cli.main(["tokens", "list"]) == 0
        listing = capsys.readouterr().out
        assert "henry" in listing and token not in listing and ADMIN not in listing
        assert admin_cli.main(["logs", "--token", "henry", "--limit", "5"]) == 0
        assert '"token_name": "henry"' in capsys.readouterr().out
        assert admin_cli.main(["tokens", "revoke", "henry"]) == 0
        capsys.readouterr()
        assert admin_cli.main(["tokens", "revoke", "alice"]) == 1
        assert "env_token_not_revocable" in capsys.readouterr().err
        assert init(c, token).status_code == 401


def test_cli_requires_env(monkeypatch, capsys):
    monkeypatch.delenv("LEXLINK_ADMIN_URL", raising=False)
    monkeypatch.delenv("LEXLINK_ADMIN_TOKEN", raising=False)
    with pytest.raises(SystemExit) as e:
        admin_cli.main(["tokens", "list"])
    assert e.value.code == 2
