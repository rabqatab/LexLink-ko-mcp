"""Follow-up fixes: resolver citations, OC removal, lawService NOT_FOUND, id->rank, cache type."""

import asyncio
import json
import logging

import httpx
import pytest

import lexlink.server as server_mod
from lexlink._helpers import (
    handle_tool_error, rename_row_ids_to_rank, run_coroutine_sync, run_search,
)
from lexlink.cache import get_cache
from lexlink.client import LawAPIClient, detect_upstream_body_error, redact_oc
from lexlink.errors import ErrorCode, create_error_response

from test_amendment import FakeClient as AmendmentFakeClient

FAKE_OC = "unit-test-oc"
SERVICE = "/DRF/lawService.do"
SEARCH = "/DRF/lawSearch.do"


@pytest.fixture(autouse=True)
def _fresh_cache():
    get_cache().invalidate()
    yield
    get_cache().invalidate()


# --- item 1: legal_resolver citations -----------------------------------------

AI_BODY = json.dumps({"aiSearch": {"법령조문": [
    {"법령명": "저작권법", "법령ID": "000798", "조문번호": "35", "조문제목": "공정이용",
     "조문내용": "내용"},
]}}, ensure_ascii=False)


class ResolverFake(AmendmentFakeClient):
    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == SEARCH and params.get("target") == "aiSearch":
            return self._ok(AI_BODY)
        return super().get(endpoint, params, response_type)


@pytest.fixture
def resolver_tools(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", ResolverFake)
    monkeypatch.setenv("OC", FAKE_OC)
    ResolverFake.calls = []
    server = server_mod.create_server()
    return lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)


# Real shape of CitationResult.to_dict() / Citation.to_dict()
REAL_CITATIONS = {
    "success": True, "citations": [
        {"type": "external", "raw_text": "「민법」 제3조", "ref_id": "x",
         "target_law_name": "민법", "target_article": 3},
        {"type": "internal", "raw_text": "제5조", "ref_id": "y", "target_article": 5},
    ],
}


@pytest.mark.unit
def test_run_coroutine_sync_with_and_without_loop():
    async def coro():
        return 7

    assert run_coroutine_sync(coro()) == 7

    async def outer():
        return run_coroutine_sync(coro())

    assert asyncio.run(outer()) == 7


@pytest.mark.unit
def test_legal_resolver_citations_inside_running_loop(monkeypatch, resolver_tools):
    import lexlink.citation as citation_mod

    async def fake_extract(**kwargs):
        return REAL_CITATIONS

    monkeypatch.setattr(citation_mod, "extract_article_citations", fake_extract)

    async def run():
        return resolver_tools("legal_resolver", situation="저작물 이용")

    out = asyncio.run(run())
    assert out["status"] == "ok", out
    assert "warnings" not in out
    assert [c["to_law"] for c in out["citations"]] == ["민법", "저작권법"]
    assert [c["type"] for c in out["citations"]] == ["external", "internal"]
    assert out["citations"][0]["to_article"] == "제3조"


@pytest.mark.unit
def test_legal_resolver_citation_failure_is_reported(monkeypatch, resolver_tools):
    import lexlink.citation as citation_mod

    async def boom(**kwargs):
        raise RuntimeError(f"boom OC={FAKE_OC}&x=1")

    monkeypatch.setattr(citation_mod, "extract_article_citations", boom)

    async def run():
        return resolver_tools("legal_resolver", situation="저작물 이용")

    out = asyncio.run(run())
    assert out["status"] == "ok"
    assert out["citations"] == []
    assert len(out["warnings"]) == 1
    assert "RuntimeError" in out["warnings"][0]
    assert FAKE_OC not in out["warnings"][0]


@pytest.mark.unit
def test_chain_full_research_carries_warnings(monkeypatch, resolver_tools):
    import lexlink.citation as citation_mod

    async def boom(**kwargs):
        raise ValueError("nope")

    monkeypatch.setattr(citation_mod, "extract_article_citations", boom)
    out = resolver_tools("chain_full_research", query="저작물 이용")
    assert out["status"] == "ok", out
    assert any("ValueError" in w for w in out["warnings"])


# --- item 2: OC removal ---------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("src,expected", [
    ('<input type="hidden" name="OC" value="abc">', '<input type="hidden" name="OC" value="">'),
    ("<input value='abc' name='OC'>", '<input value="" name=\'OC\'>'),
    ('<input name=OC value=abc type=hidden>', '<input name=OC value="" type=hidden>'),
    ("OC = 'abc';", "OC = '';"),
    ('{"OC":"abc","a":1}', '{"OC":"","a":1}'),
    ('{oc: "abc"}', '{oc: ""}'),
    ('<input name="DOC" value="x">', '<input name="DOC" value="x">'),
    ('DOC="x"', 'DOC="x"'),
])
def test_redact_oc_structural(src, expected):
    assert redact_oc(src) == expected


@pytest.mark.unit
def test_redact_oc_short_literal_is_delimited_only():
    assert redact_oc("the law of law", "law") == "the law of law"
    assert redact_oc("법 g4c 조항", "g4c") == "법 g4c 조항"
    assert redact_oc('"x":"g4c" a=g4c&b', "g4c") == '"x":"***" a=***&b'
    assert redact_oc("tok unit-test-oc", FAKE_OC) == "tok ***"


@pytest.mark.unit
def test_drlaw_search_hidden_oc_input_removed(monkeypatch):
    html = (f'<html><body><form><input type="hidden" name="OC" value="{FAKE_OC}">'
            f'<script>var OC = "{FAKE_OC}";</script></form></body></html>')

    def handler(request):
        return httpx.Response(200, text=html, request=request)

    def make_client(*a, **k):
        c = LawAPIClient(base_url="http://law.test")
        c.client = httpx.Client(transport=httpx.MockTransport(handler))
        return c

    monkeypatch.setattr(server_mod, "LawAPIClient", make_client)
    monkeypatch.setenv("OC", FAKE_OC)
    server = server_mod.create_server()
    out = server._tool_manager.get_tool("drlaw_search").fn()
    assert FAKE_OC not in json.dumps(out, ensure_ascii=False)
    assert 'name="OC"' in out["raw_content"]


@pytest.mark.unit
@pytest.mark.parametrize("exc_cls", [ValueError, RuntimeError])
def test_handle_tool_error_redacts_sync_and_async(exc_cls, caplog):
    @handle_tool_error
    def sync_tool(oc=None):
        raise exc_cls(f"fail https://x/y?OC={FAKE_OC}&a=1 and {FAKE_OC}")

    @handle_tool_error
    async def async_tool(oc=None):
        raise exc_cls(f"fail https://x/y?OC={FAKE_OC}&a=1 and {FAKE_OC}")

    with caplog.at_level(logging.DEBUG):
        a = sync_tool(oc=FAKE_OC)
        b = asyncio.run(async_tool(oc=FAKE_OC))
    for out in (a, b):
        assert out["status"] == "error"
        assert FAKE_OC not in json.dumps(out, ensure_ascii=False)
    assert FAKE_OC not in caplog.text
    assert FAKE_OC not in "".join(str(r.exc_text) for r in caplog.records)


# --- item 3: lawService bodyless success ----------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("body", ["", "  \n"])
def test_blank_service_body_is_not_found_but_search_stays_empty(body):
    err = detect_upstream_body_error(body, "JSON", target="expc", endpoint=SERVICE)
    assert err["error_code"] == ErrorCode.NOT_FOUND
    err = detect_upstream_body_error(body, "JSON", target="expc", endpoint=SEARCH)
    assert err["error_code"] == ErrorCode.EMPTY_RESPONSE


@pytest.mark.unit
@pytest.mark.parametrize("body", [
    "{}", '{"A": {}}', '{"A": "", "B": null, "C": []}',
])
def test_empty_json_object_on_service_is_not_found(body):
    err = detect_upstream_body_error(body, "JSON", target="ttSpecialDecc", endpoint=SERVICE)
    assert err["error_code"] == ErrorCode.NOT_FOUND
    assert all("_search" not in h for h in err["hints"])
    # starts with "{" even when XML was requested
    assert detect_upstream_body_error(body, "XML", target="x", endpoint=SERVICE)["error_code"] == ErrorCode.NOT_FOUND
    # not on search, not for non-empty content
    assert detect_upstream_body_error(body, "JSON", endpoint=SEARCH) is None
    assert detect_upstream_body_error('{"A": {"x": "1"}}', "JSON", endpoint=SERVICE) is None


@pytest.mark.unit
def test_generic_no_match_hint_is_neutral():
    err = detect_upstream_body_error(
        '{"Law":"일치하는 결정례가 없습니다."}', "JSON", target="ttSpecialDecc", endpoint=SERVICE)
    assert err["error_code"] == ErrorCode.NOT_FOUND
    assert all("ttSpecialDecc_search" not in h for h in err["hints"])
    assert any("실제 키" in h for h in err["hints"])


class MissingMstFake(AmendmentFakeClient):
    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == SERVICE and params.get("target") == "law" and params.get("MST") == "999":
            return create_error_response(
                error_code=ErrorCode.NOT_FOUND, message="일치하는 법령이 없습니다. MST", hints=[])
        return super().get(endpoint, params, response_type)


@pytest.mark.unit
def test_article_amendment_diff_still_tries_next_mst(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", MissingMstFake)
    monkeypatch.setenv("OC", FAKE_OC)
    server = server_mod.create_server()
    out = server._tool_manager.get_tool("article_amendment_diff").fn(
        mst_old="999", mst_new="283335", article=35, article_branch=5)
    assert out["status"] == "ok", out
    assert out["old_version"]["note"]
    assert out["new_version"]["text"]


# --- item 4: id -> rank ---------------------------------------------------------

@pytest.mark.unit
def test_rename_rows_list_single_and_no_id():
    resp = {
        "raw_content": '{"id": "1"}',
        "ranked_data": {
            "a": [{"id": "1", "x": 1}, {"x": 2}],
            "b": {"id": "2", "y": 1},
            "total": "3",
        },
    }
    out = rename_row_ids_to_rank(resp)
    assert out["ranked_data"]["a"] == [{"rank": "1", "x": 1}, {"x": 2}]
    assert out["ranked_data"]["b"] == {"rank": "2", "y": 1}
    assert out["raw_content"] == '{"id": "1"}'
    assert "raw_content" in out["id_note"]

    none = rename_row_ids_to_rank({"raw_content": "x", "ranked_data": {"a": [{"x": 1}]}})
    assert "id_note" not in none and none["ranked_data"] == {"a": [{"x": 1}]}
    slim = rename_row_ids_to_rank({"ranked_data": {"a": [{"id": "1"}]}})
    assert "id_note" not in slim and slim["ranked_data"]["a"] == [{"rank": "1"}]


class SearchFake(AmendmentFakeClient):
    pass


@pytest.mark.unit
def test_run_search_renames_but_keeps_raw_content():
    client = SearchFake()
    out = run_search(
        get_client=lambda: client, target="eflaw", query="저작권법",
        snake_params={"oc": FAKE_OC, "target": "eflaw", "query": "저작권법", "type": "JSON"},
        response_type="JSON", display=5, ranking_field="법령명한글", list_type="law",
    )
    rows = out["ranked_data"]["law"]
    assert rows and all("id" not in r and "rank" in r for r in rows)
    raw_rows = json.loads(out["raw_content"])["LawSearch"]["law"]
    assert all("id" in r and "rank" not in r for r in raw_rows)
    assert out["id_note"].startswith("raw_content의 id는 행 번호")


@pytest.mark.unit
def test_cgm_expc_search_raw_rewrite_keeps_id(monkeypatch):
    rows = [{"id": str(i + 1), "안건명": f"퇴직금 {i}", "법령해석일련번호": str(100 + i)} for i in range(5)]
    body = json.dumps({"CgmExpc": {"totalCnt": "5", "cgmExpc": rows}}, ensure_ascii=False)

    class F:
        def __init__(self, *a, **k):
            pass

        def get(self, endpoint, params, response_type="JSON"):
            return {"status": "ok", "upstream_type": "JSON", "raw_content": body}

    monkeypatch.setattr(server_mod, "LawAPIClient", F)
    monkeypatch.setenv("OC", FAKE_OC)
    server = server_mod.create_server()
    out = server._tool_manager.get_tool("cgm_expc_search").fn(
        ministry="고용노동부", query="*", display=2)
    assert len(out["ranked_data"]["cgmExpc"]) == 2
    assert all("rank" in r and "id" not in r for r in out["ranked_data"]["cgmExpc"])
    raw_rows = json.loads(out["raw_content"])["CgmExpc"]["cgmExpc"]
    assert len(raw_rows) == 2 and all("id" in r for r in raw_rows)
    assert "id_note" in out


# --- cache key includes type ----------------------------------------------------

@pytest.mark.unit
def test_service_tools_send_type(monkeypatch):
    seen = []

    class F:
        def __init__(self, *a, **k):
            pass

        def get(self, endpoint, params, response_type="JSON"):
            seen.append(dict(params))
            return {"status": "ok", "upstream_type": response_type, "raw_content": "<x/>"}

    monkeypatch.setattr(server_mod, "LawAPIClient", F)
    monkeypatch.setenv("OC", FAKE_OC)
    server = server_mod.create_server()
    call = lambda n, **kw: server._tool_manager.get_tool(n).fn(**kw)
    call("elaw_service", id="1", type="XML")
    call("admrul_service", id="1", type="XML")
    call("lsDelegated_service", id="1", type="XML")
    call("admrul_search", query="학교", type="XML")
    call("lnkLs_search", query="자동차관리법", type="XML")
    call("lnkLsOrdJo_search", knd="002118", type="XML")
    call("lnkDep_search", org="1400000", type="XML")
    assert len(seen) == 7
    assert all(p.get("type") == "XML" for p in seen), seen
