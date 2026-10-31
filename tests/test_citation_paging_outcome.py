"""article_citation verification, ranked paging, zero-result guidance, outcome heuristic."""

import asyncio
import json

import pytest

import lexlink.citation as citation_mod
import lexlink.server as server_mod
from lexlink._helpers import ToolValidationError, run_search
from lexlink.errors import ErrorCode, create_error_response
from lexlink.cache import ResponseCache
from lexlink.cache import get_cache
from lexlink.citation import CitationExtractor

FAKE_OC = "unit-test-oc"


@pytest.fixture(autouse=True)
def _fresh_cache():
    get_cache().invalidate()
    yield
    get_cache().invalidate()


# ------------------------------------------------------------ article_citation

def _law_body(name="민법", with_article=True):
    body = {"법령": {"기본정보": {"법령명_한글": name}}}
    if with_article:
        body["법령"]["조문"] = {"조문단위": [{"조문번호": "3", "조문내용": "제3조"}]}
    return json.dumps(body, ensure_ascii=False)


class CitationClient:
    calls: list = []
    body = _law_body()
    error = None

    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        CitationClient.calls.append((endpoint, dict(params)))
        if CitationClient.error:
            return CitationClient.error
        return {"status": "ok", "request_id": "r", "raw_content": CitationClient.body}


@pytest.fixture
def cite(monkeypatch):
    CitationClient.calls = []
    CitationClient.body = _law_body()
    CitationClient.error = None
    extracted = []

    async def fake_extract(mst, law_name, article, article_branch=0):
        extracted.append((mst, law_name, article, article_branch))
        return {"success": True, "citation_count": 0, "citations": []}

    monkeypatch.setattr(server_mod, "LawAPIClient", CitationClient)
    monkeypatch.setattr(citation_mod, "extract_article_citations", fake_extract)
    monkeypatch.setenv("OC", FAKE_OC)
    server = server_mod.create_server()
    fn = server._tool_manager.get_tool("article_citation").fn

    def call(**kw):
        return asyncio.run(fn(**kw))
    call.extracted = extracted
    return call


@pytest.mark.unit
def test_citation_verified_ok_uses_branch_jo(cite):
    out = cite(mst="1", law_name="민 법", article=37, article_branch=2)
    assert out["success"] is True and "warnings" not in out
    (endpoint, params), = CitationClient.calls
    assert endpoint == "/DRF/lawService.do"
    assert params["target"] == "law" and params["MST"] == "1" and params["JO"] == "003702"
    assert cite.extracted == [("1", "민 법", 37, 2)]


@pytest.mark.unit
def test_citation_name_mismatch_is_validation_error(cite):
    CitationClient.body = _law_body("난민법")
    out = cite(mst="1", law_name="민법", article=3)
    assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR"
    assert out["success"] is False
    assert "난민법" in out["message"] and "민법" in out["message"]
    assert cite.extracted == []


@pytest.mark.unit
def test_citation_missing_article(cite):
    CitationClient.body = _law_body(with_article=False)
    out = cite(mst="1", law_name="민법", article=9999)
    assert out["error_code"] == "ARTICLE_NOT_FOUND" and out["success"] is False
    assert cite.extracted == []


@pytest.mark.unit
def test_citation_upstream_not_found_passes_through(cite):
    CitationClient.error = {"status": "error", "error_code": "NOT_FOUND", "message": "x"}
    out = cite(mst="999", law_name="민법", article=3)
    assert out["error_code"] == "NOT_FOUND"
    assert cite.extracted == []


@pytest.mark.unit
def test_citation_without_oc_skips_verification_with_warning(cite, monkeypatch):
    monkeypatch.delenv("OC", raising=False)
    out = cite(mst="1", law_name="민법", article=3)
    assert CitationClient.calls == []
    assert out["success"] is True
    assert out["warnings"] == ["OC 없음: mst/법령명 일치와 조문 존재를 확인하지 못했습니다"]


@pytest.mark.unit
def test_lsi_seq_cache_is_keyed_by_mst_and_name(monkeypatch):
    seen = []

    class Resp:
        status_code = 200
        def __init__(self, text):
            self.text = text

    class FakeHttp:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def get(self, url, **k):
            seen.append(url)
            return Resp("lsiSeq=111" if "%EB%AF%BC%EB%B2%95" in url and "%EB%82%9C" not in url else "lsiSeq=222")

    monkeypatch.setattr(citation_mod.httpx, "AsyncClient", FakeHttp)
    ex = CitationExtractor()
    a = asyncio.run(ex.get_lsi_seq("민법", "1"))
    b = asyncio.run(ex.get_lsi_seq("난민법", "1"))
    again = asyncio.run(ex.get_lsi_seq("민법", "1"))
    assert (a, b, again) == ("111", "222", "111")
    assert len(seen) == 2


# ------------------------------------------------------------------- paging

TOTAL = 45


def _name(i):
    return f"민법 시행 규칙 {i:03d}"


class PagedClient:
    """Mimics upstream: page size from display (JSON) / numOfRows (XML), page honoured."""

    def __init__(self, total=TOTAL):
        self.total = total
        self.calls = []

    def get(self, endpoint, params, response_type="JSON"):
        self.calls.append(dict(params))
        size = int(params.get("numOfRows") or params.get("display") or 20)
        if response_type == "JSON":
            size = int(params.get("display") or 20)
        page = int(params.get("page") or 1)
        lo = (page - 1) * size
        ids = list(range(1, self.total + 1))[lo:lo + size]
        if response_type == "JSON":
            rows = [{"id": str(i), "법령명한글": _name(i), "법령일련번호": str(1000 + i)} for i in ids]
            raw = json.dumps({"LawSearch": {"totalCnt": str(self.total), "page": str(page), "law": rows}},
                             ensure_ascii=False)
        else:
            rows = "".join(
                f'<law id="{i}"><법령명한글>{_name(i)}</법령명한글><법령일련번호>{1000 + i}</법령일련번호></law>'
                for i in ids)
            raw = f"<LawSearch><totalCnt>{self.total}</totalCnt><page>{page}</page>{rows}</LawSearch>"
        return {"status": "ok", "request_id": "r", "raw_content": raw}


def _search(client, rtype, display, page, total=None):
    if total is not None:
        client.total = total
    params = {"oc": FAKE_OC, "target": "eflaw", "type": rtype, "query": "민법",
              "display": display, "page": page}
    return run_search(
        get_client=lambda: client, target="eflaw", query="민법", snake_params=params,
        response_type=rtype, display=display, ranking_field="법령명한글", list_type="law",
        over_fetch_key="numOfRows",
    )


def _seqs(resp):
    rows = resp["ranked_data"].get("law", [])
    return [r["법령일련번호"] for r in rows]


@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
@pytest.mark.parametrize("page, expected_len", [(1, 20), (2, 20), (3, 5)])
def test_ranked_paging_slices_one_window(rtype, page, expected_len):
    client = PagedClient()
    resp = _search(client, rtype, display=20, page=page)
    assert len(_seqs(resp)) == expected_len
    sent = client.calls[0]
    assert sent["page"] == "1" and (sent.get("display") == "100" or sent.get("numOfRows") == "100")
    assert "ranking_applied" not in resp and "warning" not in resp


@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
def test_ranked_pages_are_disjoint_and_complete(rtype):
    seen = []
    for page in (1, 2, 3):
        seen += _seqs(_search(PagedClient(), rtype, display=20, page=page))
    assert len(seen) == len(set(seen)) == TOTAL


@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
def test_ranked_page_beyond_results_is_empty_not_no_results(rtype):
    resp = _search(PagedClient(), rtype, display=50, page=2)  # 100 <= 100, rows 51..100 of 45
    assert resp["status"] == "ok"
    assert _seqs(resp) == []
    assert resp.get("warning") != "no_results"


@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
def test_ranked_beyond_window_fetches_size_100_upstream_page(rtype):
    client = PagedClient(total=250)
    resp = _search(client, rtype, display=30, page=5)  # offset 120 >= 100
    assert len(client.calls) == 1
    sent = client.calls[0]
    assert sent["page"] == "2" and (sent.get("display") == "100" or sent.get("numOfRows") == "100")
    assert resp["ranking_applied"] is False
    assert _seqs(resp) == [str(1000 + i) for i in range(121, 151)]


@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
def test_display_100_forwards_page_unchanged(rtype):
    client = PagedClient(total=250)
    _search(client, rtype, display=100, page=2)
    assert client.calls[0]["page"] == 2


# ------------------------------------------------------------ zero results

@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
def test_zero_results_warning(rtype):
    resp = _search(PagedClient(), rtype, display=20, page=1, total=0)
    assert resp["status"] == "ok"
    assert resp["warning"] == "no_results"
    assert resp["message"] and any("정식 명칭" in h for h in resp["hints"])
    assert not any("search=2" in h for h in resp["hints"])  # no search option here


@pytest.mark.unit
def test_zero_results_body_search_hint_only_with_search_option():
    client = PagedClient(total=0)
    params = {"oc": FAKE_OC, "target": "prec", "type": "JSON", "query": "민법",
              "display": 20, "page": 1, "search": 1}
    resp = run_search(get_client=lambda: client, target="prec", query="민법",
                      snake_params=params, response_type="JSON", display=20,
                      ranking_field="판례명", list_type="items", item_category="prec",
                      over_fetch_key="display")
    assert resp["warning"] == "no_results"
    assert any("search=2" in h for h in resp["hints"])


@pytest.mark.unit
def test_elaw_search_pages_and_zero_results(monkeypatch):
    client = PagedClient()
    monkeypatch.setattr(server_mod, "LawAPIClient", lambda *a, **k: client)
    monkeypatch.setenv("OC", FAKE_OC)
    fn = server_mod.create_server()._tool_manager.get_tool("elaw_search").fn
    p2 = fn(query="민법", display=20, page=2, type="JSON")
    assert len(_seqs(p2)) == 20 and client.calls[0]["page"] == "1"
    client.total = 0
    zero = fn(query="민법", display=20, page=1, type="JSON")
    assert zero["warning"] == "no_results"
    client.total = 250
    beyond = fn(query="민법", display=30, page=6, type="JSON")
    assert beyond["ranking_applied"] is False
    assert len(_seqs(beyond)) == 30 and "ranked_data" in beyond


@pytest.mark.unit
def test_composites_report_no_results(monkeypatch):
    class Empty:
        def __init__(self, *a, **k):
            pass

        def get(self, endpoint, params, response_type="JSON"):
            return {"status": "ok", "request_id": "r",
                    "raw_content": json.dumps({"X": {"totalCnt": "0"}})}

    monkeypatch.setattr(server_mod, "LawAPIClient", Empty)
    monkeypatch.setenv("OC", FAKE_OC)
    tm = server_mod.create_server()._tool_manager
    for name, kw in [("legal_resolver", {"situation": "없는상황"}),
                     ("check_precedent_odds", {"query": "없는질의"}),
                     ("chain_dispute_prep", {"query": "없는질의"})]:
        out = tm.get_tool(name).fn(**kw)
        assert out["status"] == "ok" and out["warning"] == "no_results", name
    assert "outcome_note" in tm.get_tool("check_precedent_odds").fn(query="없는질의")


# ============================================================ round 3 regressions

def _tool(monkeypatch, client, name):
    monkeypatch.setattr(server_mod, "LawAPIClient", lambda *a, **k: client)
    monkeypatch.setenv("OC", FAKE_OC)
    return server_mod.create_server()._tool_manager.get_tool(name).fn


# ---- 1. cache aliasing

@pytest.mark.unit
def test_response_cache_returns_and_stores_copies():
    cache = ResponseCache()
    original = {"status": "ok", "raw_content": "A"}
    params = {"query": "q"}
    cache.put("law", params, original)
    original["raw_content"] = "mutated-after-put"
    first = cache.get("law", params)
    assert first["raw_content"] == "A"
    first["raw_content"] = "mutated-after-get"
    first["ranked_data"] = {"x": 1}
    second = cache.get("law", params)
    assert second["raw_content"] == "A" and "ranked_data" not in second
    assert second is not first


class RowsClient:
    """Serves ROWS pages honouring display/page (JSON), recording calls."""

    def __init__(self, root, list_key, rows, name_field):
        self.root, self.list_key, self.rows, self.name_field = root, list_key, rows, name_field
        self.calls = []

    def get(self, endpoint, params, response_type="JSON"):
        self.calls.append(dict(params))
        n = min(int(params.get("display", 20)), 100)
        pg = int(params.get("page", 1))
        body = {self.root: {"totalCnt": str(len(self.rows)), "page": str(pg),
                            self.list_key: self.rows[(pg - 1) * n:pg * n]}}
        return {"status": "ok", "request_id": "r", "raw_content": json.dumps(body, ensure_ascii=False)}


@pytest.mark.unit
def test_cgm_expc_pages_2_plus_not_empty_after_cache_hit(monkeypatch):
    rows = [{"id": str(i + 1), "안건명": f"퇴직금 해석 {i:02d}", "법령해석례일련번호": str(5000 + i)}
            for i in range(60)]
    client = RowsClient("CgmExpc", "cgmExpc", rows, "안건명")
    fn = _tool(monkeypatch, client, "cgm_expc_search")
    seen = []
    for pg in (1, 2, 3):
        out = fn(ministry="고용노동부", query="퇴직금", display=5, page=pg)
        ids = [r["법령해석례일련번호"] for r in out["ranked_data"]["cgmExpc"]]
        assert len(ids) == 5, (pg, ids)
        seen += ids
    assert len(set(seen)) == 15
    assert len(client.calls) == 1  # one cached 100-row window


@pytest.mark.unit
def test_special_decc_pages_and_display_change_after_cache_hit(monkeypatch):
    rows = [{"id": str(i + 1), "사건명": f"부가가치세 {i:02d}", "특별행정심판재결례일련번호": str(5000 + i)}
            for i in range(60)]
    client = RowsClient("Decc", "decc", rows, "사건명")
    fn = _tool(monkeypatch, client, "special_decc_search")
    kw = dict(tribunal="조세심판원", query="부가가치세")
    assert len(fn(display=5, page=1, **kw)["ranked_data"]["decc"]) == 5
    assert len(fn(display=5, page=2, **kw)["ranked_data"]["decc"]) == 5
    assert len(fn(display=10, page=1, **kw)["ranked_data"]["decc"]) == 10


# ---- 2. paging across the 100-row window

def _prec_name(i):
    # varied lengths so relevance ranking really reorders the window
    return f"민법 {i:03d}" if i % 3 == 0 else f"{'가' * (i % 7)} 민법 판례 사건 {i:03d}"


class PrecPagedClient:
    def __init__(self, total):
        self.total, self.calls = total, []

    def get(self, endpoint, params, response_type="JSON"):
        self.calls.append(dict(params))
        n = int(params.get("display") or 20)
        pg = int(params.get("page") or 1)
        ids = list(range(1, self.total + 1))[(pg - 1) * n:pg * n]
        if response_type == "JSON":
            rows = [{"id": str(i), "사건명": _prec_name(i), "판례일련번호": str(2000 + i)} for i in ids]
            raw = json.dumps({"PrecSearch": {"totalCnt": str(self.total), "page": str(pg), "prec": rows}},
                             ensure_ascii=False)
        else:
            rows = "".join(f'<prec id="{i}"><사건명>{_prec_name(i)}</사건명><판례일련번호>{2000 + i}</판례일련번호></prec>'
                           for i in ids)
            raw = f"<PrecSearch><totalCnt>{self.total}</totalCnt><page>{pg}</page>{rows}</PrecSearch>"
        return {"status": "ok", "request_id": "r", "raw_content": raw}


DISPLAYS = [1, 3, 7, 20, 30, 33, 50, 99, 100]


def _traverse(search_page, total, display):
    seen, applied = [], []
    for pg in range(1, total // display + 3):
        resp = search_page(pg)
        assert "ranked_data" in resp, f"page {pg} lacks ranked_data"
        rows = _seqs(resp)
        applied.append(resp.get("ranking_applied"))
        if not rows:
            break
        seen += rows
    return seen, applied


@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
@pytest.mark.parametrize("display", DISPLAYS)
def test_paging_traversal_has_no_dups_or_gaps_run_search(rtype, display):
    client = PagedClient(total=250)
    seen, applied = _traverse(lambda pg: _search(client, rtype, display, pg), 250, display)
    assert len(seen) == len(set(seen)) == 250
    assert set(seen) == {str(1000 + i) for i in range(1, 251)}
    if display < 100 and 100 % display:
        assert "partial" in applied
    assert max(len(client.calls) for _ in [0]) >= 1


@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
@pytest.mark.parametrize("display", DISPLAYS)
def test_paging_traversal_has_no_dups_or_gaps_elaw(monkeypatch, rtype, display):
    client = PagedClient(total=250)
    fn = _tool(monkeypatch, client, "elaw_search")
    seen, _ = _traverse(lambda pg: fn(query="민법", display=display, page=pg, type=rtype), 250, display)
    assert len(seen) == len(set(seen)) == 250


@pytest.mark.unit
@pytest.mark.parametrize("rtype", ["JSON", "XML"])
@pytest.mark.parametrize("display", [7, 30, 33, 100])
def test_paging_traversal_with_display_over_fetch_key(rtype, display):
    client = PrecPagedClient(250)

    def page(pg):
        params = {"oc": FAKE_OC, "target": "prec", "type": rtype, "query": "민법",
                  "display": display, "page": pg}
        resp = run_search(get_client=lambda: client, target="prec", query="민법",
                          snake_params=params, response_type=rtype, display=display,
                          ranking_field="사건명", list_type="items", item_category="prec",
                          over_fetch_key="display")
        rows = resp["ranked_data"]["prec"] if "prec" in resp.get("ranked_data", {}) else []
        return {"ranked_data": {"law": [{"법령일련번호": r["판례일련번호"]} for r in rows]},
                "ranking_applied": resp.get("ranking_applied")}

    seen, _ = _traverse(page, 250, display)
    assert len(seen) == len(set(seen)) == 250


@pytest.mark.unit
def test_straddling_page_uses_at_most_two_upstream_calls_and_is_partial():
    client = PagedClient(total=250)
    resp = _search(client, "JSON", display=30, page=4)  # rows 90..119
    assert resp["ranking_applied"] == "partial"
    assert len(client.calls) == 2
    assert [c["page"] for c in client.calls] == ["1", "2"]
    assert len(_seqs(resp)) == 30


@pytest.mark.unit
def test_ranked_data_page_field_reflects_requested_page():
    client = PagedClient(total=250)
    for pg in (1, 2, 3, 4, 9):
        assert _search(client, "JSON", display=30, page=pg)["ranked_data"]["page"] == str(pg)


# ---- 7. paging inputs and hints

@pytest.mark.unit
@pytest.mark.parametrize("page, display", [(0, 20), (-1, 20), (1, 0), (1, -5)])
def test_run_search_rejects_bad_paging(page, display):
    with pytest.raises(ToolValidationError):
        _search(PagedClient(), "JSON", display=display, page=page)


@pytest.mark.unit
def test_elaw_search_rejects_bad_paging(monkeypatch):
    fn = _tool(monkeypatch, PagedClient(), "elaw_search")
    for kw in ({"page": 0}, {"page": -1}, {"display": 0}):
        out = fn(query="민법", type="JSON", **kw)
        assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR", kw


@pytest.mark.unit
def test_display_over_100_still_clamps_not_errors():
    resp = _search(PagedClient(total=250), "JSON", display=150, page=1)
    assert resp["status"] == "ok"


@pytest.mark.unit
@pytest.mark.parametrize("display, page", [(20, 20), (100, 5)])
def test_page_beyond_results_hints_no_more_results(display, page):
    resp = _search(PagedClient(total=45), "JSON", display=display, page=page)
    assert resp["status"] == "ok"
    assert any("no_more_results" in h for h in resp.get("hints", []))
    ok = _search(PagedClient(total=45), "JSON", display=20, page=1)
    assert not any("no_more_results" in h for h in ok.get("hints", []))


# ---- 3. composite failures are not "no results"

class TargetClient:
    """Per-target responder; ``fail`` maps target(+search) -> error code."""

    def __init__(self, fail=None, ok_rows=False):
        self.fail, self.ok_rows, self.calls = fail or {}, ok_rows, []

    def get(self, endpoint, params, response_type="JSON"):
        self.calls.append(dict(params))
        target = params.get("target")
        for key, code in self.fail.items():
            tgt, _, search = key.partition(":")
            if tgt == target and (not search or str(params.get("search")) == search):
                return create_error_response(error_code=code, message="boom", hints=[], request_id="r")
        return {"status": "ok", "request_id": "r",
                "raw_content": json.dumps({"X": {"totalCnt": "0"}})}


ALL_TARGETS = ["aiSearch", "prec", "expc", "eflaw", "decc", "detc", "ttSpecialDecc"]


@pytest.mark.unit
@pytest.mark.parametrize("name, kw", [
    ("legal_resolver", {"situation": "보증금 문제"}),
    ("check_precedent_odds", {"query": "보증금"}),
    ("chain_dispute_prep", {"query": "보증금"}),
    ("chain_full_research", {"query": "보증금"}),
])
def test_composites_return_error_when_every_search_failed(monkeypatch, name, kw):
    client = TargetClient({t: ErrorCode.TIMEOUT for t in ALL_TARGETS})
    out = _tool(monkeypatch, client, name)(**kw)
    assert out["status"] == "error" and out["error_code"] == "TIMEOUT", out
    assert out["hints"] and out.get("warning") != "no_results"
    assert out["success"] is False


@pytest.mark.unit
def test_composite_mixed_failure_codes_become_upstream_error(monkeypatch):
    client = TargetClient({"aiSearch": ErrorCode.TIMEOUT, "expc": ErrorCode.API_NOT_SUBSCRIBED})
    out = _tool(monkeypatch, client, "legal_resolver")(situation="보증금")
    assert out["status"] == "error" and out["error_code"] == "UPSTREAM_ERROR"


@pytest.mark.unit
def test_legal_resolver_partial_failure_warns_and_never_no_results(monkeypatch):
    client = TargetClient({"expc": ErrorCode.TIMEOUT})
    out = _tool(monkeypatch, client, "legal_resolver")(situation="보증금")
    assert out["status"] == "ok" and "warning" not in out
    assert any("expc" in w and "TIMEOUT" in w for w in out["warnings"])


@pytest.mark.unit
def test_check_precedent_odds_partial_failure_warns(monkeypatch):
    client = TargetClient({"prec:1": ErrorCode.TIMEOUT})
    out = _tool(monkeypatch, client, "check_precedent_odds")(query="보증금")
    assert out["status"] == "ok" and "warning" not in out
    assert any("TIMEOUT" in w and "prec" in w for w in out["warnings"])


@pytest.mark.unit
def test_chain_dispute_prep_partial_failure_warns_and_full_success_keeps_no_results(monkeypatch):
    out = _tool(monkeypatch, TargetClient({"detc": ErrorCode.UPSTREAM_ERROR}), "chain_dispute_prep")(query="보증금")
    assert out["status"] == "ok" and "warning" not in out
    assert any("detc" in w and "UPSTREAM_ERROR" in w for w in out["warnings"])
    clean = _tool(monkeypatch, TargetClient(), "chain_dispute_prep")(query="보증금")
    assert clean["warning"] == "no_results" and "warnings" not in clean


@pytest.mark.unit
def test_chain_full_research_one_branch_failed_warns(monkeypatch):
    client = TargetClient({"prec": ErrorCode.TIMEOUT})
    out = _tool(monkeypatch, client, "chain_full_research")(query="보증금")
    assert out["status"] == "ok"
    assert any("check_precedent_odds" in w and "TIMEOUT" in w for w in out["warnings"])


# ---- 4. article_citation name check

def _named_body(name, abbrev=None):
    info = {"법령명_한글": name}
    if abbrev is not None:
        info["법령명약칭"] = abbrev
    return json.dumps({"법령": {"기본정보": info,
                              "조문": {"조문단위": [{"조문번호": "3", "조문내용": "제3조"}]}}},
                      ensure_ascii=False)


@pytest.mark.unit
@pytest.mark.parametrize("given, official, abbrev", [
    ("정보통신망법", "정보통신망 이용촉진 및 정보보호 등에 관한 법률", "정보통신망법"),
    ("중대재해처벌법", "중대재해 처벌 등에 관한 법률", "중대재해처벌법"),
    ("남녀고용평등법", "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률", "남녀고용평등법"),
    ("상가임대차보호법", "상가건물 임대차보호법", "상가임대차보호법"),
    ("「민법」", "민법", ""),
    ("민법(법률)", "민법", ""),
    ("민 법", "민법", None),
])
def test_citation_accepts_abbreviation_and_decorated_names(cite, given, official, abbrev):
    CitationClient.body = _named_body(official, abbrev)
    out = cite(mst="1", law_name=given, article=3)
    assert out.get("error_code") is None and out["success"] is True, out


@pytest.mark.unit
def test_citation_abbreviation_found_via_law_search_when_body_lacks_it(cite):
    official = "중대재해 처벌 등에 관한 법률"
    CitationClient.body = _named_body(official)  # no 법령명약칭 field at all
    searches = []
    original_get = CitationClient.get

    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == "/DRF/lawSearch.do":
            searches.append(dict(params))
            body = {"LawSearch": {"totalCnt": "1", "law": [
                {"법령명한글": official, "법령약칭명": "중대재해처벌법", "법령일련번호": "1"}]}}
            return {"status": "ok", "request_id": "r", "raw_content": json.dumps(body, ensure_ascii=False)}
        return original_get(self, endpoint, params, response_type)

    CitationClient.get = get
    try:
        out = cite(mst="1", law_name="중대재해처벌법", article=3)
        matched = cite(mst="1", law_name=official, article=3)
    finally:
        CitationClient.get = original_get
    assert out["success"] is True
    assert len(searches) == 1  # only the mismatching call searched
    assert matched["success"] is True


@pytest.mark.unit
@pytest.mark.parametrize("upstream, given", [
    ("개인정보 보호법 시행령", "개인정보보호법"),
    ("개인정보 보호법", "개인정보보호법 시행령"),
    ("개인정보 보호법 시행규칙", "개인정보보호법 시행령"),
    ("정보통신망 이용촉진 및 정보보호 등에 관한 법률 시행령", "정보통신망법"),
])
def test_citation_still_rejects_law_vs_decree_mismatch(cite, upstream, given):
    CitationClient.body = _named_body(upstream, "")
    out = cite(mst="1", law_name=given, article=3)
    assert out["error_code"] == "VALIDATION_ERROR" and out["success"] is False
    assert cite.extracted == []


# ---- 5. verification outage

@pytest.mark.unit
@pytest.mark.parametrize("code", ["TIMEOUT", "API_NOT_SUBSCRIBED", "UPSTREAM_ERROR", "EMPTY_RESPONSE"])
def test_citation_verification_outage_continues_with_warning(cite, code):
    CitationClient.error = create_error_response(error_code=code, message="x", hints=[], request_id="r")
    out = cite(mst="1", law_name="민법", article=3)
    assert out["success"] is True and cite.extracted
    assert any(code in w for w in out["warnings"])


@pytest.mark.unit
def test_citation_not_found_is_hard_error_with_success_false(cite):
    CitationClient.error = create_error_response(error_code="NOT_FOUND", message="x", hints=[], request_id="r")
    out = cite(mst="9", law_name="민법", article=3)
    assert out["error_code"] == "NOT_FOUND" and out["success"] is False
    assert cite.extracted == []


@pytest.mark.unit
def test_outcome_keywords_dict_removed():
    import lexlink._helpers as helpers
    assert not hasattr(helpers, "OUTCOME_KEYWORDS")


# ---- 8. docs

@pytest.mark.unit
def test_ordin_search_rr_cls_cd_doc_uses_revision_type_meaning():
    fn = server_mod.create_server()._tool_manager.get_tool("ordin_search").fn
    assert "제개정" in fn.__doc__ and "Administrative district" not in fn.__doc__
