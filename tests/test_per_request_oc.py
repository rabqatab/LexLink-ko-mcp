"""Per-request OC (X-LexLink-OC) through the real HTTP app with a mocked upstream."""
import concurrent.futures as cf
import json
import os
import threading
import time
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from lexlink import http_server, server as server_mod
from lexlink.params import set_ignore_oc_override

TOKEN = "fake-token-aaaaaaaaaaaa"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}


def auth_headers():
    return {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}"}


ENV_OC = "fake-env-oc-1111"
HDR_OC = "fake-user-oc-2222"
HDR_OC2 = "fake-user-oc-3333"
ARG_OC = "fake-arg-oc-4444"
ALL = (ENV_OC, HDR_OC, HDR_OC2, ARG_OC)
LAW = {"LawSearch": {"law": [{"법령명한글": "민법", "법령일련번호": "1", "법령ID": "1", "현행연혁코드": "현행",
                              "시행일자": "20240101", "공포일자": "20240101", "법령구분명": "법률",
                              "법령상세링크": "/DRF/lawService.do?OC={oc}&target=law&MST=1"}],
                      "totalCnt": 1, "page": 1}}


@pytest.fixture
def app_env(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.startswith("LEXLINK_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("LEXLINK_AUTH_TOKENS", f"a:{TOKEN}")
    monkeypatch.setenv("LEXLINK_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LEXLINK_LOG_BODIES", "true")
    monkeypatch.setenv("OC", ENV_OC)
    monkeypatch.setenv("LEXLINK_ALLOWED_HOSTS", "testserver")
    seen = []  # (path, OC query param) as received by the mocked law.go.kr
    mode = {"auth_fail": False, "delay": 0.0}
    lock = threading.Lock()

    def handler(request: httpx.Request):
        oc = request.url.params.get("OC")
        with lock:
            seen.append((request.url.path, oc))
        if mode["delay"]:
            time.sleep(mode["delay"])
        if mode["auth_fail"]:
            return httpx.Response(200, text=f"<Law>사용자 정보 검증에 실패하였습니다. OC={oc}</Law>", request=request)
        body = json.dumps(LAW, ensure_ascii=False).replace("{oc}", oc or "")
        return httpx.Response(200, text=body, request=request)

    real = server_mod.LawAPIClient

    def make_client(*a, **k):
        c = real(base_url="http://law.test")
        c.client = httpx.Client(transport=httpx.MockTransport(handler))
        return c

    monkeypatch.setattr(server_mod, "LawAPIClient", make_client)
    from lexlink.cache import get_cache
    get_cache().invalidate()
    yield seen, mode, tmp_path
    set_ignore_oc_override(False)
    get_cache().invalidate()


def _session(c):
    r = c.post("/mcp", json=INIT, headers=auth_headers())
    sid = r.headers["mcp-session-id"]
    h = {**auth_headers(), "mcp-session-id": sid}
    c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h)
    return h


def _call(c, h, name, args, oc=None, rid=10):
    hh = dict(h)
    if oc is not None:
        hh["X-LexLink-OC"] = oc
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                             "params": {"name": name, "arguments": args}}, headers=hh)
    assert r.status_code == 200, r.text
    text = r.text
    data = next((ln[6:] for ln in text.splitlines() if ln.startswith("data: ")), text)
    return json.loads(data)["result"], text


def _flag(monkeypatch, on=True):
    monkeypatch.setenv("LEXLINK_ACCEPT_OC_HEADER", "true" if on else "false")


def _logs(tmp_path):
    return "\n".join(p.read_text() for p in Path(tmp_path / "logs").glob("*.jsonl"))


def _stub_citation(monkeypatch):
    async def fake(**kw):
        return {"success": True, "citations": []}
    monkeypatch.setattr("lexlink.citation.extract_article_citations", fake)


def test_header_oc_used_for_every_upstream_call_incl_chain_and_citation(monkeypatch, app_env):
    seen, mode, tmp = app_env
    _flag(monkeypatch)
    _stub_citation(monkeypatch)
    with TestClient(http_server.create_app()) as c:
        h = _session(c)
        res, _ = _call(c, h, "law_search", {"query": "민법", "oc": ARG_OC}, HDR_OC)
        assert seen and {o for _, o in seen} == {HDR_OC}
        assert res["_meta"]["lexlink/upstream_calls"] == len(seen)
        n = len(seen)
        _call(c, h, "chain_full_research", {"query": "임대차 보증금 반환"}, HDR_OC, rid=11)
        assert len(seen) > n + 1
        assert {o for _, o in seen[n:]} == {HDR_OC}
        n = len(seen)
        _call(c, h, "article_citation", {"mst": "1", "law_name": "민법", "article": 3}, HDR_OC, rid=12)
        assert len(seen) > n and {o for _, o in seen[n:]} == {HDR_OC}


def test_no_header_uses_env_oc_and_flag_off_ignores_header(monkeypatch, app_env):
    seen, mode, tmp = app_env
    _flag(monkeypatch)
    with TestClient(http_server.create_app()) as c:
        h = _session(c)
        _call(c, h, "law_search", {"query": "민법", "oc": ARG_OC})
        assert {o for _, o in seen} == {ENV_OC}
    seen.clear()
    _flag(monkeypatch, False)
    with TestClient(http_server.create_app()) as c:
        h = _session(c)
        _call(c, h, "law_search", {"query": "형법"}, HDR_OC, rid=20)
        assert {o for _, o in seen} == {ENV_OC}
    assert '"oc_source": "server"' in _logs(tmp)


@pytest.mark.parametrize("bad", ["bad value", "a" * 65, "x;y", "x/y"])
def test_invalid_header_is_validation_error_without_echo(monkeypatch, app_env, bad):
    seen, mode, tmp = app_env
    _flag(monkeypatch)
    _stub_citation(monkeypatch)
    with TestClient(http_server.create_app()) as c:
        h = _session(c)
        for i, (tool, args) in enumerate((("law_search", {"query": "민법"}),
                                          ("article_citation", {"mst": "1", "law_name": "민법", "article": 3}))):
            res, text = _call(c, h, tool, args, bad, rid=40 + i)
            assert "VALIDATION_ERROR" in text  # LexLink reports tool errors as a result dict
            assert bad not in text
    assert seen == []
    assert bad not in _logs(tmp)


def test_concurrent_sessions_do_not_cross(monkeypatch, app_env):
    seen, mode, tmp = app_env
    mode["delay"] = 0.05
    _flag(monkeypatch)
    with TestClient(http_server.create_app()) as c:
        hs = [_session(c), _session(c)]
        seen.clear()

        def run(i):
            for k in range(3):  # distinct queries so the response cache cannot hide a call
                _call(c, hs[i % 2], "law_search", {"query": f"q{i}-{k}"}, (HDR_OC, HDR_OC2)[i % 2],
                      rid=100 + i * 10 + k)
        with cf.ThreadPoolExecutor(6) as ex:
            list(ex.map(run, range(6)))
    assert {o for _, o in seen} == {HDR_OC, HDR_OC2}
    assert sum(o == HDR_OC for _, o in seen) == 9 and sum(o == HDR_OC2 for _, o in seen) == 9


def test_no_leakage_and_oc_auth_failed_error(monkeypatch, app_env):
    seen, mode, tmp = app_env
    _flag(monkeypatch)
    monkeypatch.setenv("LEXLINK_LOG_ARGUMENTS", "true")
    with TestClient(http_server.create_app()) as c:
        h = _session(c)
        res, text = _call(c, h, "law_search", {"query": "민법"}, HDR_OC)
        assert res.get("isError") is not True
        mode["auth_fail"] = True
        res2, text2 = _call(c, h, "law_search", {"query": "형법", "oc": ARG_OC}, HDR_OC, rid=30)
        err = res2["structuredContent"] if "structuredContent" in res2 else json.loads(res2["content"][0]["text"])
        assert err["error_code"] == "OC_AUTH_FAILED" and err["oc_source"] == "header"
        assert any("open.law.go.kr" in x and "X-LexLink-OC" in x for x in err["hints"])
        res3, text3 = _call(c, h, "law_search", {"query": "상법"}, rid=31)
        err3 = res3["structuredContent"] if "structuredContent" in res3 else json.loads(res3["content"][0]["text"])
        assert err3["error_code"] == "OC_AUTH_FAILED" and err3["oc_source"] == "server"
        for needle in ALL:
            assert needle not in text and needle not in text2 and needle not in text3
    log = _logs(tmp)
    assert log
    for needle in ALL:
        assert needle not in log
    assert '"oc_source": "header"' in log and '"oc_source": "server"' in log


def test_errors_are_not_cached_and_cache_key_has_no_oc(monkeypatch, app_env):
    from lexlink.cache import _make_cache_key
    assert _make_cache_key("law", {"OC": "a", "query": "x"}) == _make_cache_key("law", {"OC": "b", "query": "x"})
    seen, mode, tmp = app_env
    _flag(monkeypatch)
    mode["auth_fail"] = True
    with TestClient(http_server.create_app()) as c:
        h = _session(c)
        _call(c, h, "law_search", {"query": "민법"}, HDR_OC)
        mode["auth_fail"] = False
        res, text = _call(c, h, "law_search", {"query": "민법"}, HDR_OC2, rid=11)
        assert res.get("isError") is not True
    assert seen[-1][1] == HDR_OC2
