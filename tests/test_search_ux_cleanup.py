"""Offline tests: no-result guidance, raw_content trimming, and misc UX fixes (issues #18, #19)."""

import json
import logging

import httpx
import pytest

import lexlink.server as server_mod
from lexlink._helpers import body_is_all_null, rename_row_ids_to_rank
from lexlink.cache import get_cache
from lexlink.client import LawAPIClient
from lexlink.linkage import parse_drlaw_html, pick_linked_term

FAKE_OC = "unit-test-oc"


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setenv("OC", FAKE_OC)
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    get_cache().invalidate()
    yield
    get_cache().invalidate()


def _tool(monkeypatch, name, body, seen=None):
    """Create the server with a mocked upstream that always answers ``body`` (str)."""
    def handler(request):
        if seen is not None:
            seen.append(request)
        text = body(request) if callable(body) else body
        return httpx.Response(200, text=text, request=request)

    def make_client(*a, **k):
        c = LawAPIClient(base_url="http://law.test")
        c.client = httpx.Client(transport=httpx.MockTransport(handler))
        return c

    monkeypatch.setattr(server_mod, "LawAPIClient", make_client)
    return server_mod.create_server()._tool_manager.get_tool(name).fn


# --- #18: no-result guidance on tools that ignored it -------------------------

@pytest.mark.unit
@pytest.mark.parametrize("tool,body", [
    ("lstrm_ai_search", {"lstrmAISearch": {"검색결과개수": "0", "키워드": "x", "page": "1", "target": "lstrmAI"}}),
    ("dlytrm_search", {"dlytrmSearch": {"검색결과개수": "0", "키워드": "x", "page": "1", "target": "dlytrm"}}),
    ("ls_rlt_search", {"Law": "일치하는 관련법령 정보가 없습니다. 검색조건을 확인하여 주십시오."}),
    ("ordinLsCon_search", {"OrdinSearch": {"키워드": "건축법", "page": "1", "target": "lnkOrd", "totalCnt": "0"}}),
])
def test_empty_search_gets_no_results_guidance(monkeypatch, tool, body):
    fn = _tool(monkeypatch, tool, json.dumps(body, ensure_ascii=False))
    out = fn(query="건축법")
    assert out["status"] == "ok"
    assert out["warning"] == "no_results"
    assert out["message"] and out["hints"]


@pytest.mark.unit
def test_lstrm_rlt_jo_search_empty_gets_guidance(monkeypatch):
    body = json.dumps({"Law": "일치하는 법령용어-조문 연계 정보가 없습니다. 검색조건을 확인하여 주십시오."}, ensure_ascii=False)
    out = _tool(monkeypatch, "lstrm_rlt_jo_search", body)(query="없는용어")
    assert out["warning"] == "no_results" and out["hints"]


@pytest.mark.unit
def test_nonempty_knowledge_base_search_has_no_warning(monkeypatch):
    body = json.dumps({"lstrmAISearch": {"검색결과개수": "1", "법령용어": [{"법령용어명": "불법행위"}]}}, ensure_ascii=False)
    out = _tool(monkeypatch, "lstrm_ai_search", body)(query="불법행위")
    assert "warning" not in out


# --- #18: raw_content only carries the requested page -------------------------

def _prec_rows(n):
    return [
        {"id": str(i + 1), "사건명": f"손해배상 {i}", "사건번호": f"2026다{i}", "판례일련번호": str(1000 + i)}
        for i in range(n)
    ]


@pytest.mark.unit
def test_prec_search_raw_content_is_only_requested_rows(monkeypatch):
    body = json.dumps({"PrecSearch": {"totalCnt": "100", "page": "1", "prec": _prec_rows(100)}}, ensure_ascii=False)
    out = _tool(monkeypatch, "prec_search", body)(query="손해배상", display=5)
    raw_rows = json.loads(out["raw_content"])["PrecSearch"]["prec"]
    assert len(raw_rows) == 5 == len(out["ranked_data"]["prec"])
    # no fields lost: raw rows are the upstream rows (still carrying id)
    assert all({"id", "사건명", "사건번호", "판례일련번호"} <= set(r) for r in raw_rows)
    assert {r["판례일련번호"] for r in raw_rows} == {r["판례일련번호"] for r in out["ranked_data"]["prec"]}


@pytest.mark.unit
def test_detc_search_past_end_raw_content_matches_empty_ranked_data(monkeypatch):
    rows = [{"id": str(i + 1), "사건명": f"재산권 {i}", "헌재결정례일련번호": str(i)} for i in range(29)]
    def body(request):  # like upstream: rows on page 1, an empty page beyond it
        page = request.url.params.get("page")
        root = {"totalCnt": "29", "page": page}
        if page == "1":
            root["detc"] = rows
        return json.dumps({"DetcSearch": root}, ensure_ascii=False)

    out = _tool(monkeypatch, "detc_search", body)(query="재산권", page=11, display=10)
    assert out["ranked_data"]["detc"] == []
    assert json.loads(out["raw_content"])["DetcSearch"]["page"] == "11"
    assert json.loads(out["raw_content"])["DetcSearch"]["detc"] == []


# --- #19 ---------------------------------------------------------------------

@pytest.mark.unit
def test_ordin_id_note_distinguishes_id_from_serial():
    resp = rename_row_ids_to_rank({
        "raw_content": "{}",
        "ranked_data": {"law": [{"id": "1", "자치법규ID": "2021769", "자치법규일련번호": "2169057"}]},
    })
    assert "자치법규ID" in resp["id_note"] and "자치법규일련번호" in resp["id_note"]
    other = rename_row_ids_to_rank({"raw_content": "{}", "ranked_data": {"prec": [{"id": "1"}]}})
    assert "자치법규" not in other["id_note"]


ALL_NULL = json.dumps({"FtcService": {
    "사건번호": "null", "결정문일련번호": "18701", "문서유형": "null",
    "피심정보": {"피심정보명": "", "피심정보내용": ""}, "사건명": "null",
}}, ensure_ascii=False)


@pytest.mark.unit
def test_committee_service_all_null_body_is_not_found(monkeypatch):
    out = _tool(monkeypatch, "committee_service", ALL_NULL)(committee="공정거래위원회", id=18701)
    assert out["status"] == "error"
    assert out["error_code"] == "NOT_FOUND"


@pytest.mark.unit
def test_committee_service_real_body_is_ok(monkeypatch):
    body = json.dumps({"FtcService": {"사건번호": "2020서1234", "결정문일련번호": "5", "사건명": "담합"}}, ensure_ascii=False)
    out = _tool(monkeypatch, "committee_service", body)(committee="공정거래위원회", id=5)
    assert out["status"] == "ok"
    assert not body_is_all_null("{}", "JSON")


LSTRM_ROOT = {
    "검색결과개수": "1", "target": "lstrmRlt",
    "법령용어": {"id": "1", "연계용어": [
        {"일상용어명": "범죄", "용어관계": "연관어"},
        {"일상용어명": "노동자", "용어관계": "하위어"},
        {"일상용어명": "세입자", "용어관계": "상위어"},
        {"일상용어명": "임차인", "용어관계": "동의어"},
    ]},
}


@pytest.mark.unit
def test_pick_linked_term_reads_nested_links_and_prefers_synonyms():
    assert pick_linked_term(LSTRM_ROOT, "일상용어명") == ("임차인", "동의어")
    only_loose = {"법령용어": {"연계용어": [{"일상용어명": "범죄", "용어관계": "연관어"}]}}
    assert pick_linked_term(only_loose, "일상용어명") == ("", "")
    single = {"법령용어": {"연계용어": {"일상용어명": "정당이용", "용어관계": "동의어"}}}
    assert pick_linked_term(single, "일상용어명") == ("정당이용", "동의어")
    assert pick_linked_term(single, "일상용어명", exclude="정당이용") == ("", "")


DRLAW_HTML = """<html><body><div class="lelitop"><div class="num">총<strong>981</strong>건</div></div>
<table id="unOrdinStatsTb"><thead>
<tr><th rowspan="2">소관부처</th><th rowspan="2">법령명</th><th rowspan="2">조문</th><th colspan="2">현황</th></tr>
<tr><th>전체</th><th>서울</th></tr></thead><tbody>
<tr><td>소방청</td><td>119구조법</td><td id="unOrdinStatsTd" align="left">제13조(센터)&lt;2021.1.21&gt;
<td class="unordTd">16</td><td class="unordTd">1</td></tr>
</tbody></table></body></html>"""


@pytest.mark.unit
def test_parse_drlaw_html_handles_unclosed_article_cell():
    parsed = parse_drlaw_html(DRLAW_HTML)
    assert parsed["total"] == 981
    assert parsed["columns"] == ["전체", "서울"]
    assert parsed["rows"] == [{
        "소관부처": "소방청", "법령명": "119구조법", "조문": "제13조(센터)<2021.1.21>",
        "자치법규수": {"전체": "16", "서울": "1"},
    }]
    assert parse_drlaw_html("<html>nothing</html>") is None


@pytest.mark.unit
def test_drlaw_search_returns_structured_data_not_raw_html(monkeypatch):
    out = _tool(monkeypatch, "drlaw_search", DRLAW_HTML)()
    assert "raw_content" not in out
    assert out["parsed_data"]["rows"][0]["법령명"] == "119구조법"
    assert out["content_note"]


@pytest.mark.unit
def test_elaw_search_strips_keyword_markup(monkeypatch):
    rows = [{"id": "1", "법령일련번호": "11", "법령명한글": "간호법",
             "법령명영문": 'NURSING <strong class="tbl_tx_type">ACT</strong>'}]
    body = json.dumps({"LawSearch": {"totalCnt": "1", "law": rows}}, ensure_ascii=False)
    out = _tool(monkeypatch, "elaw_search", body)(query="Act")
    assert out["ranked_data"]["law"][0]["법령명영문"] == "NURSING ACT"
    assert "<strong" not in out["raw_content"]


@pytest.mark.unit
def test_httpx_debug_logging_never_shows_oc(caplog):
    httpx_logger = logging.getLogger("httpx")
    old_level = httpx_logger.level
    httpx_logger.setLevel(logging.DEBUG)
    try:
        client = LawAPIClient(base_url="http://law.test")
        client.client = httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text='{"LawSearch": {"totalCnt": "0"}}', request=request)))
        with caplog.at_level(logging.DEBUG):
            client.get("/DRF/lawSearch.do", {"OC": "secret-oc-value", "target": "law", "query": "민법"}, "JSON")
    finally:
        httpx_logger.setLevel(old_level)
    httpx_lines = [r.getMessage() for r in caplog.records if r.name.startswith("httpx")]
    assert httpx_lines, "expected httpx to log the request at DEBUG/INFO"
    assert all("secret-oc-value" not in line for line in httpx_lines)
