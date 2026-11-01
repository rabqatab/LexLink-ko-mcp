"""Upstream failure behaviour through the real LawAPIClient: 500, timeout, truncated JSON.

Each failure must come back as a structured error and must not be cached (the next call
goes upstream again). Fake OC only.
"""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

import lexlink.server as server_mod
from lexlink.cache import get_cache
from lexlink.client import LawAPIClient, detect_upstream_body_error

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_OC = "unit-test-oc"
GOOD = (FIXTURES / "lsAbrv_list_trimmed.json").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    get_cache().invalidate()
    monkeypatch.setenv("OC", FAKE_OC)
    yield
    get_cache().invalidate()


def make_tool(monkeypatch, behaviours):
    """behaviours: list of callables(request) -> httpx.Response | raises; the last one repeats."""
    calls = []

    def handler(request):
        calls.append(str(request.url))
        b = behaviours[min(len(calls) - 1, len(behaviours) - 1)]
        return b(request)

    def make_client(*a, **k):
        c = LawAPIClient(base_url="http://law.test")
        c.client = httpx.Client(transport=httpx.MockTransport(handler))
        return c

    monkeypatch.setattr(server_mod, "LawAPIClient", make_client)
    asyncio.set_event_loop(asyncio.new_event_loop())
    server = server_mod.create_server()
    return (lambda **kw: server._tool_manager.get_tool("law_search").fn(**kw)), calls


def ok(body):
    return lambda req: httpx.Response(200, text=body, request=req)


def status(code, body="<html>err</html>"):
    return lambda req: httpx.Response(code, text=body, request=req)


def timeout(req):
    raise httpx.ReadTimeout("slow", request=req)


@pytest.mark.unit
@pytest.mark.parametrize("bad, code", [
    (status(500), "UPSTREAM_ERROR"),
    (status(503), "UPSTREAM_ERROR"),
    (timeout, "TIMEOUT"),
    (ok(GOOD[:80]), "UPSTREAM_ERROR"),              # JSON cut off in the middle
    (ok('{"LawSearch":{"law":[{"a":'), "UPSTREAM_ERROR"),
    (ok("[1, 2"), "UPSTREAM_ERROR"),
    (ok(""), "EMPTY_RESPONSE"),
])
def test_failure_is_structured_and_not_cached(monkeypatch, bad, code):
    tool, calls = make_tool(monkeypatch, [bad, bad, ok(GOOD)])
    first = tool(query="민법")
    assert first["status"] == "error" and first["error_code"] == code and first["message"]
    assert FAKE_OC not in json.dumps(first, ensure_ascii=False)
    tool(query="민법")
    assert len(calls) == 2                            # the failure was not served from the cache
    good = tool(query="민법")
    assert good["status"] == "ok" and len(calls) == 3
    tool(query="민법")
    assert len(calls) == 3                            # a good response is cached


@pytest.mark.unit
@pytest.mark.parametrize("body", [GOOD, "{}", "[]", '{"a": "line\nbreak"}', "일치하는 법령이 없습니다", "  "])
def test_valid_or_non_json_bodies_are_not_flagged_as_truncated(body):
    err = detect_upstream_body_error(body, "JSON", endpoint="/DRF/lawSearch.do")
    assert err is None or "invalid JSON body" not in err["message"]


@pytest.mark.unit
def test_json_check_ignores_bom_survives_deep_nesting_and_is_neutral():
    assert detect_upstream_body_error("\ufeff" + GOOD, "JSON", endpoint="/DRF/lawSearch.do") is None
    deep = "[" * 100000 + "]" * 100000                 # RecursionError inside json.loads
    err = detect_upstream_body_error(deep, "JSON", endpoint="/DRF/lawSearch.do")
    assert err["error_code"] == "UPSTREAM_ERROR" and "invalid JSON body" in err["message"]
    text = detect_upstream_body_error("[공지] 점검 중입니다", "JSON", endpoint="/DRF/lawSearch.do")
    assert text["error_code"] == "UPSTREAM_ERROR" and "끊" not in text["message"] and "truncated" not in text["message"]


@pytest.mark.unit
def test_truncated_xml_is_not_json_checked():
    assert detect_upstream_body_error("<a><b>", "XML", endpoint="/DRF/lawSearch.do") is None


NO_MATCH_PAGE = ("\r \r <!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 Transitional//EN\">\r<html><head><title>국가법령통합관리시스템</title>"
                 "<script>var a = '일치하는 x 없습니다';</script></head><body><div>일치하는 신구법 없습니다.</div></body></html>")


@pytest.mark.unit
def test_html_no_match_page_on_a_service_call_is_not_found_not_ok():
    err = detect_upstream_body_error(NO_MATCH_PAGE, "HTML", endpoint="/DRF/lawService.do", target="oldAndNew")
    assert err is not None and err["error_code"] == "NOT_FOUND"
    # a search call and a real (long) page are untouched
    assert detect_upstream_body_error(NO_MATCH_PAGE, "HTML", endpoint="/DRF/lawSearch.do", target="oldAndNew") is None
    real = "<html><body>" + "<p>구조문 신조문 표</p>" * 50 + "<p>일치하는 신구법 없습니다.</p></body></html>"
    assert detect_upstream_body_error(real, "HTML", endpoint="/DRF/lawService.do", target="oldAndNew") is None
