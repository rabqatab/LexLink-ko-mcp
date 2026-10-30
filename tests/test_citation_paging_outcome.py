"""article_citation verification, ranked paging, zero-result guidance, outcome heuristic."""

import asyncio
import json

import pytest

import lexlink.citation as citation_mod
import lexlink.server as server_mod
from lexlink._helpers import extract_outcome, run_search
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
    rows = resp["ranked_data"]["law"]
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
def test_ranked_over_window_skips_ranking_and_forwards_page(rtype):
    client = PagedClient(total=150)
    resp = _search(client, rtype, display=30, page=4)  # 120 > 100
    sent = client.calls[0]
    assert sent["page"] == 4 and sent["display"] == 30
    assert "numOfRows" not in sent
    assert resp["ranking_applied"] is False


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
    skipped = fn(query="민법", display=30, page=4, type="JSON")
    assert skipped["ranking_applied"] is False


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


# ------------------------------------------------------------------ outcome

@pytest.mark.unit
@pytest.mark.parametrize("text, expected", [
    ("", "불명"),
    ("원고의 청구를 일부인용한다", "일부인용"),
    ("청구를 일부 인용하고 나머지를 기각한다", "일부인용"),
    ("항소를 일부기각한다", "일부기각"),
    ("원심판결을 파기하고 사건을 환송한다. 파기환송", "파기환송"),
    ("원심판결을 파기자판한다", "파기자판"),
    ("원심판결을 파기한다", "파기"),
    ("상고를 기각한다", "기각"),
    ("피고의 항소를 기각하였다", "기각"),
    ("이 사건 심판청구를 각하한다", "각하"),
    ("청구를 인용한다", "인용"),
    ("신청을 인용하는 결정", "인용"),
    ("처분을 취소한다", "취소"),
    ("원심판결 인용", "불명"),
    ("원심판결을 인용하여 상고를 기각한다", "기각"),
    ("제1심 판결 이유를 인용하여 판단한다", "불명"),
    ("청구를 인용하지 아니한다", "불명"),
    ("인용된 판례에 비추어", "불명"),
    ("임대인은 보증금을 반환할 의무가 있다", "불명"),
])
def test_extract_outcome_table(text, expected):
    assert extract_outcome(text) == expected


@pytest.mark.unit
def test_extract_outcome_docstring_notes_heuristic():
    assert "Heuristic" in extract_outcome.__doc__
