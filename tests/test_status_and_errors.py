"""Status labels and error classification: nw text, unknown-MST diffs, empty bodies, 미신청 page,
blank queries, jo forms, citation ranges, non-numeric ids, OC advice (all offline)."""

import asyncio
import json

import httpx
import pytest

import lexlink.server as server_mod
from lexlink import params as params_mod
from lexlink.cache import get_cache
from lexlink.citation import CitationExtractor
from lexlink.client import LawAPIClient
from lexlink.errors import ErrorCode, create_error_response

from test_amendment import FakeClient
from test_client_errors import NOT_SUBSCRIBED_HTML

SERVICE = "/DRF/lawService.do"
SEARCH = "/DRF/lawSearch.do"


@pytest.fixture(autouse=True)
def _fresh_cache():
    get_cache().invalidate()
    yield
    get_cache().invalidate()


def _tools(monkeypatch, client_cls=FakeClient):
    monkeypatch.setattr(server_mod, "LawAPIClient", client_cls)
    monkeypatch.setenv("OC", "unit-test-oc")
    client_cls.calls = []
    server = server_mod.create_server()

    def call(name, **kwargs):
        out = server._tool_manager.get_tool(name).fn(**kwargs)
        return asyncio.run(out) if asyncio.iscoroutine(out) else out
    return server, call


# --- 1. eflaw_search nw ----------------------------------------------------------

@pytest.mark.unit
def test_eflaw_nw_text_matches_measured_codes(monkeypatch):
    """Measured live: nw=1 연혁, nw=2 시행예정, nw=3 현행."""
    server, call = _tools(monkeypatch)
    tool = server._tool_manager.get_tool("eflaw_search")
    desc = tool.parameters["properties"]["nw"]["description"]
    assert "2=시행예정" in desc and "3=현행" in desc and "2=현행" not in desc
    assert "2=시행예정, 3=현행" in tool.fn.__doc__ and "2=현행" not in tool.fn.__doc__
    out = call("eflaw_search", query="저작권법", nw="4")
    assert out["error_code"] == ErrorCode.VALIDATION_ERROR
    assert "2=시행예정, 3=현행" in out["message"]


# --- 2. article_amendment_diff / chain_amendment_track ----------------------------

@pytest.mark.unit
@pytest.mark.parametrize("old,new", [("150421", "999999999"), ("999999999", "150421")])
def test_diff_unknown_mst_returns_error_not_deleted(monkeypatch, old, new):
    class Fake(FakeClient):
        def _service(self, target, params, response_type):
            if target == "law" and params.get("MST") == "999999999":
                return create_error_response(error_code=ErrorCode.NOT_FOUND,
                                             message="일치하는 법령이 없습니다.", hints=[])
            return super()._service(target, params, response_type)
    _, call = _tools(monkeypatch, Fake)
    out = call("article_amendment_diff", mst_old=old, mst_new=new, article=35, article_branch=5)
    assert out["status"] == "error" and out["error_code"] == ErrorCode.NOT_FOUND
    assert "999999999" in out["message"]
    assert "has_changes" not in out and "summary" not in out


@pytest.mark.unit
def test_diff_deleted_only_when_both_versions_exist(monkeypatch):
    _, call = _tools(monkeypatch)
    # 283335 has the article, 29306 is a real version without it
    out = call("article_amendment_diff", mst_old="283335", mst_new="29306", article=35, article_branch=5)
    assert out["status"] == "ok" and out["has_changes"] is True
    assert "deleted" in out["summary"]
    assert out["new_version"]["note"] and out["old_version"]["text"]


@pytest.mark.unit
def test_chain_amendment_track_reports_failed_diff(monkeypatch):
    class Fake(FakeClient):
        def _service(self, target, params, response_type):
            if target == "law" and params.get("JO"):
                return create_error_response(error_code=ErrorCode.NOT_FOUND,
                                             message="일치하는 법령이 없습니다.", hints=[])
            return super()._service(target, params, response_type)
    _, call = _tools(monkeypatch, Fake)
    out = call("chain_amendment_track", law_name="저작권법", date_from="20240101",
               article=35, article_branch=5)
    diff = out["article_diff"]
    assert diff["error"]["error_code"] == ErrorCode.NOT_FOUND
    assert "has_changes" not in diff and "summary" not in diff
    assert any("조문 비교 실패" in w for w in out["warnings"])


# --- 3. empty bodies ---------------------------------------------------------------

EMPTY_DETC = json.dumps({"DetcService": {
    "사건번호": "2014헌바182", "판시사항": "", "결정요지": "", "전문": "", "사건명": "공직선거법 위헌소원",
    "헌재결정례일련번호": "150756"}}, ensure_ascii=False)
FULL_DETC = json.dumps({"DetcService": {
    "사건번호": "2017헌바127", "판시사항": "낙태", "결정요지": "", "전문": "본문", "사건명": "형법 위헌소원",
    "헌재결정례일련번호": "150780"}}, ensure_ascii=False)


def _service_fake(bodies):
    class Fake(FakeClient):
        def get(self, endpoint, params, response_type="JSON"):
            body = bodies[params["target"]]
            return {"status": "ok", "request_id": "fake", "upstream_type": response_type, "raw_content": body}
    return Fake


@pytest.mark.unit
@pytest.mark.parametrize("sections", [None, "summary"])
def test_empty_body_gets_machine_readable_warning(monkeypatch, sections):
    _, call = _tools(monkeypatch, _service_fake({"detc": EMPTY_DETC}))
    out = call("detc_service", id="150756", sections=sections)
    assert out["status"] == "ok"
    assert out["warning"] == "empty_body"
    assert out["empty_fields"] == ["판시사항", "결정요지", "전문"]
    assert "단정하지" in out["message"]


@pytest.mark.unit
def test_non_empty_body_has_no_warning(monkeypatch):
    _, call = _tools(monkeypatch, _service_fake({"detc": FULL_DETC}))
    out = call("detc_service", id="150780")
    assert "warning" not in out and "empty_fields" not in out


@pytest.mark.unit
def test_empty_body_other_service_tools(monkeypatch):
    empty = {
        "expc": json.dumps({"ExpcService": {"안건명": "x", "질의요지": "", "회답": "", "이유": ""}}),
        "decc": json.dumps({"DeccService": {"사건명": "x", "주문": "", "청구취지": "", "재결요지": "", "이유": ""}}),
        "prec": json.dumps({"PrecService": {"사건명": "x", "판시사항": "", "판결요지": "", "판례내용": ""}}),
        "trty": json.dumps({"BothTrtyService": {"조약기본정보": {"a": "b"}, "조약내용": ""}}),
    }
    _, call = _tools(monkeypatch, _service_fake(empty))
    for tool in ("expc_service", "decc_service", "prec_service", "trty_service"):
        out = call(tool, id="1")
        assert out["warning"] == "empty_body", tool
    # prec with sections=summary keeps the empty-body warning instead of the fallback text
    assert call("prec_service", id="1", sections="summary")["warning"] == "empty_body"


# --- 4. 미신청 page vs request errors -----------------------------------------------

def _routing_client(service_body, search_body, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        body = service_body if request.url.path.endswith("lawService.do") else search_body
        return httpx.Response(200, text=body, request=request)
    client = LawAPIClient(base_url="http://law.test")
    client.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return client


OK_LIST = '{"LawSearch": {"totalCnt": "3", "law": [{"법령명한글": "x"}]}}'


@pytest.mark.integration
def test_not_subscribed_page_with_working_list_is_not_reported_as_unsubscribed():
    client = _routing_client(NOT_SUBSCRIBED_HTML, OK_LIST)
    out = client.get(SERVICE, {"OC": "x", "target": "eflaw", "MST": "283335", "efYd": "19000101"}, "JSON")
    assert out["status"] == "error"
    assert out["error_code"] == ErrorCode.UPSTREAM_HTML_ERROR
    assert out["error_code"] != ErrorCode.API_NOT_SUBSCRIBED
    assert out["may_be_not_subscribed"] is True
    # both causes are named, and the law_service / eflaw_josub alternatives stay
    assert "인자" in out["message"] and "미신청" in out["message"] and "구분하지 않아" in out["message"]
    assert "law_service" in " ".join(out["hints"]) and "eflaw_josub" in " ".join(out["hints"])


@pytest.mark.integration
def test_not_subscribed_confirmed_when_list_is_unsubscribed_too():
    client = _routing_client(NOT_SUBSCRIBED_HTML, NOT_SUBSCRIBED_HTML)
    out = client.get(SERVICE, {"OC": "x", "target": "eflaw", "ID": "0000"}, "JSON")
    assert out["error_code"] == ErrorCode.API_NOT_SUBSCRIBED


@pytest.mark.integration
def test_not_subscribed_kept_when_probe_is_inconclusive():
    client = _routing_client(NOT_SUBSCRIBED_HTML, "")
    out = client.get(SERVICE, {"OC": "x", "target": "eflawjosub", "ID": "1"}, "JSON")
    assert out["error_code"] == ErrorCode.API_NOT_SUBSCRIBED
    assert any("확인하지 못함" in h for h in out["hints"])


@pytest.mark.integration
@pytest.mark.parametrize("endpoint", [SERVICE, SEARCH])
def test_invalid_type_is_validation_error_without_a_request(endpoint):
    seen = []
    client = _routing_client(NOT_SUBSCRIBED_HTML, NOT_SUBSCRIBED_HTML, seen)
    out = client.get(endpoint, {"OC": "x", "target": "eflaw", "ID": "1"}, "BOGUS")
    assert out["error_code"] == ErrorCode.VALIDATION_ERROR
    assert "JSON, XML, HTML" in out["message"]
    assert seen == []


@pytest.mark.integration
def test_lowercase_type_is_accepted():
    client = _routing_client(OK_LIST, OK_LIST)
    out = client.get(SEARCH, {"OC": "x", "target": "law"}, "json")
    assert out["status"] == "ok" and out["upstream_type"] == "JSON"


# --- 5. blank queries ------------------------------------------------------------------

BLANK_CASES = [
    ("chain_law_system", "law_name"), ("legal_resolver", "situation"),
    ("check_precedent_odds", "query"), ("chain_full_research", "query"),
    ("chain_dispute_prep", "query"), ("eflaw_search", "query"), ("law_search", "query"),
    ("aiSearch", "query"), ("aiRltLs_search", "query"), ("article_citation", "law_name"),
    ("law_amendment_summary", "law_name"), ("chain_amendment_track", "law_name"),
    ("law_as_of", "law_name"), ("simplify_article", "law_name"),
]


@pytest.mark.unit
@pytest.mark.parametrize("tool,arg", BLANK_CASES)
@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_required_text_is_validation_error_before_upstream(monkeypatch, tool, arg, blank):
    _, call = _tools(monkeypatch)
    kwargs = {arg: blank}
    if tool == "article_citation":
        kwargs.update(mst="283335", article=35)
    if tool == "law_as_of":
        kwargs.update(as_of="20250101")
    if tool == "simplify_article":
        kwargs.update(article=35)
    out = call(tool, **kwargs)
    assert out["status"] == "error" and out["error_code"] == ErrorCode.VALIDATION_ERROR, out
    assert arg in out["message"]
    assert FakeClient.calls == []


@pytest.mark.unit
def test_non_blank_query_still_passes(monkeypatch):
    _, call = _tools(monkeypatch)
    assert call("law_search", query=" 저작권법 ")["status"] == "ok"
    assert FakeClient.calls[0][1]["query"] == "저작권법"


# --- 6. lnkLsOrdJo_search jo ------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("jo,jobr,expect_jo,expect_jobr", [
    ("제11조", None, 11, None),
    ("제11조의2", None, 11, 2),
    ("11의2", None, 11, 2),
    ("0020", None, 20, None),
    (20, None, 20, None),
    ("002002", None, 20, 2),
    ("제20조", 3, 20, 3),
    ("제20조의3", 3, 20, 3),
])
def test_lnkLsOrdJo_jo_forms(monkeypatch, jo, jobr, expect_jo, expect_jobr):
    _, call = _tools(monkeypatch)
    out = call("lnkLsOrdJo_search", knd="002118", jo=jo, jobr=jobr)
    assert out["status"] == "ok", out
    sent = FakeClient.calls[-1][1]
    assert str(sent["JO"]) == str(expect_jo)
    if expect_jobr is None:
        assert "JOBR" not in sent
    else:
        assert str(sent["JOBR"]) == str(expect_jobr)


@pytest.mark.unit
def test_lnkLsOrdJo_bad_or_conflicting_jo(monkeypatch):
    _, call = _tools(monkeypatch)
    bad = call("lnkLsOrdJo_search", knd="002118", jo="abc")
    assert bad["error_code"] == ErrorCode.VALIDATION_ERROR and "int()" not in bad["message"]
    clash = call("lnkLsOrdJo_search", knd="002118", jo="제20조의2", jobr=3)
    assert clash["error_code"] == ErrorCode.VALIDATION_ERROR and "Conflicting" in clash["message"]


# --- 7. article_citation -------------------------------------------------------------

def _a(cls, text):
    return f'<a class="link {cls}" onclick="fncLsLawPop(\'1\',\'JO\',\'\')">{text}</a>'


def _extract(body, source="신탁법"):
    ex = CitationExtractor()
    return ex.consolidate_citations(ex.parse_citations(f'<div><p>{body}</p></div>', source))


@pytest.mark.unit
@pytest.mark.parametrize("mst", ["abc", "28 3335", "283335x", "-1"])
def test_article_citation_rejects_non_numeric_mst(monkeypatch, mst):
    _, call = _tools(monkeypatch)
    out = call("article_citation", mst=mst, law_name="저작권법", article=35)
    assert out["status"] == "error" and out["error_code"] == ErrorCode.VALIDATION_ERROR
    assert "numeric" in out["message"]
    assert FakeClient.calls == []


@pytest.mark.unit
def test_range_in_one_link_is_expanded_external():
    """law.go.kr links 「신탁법」 제46조부터 제48조 as one link; every article is listed."""
    body = f"{_a('sfon1', '「신탁법」')} {_a('sfon2', '제46조부터 제48조')}까지의 규정"
    cits = _extract(body, "민법")
    assert [(c.target_law_name, c.target_article) for c in cits] == [("신탁법", 46), ("신탁법", 47), ("신탁법", 48)]
    assert all(c.citation_type == "external" for c in cits)
    assert all(c.range_text == "제46조부터 제48조" for c in cits)
    assert "가지조문" in cits[0].range_note
    assert cits[1].to_dict()["range_text"] == "제46조부터 제48조"


@pytest.mark.unit
def test_range_in_one_link_is_expanded_internal():
    cits = _extract(f"수탁자가 {_a('sfon2', '제33조부터 제37조')}까지의 규정에서 정한 의무를 위반한 경우")
    assert [c.target_article for c in cits] == [33, 34, 35, 36, 37]
    assert {c.citation_type for c in cits} == {"internal"}


@pytest.mark.unit
def test_range_with_branch_end_is_not_invented():
    cits = _extract(f"{_a('sfon2', '제33조부터 제37조의2')}까지")
    assert [(c.target_article, c.target_article_branch) for c in cits] == [(33, None), (37, 2)]
    assert "나열하지 못했습니다" in cits[0].range_note


@pytest.mark.unit
def test_reversed_range_is_not_expanded():
    cits = _extract(f"{_a('sfon2', '제48조부터 제46조')}까지")
    assert [c.target_article for c in cits] == [48]


@pytest.mark.unit
def test_range_across_two_links_lists_the_articles_between():
    cits = _extract(f"{_a('sfon1', '「신탁법」')} {_a('sfon2', '제46조')}부터 {_a('sfon2', '제49조')}까지")
    assert [c.target_article for c in cits] == [46, 47, 48, 49]
    assert {c.target_law_name for c in cits} == {"신탁법"}


@pytest.mark.unit
def test_single_article_citations_have_no_range_fields():
    cits = _extract(f"{_a('sfon1', '「신탁법」')} {_a('sfon2', '제46조')}")
    assert len(cits) == 1 and "range_text" not in cits[0].to_dict()


@pytest.mark.unit
def test_documentation_examples_are_real_and_unambiguous():
    server = server_mod.create_server()
    doc = server._tool_manager.get_tool("article_citation").fn.__doc__
    assert "제37조의2" not in doc
    instructions = server._mcp_server.instructions
    assert "제300조" in instructions and "030000" in instructions


# --- 8. ids, dates, OC advice --------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("tool,kwargs", [
    ("prec_service", {"id": "abc"}), ("detc_service", {"id": "1a"}), ("expc_service", {"id": "x"}),
    ("eflaw_service", {"id": "abc"}), ("law_service", {"mst": "abc"}),
])
def test_non_numeric_id_is_validation_error(monkeypatch, tool, kwargs):
    _, call = _tools(monkeypatch)
    out = call(tool, **kwargs)
    assert out["status"] == "error" and out["error_code"] == ErrorCode.VALIDATION_ERROR, out
    assert "not your fault" not in json.dumps(out, ensure_ascii=False)
    assert FakeClient.calls == []


@pytest.mark.unit
def test_numeric_ids_still_pass(monkeypatch):
    _, call = _tools(monkeypatch, _service_fake({"detc": FULL_DETC}))
    assert call("detc_service", id=150780)["status"] == "ok"


@pytest.mark.unit
@pytest.mark.parametrize("date", ["abc", "20251301", "2025-05-01", "2025050"])
def test_admrul_search_bad_date_is_structured(monkeypatch, date):
    server, call = _tools(monkeypatch)
    out = call("admrul_search", query="학교", date=date)
    assert out["status"] == "error" and out["error_code"] == ErrorCode.VALIDATION_ERROR
    assert "date" in out["message"]
    assert FakeClient.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("date", [20250501, "20250501"])
def test_admrul_search_date_int_or_str(monkeypatch, date):
    _, call = _tools(monkeypatch)
    call("admrul_search", query="학교", date=date)
    assert str(FakeClient.calls[-1][1]["date"]) == "20250501"


@pytest.mark.unit
def test_missing_oc_advice_matches_transport(monkeypatch):
    monkeypatch.delenv("OC", raising=False)
    try:
        with pytest.raises(ValueError) as stdio:
            params_mod.resolve_oc()
        assert "oc='your_value'" in str(stdio.value)

        params_mod.set_ignore_oc_override(True)
        with pytest.raises(ValueError) as http:
            params_mod.resolve_oc(override_oc="abc")
        msg = str(http.value)
        assert "ignored in HTTP mode" in msg and "oc='your_value'" not in msg
    finally:
        params_mod.set_ignore_oc_override(False)


# --- 5b. list tools whose query defaults to "*" ------------------------------------------

LIST_TOOLS = {
    "admrul_search": {}, "cgm_expc_search": {"ministry": "국토교통부"}, "committee_search": {"committee": "개인정보보호위원회"},
    "decc_search": {}, "detc_search": {}, "dlytrm_search": {}, "elaw_search": {}, "expc_search": {},
    "lnkLsOrdJo_search": {}, "lnkLs_search": {}, "ls_rlt_search": {}, "lstrm_ai_search": {},
    "ordin_search": {}, "prec_search": {}, "special_decc_search": {"tribunal": "조세심판원"}, "trty_search": {},
}


@pytest.mark.unit
@pytest.mark.parametrize("tool", sorted(LIST_TOOLS))
@pytest.mark.parametrize("blank", ["", "  "])
def test_blank_query_on_list_tools_is_validation_error(monkeypatch, tool, blank):
    _, call = _tools(monkeypatch)
    out = call(tool, query=blank, **LIST_TOOLS[tool])
    assert out["status"] == "error" and out["error_code"] == ErrorCode.VALIDATION_ERROR, out
    assert FakeClient.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("tool", sorted(LIST_TOOLS))
def test_default_query_still_reaches_upstream(monkeypatch, tool):
    _, call = _tools(monkeypatch)
    out = call(tool, **LIST_TOOLS[tool])
    assert out.get("error_code") != ErrorCode.VALIDATION_ERROR, out
    assert FakeClient.calls


# --- review follow-ups ---------------------------------------------------------------

from lexlink.client import detect_upstream_body_error  # noqa: E402
from test_amendment import load  # noqa: E402


@pytest.mark.unit
def test_13_digit_admrul_id_is_accepted(monkeypatch):
    _, call = _tools(monkeypatch, _service_fake({"admrul": '{"AdmRulService": {"행정규칙명": "x"}}'}))
    out = call("admrul_service", id="2100000245624")
    assert out["status"] == "ok", out
    assert call("admrul_service", id="1" * 31)["error_code"] == ErrorCode.VALIDATION_ERROR


@pytest.mark.unit
@pytest.mark.parametrize("fmt,body", [
    ("XML", '<?xml version="1.0" encoding="utf-8"?><Law>일치하는 고용노동부 법령해석이 없습니다.  법령해석명을 확인하여 주십시오.</Law>'),
    ("JSON", '{"Law": "일치하는 고용노동부 법령해석이 없습니다.  법령해석명을 확인하여 주십시오."}'),
    ("XML", '<?xml version="1.0" encoding="utf-8"?><Law>일치하는 조세심판원 특별행정심판재결례이 없습니다.  특별행정심판명을 확인하여 주십시오.</Law>'),
    ("JSON", '{"Law": "일치하는 조세심판원 특별행정심판재결례이 없습니다.  특별행정심판명을 확인하여 주십시오."}'),
])
def test_multiword_no_match_is_not_found_in_every_type(fmt, body):
    err = detect_upstream_body_error(body, fmt, target="moelCgmExpc", endpoint=SERVICE)
    assert err["error_code"] == ErrorCode.NOT_FOUND


@pytest.mark.unit
@pytest.mark.parametrize("fmt", ["XML", "JSON"])
def test_cgm_and_special_service_unknown_id_is_not_found(monkeypatch, fmt):
    text = "일치하는 고용노동부 법령해석이 없습니다.  법령해석명을 확인하여 주십시오."
    body = f'<?xml version="1.0" encoding="utf-8"?><Law>{text}</Law>' if fmt == "XML" else json.dumps({"Law": text}, ensure_ascii=False)
    monkeypatch.setattr(server_mod, "LawAPIClient", lambda *a, **k: _routing_client(body, body))
    monkeypatch.setenv("OC", "unit-test-oc")
    server = server_mod.create_server()
    for tool, kw in (("cgm_expc_service", {"ministry": "고용노동부"}), ("special_decc_service", {"tribunal": "조세심판원"})):
        out = server._tool_manager.get_tool(tool).fn(id="88", type=fmt, **kw)
        assert out["error_code"] == ErrorCode.NOT_FOUND, (tool, out)


@pytest.mark.unit
def test_query_keyed_no_linkage_text_stays_ok():
    body = '{"Law": "일치하는 법령용어-조문 연계 정보가 없습니다. 검색조건을 확인하여 주십시오."}'
    assert detect_upstream_body_error(body, "JSON", target="lstrmRltJo", endpoint=SERVICE) is None


@pytest.mark.unit
def test_empty_body_needs_the_fields_to_be_present(monkeypatch):
    """A message-only body is not "a record with empty fields"."""
    for body, fmt in (('{"Law": "무언가 다른 안내문"}', "JSON"), ('<Law>x</Law>', "XML")):
        _, call = _tools(monkeypatch, _service_fake({"detc": body}))
        out = call("detc_service", id="1", type=fmt)
        assert out.get("warning") != "empty_body"


@pytest.mark.unit
@pytest.mark.parametrize("fmt", ["xml", "XML"])
def test_empty_body_lowercase_type_and_cache_and_sections_full(monkeypatch, fmt):
    xml = ('<DetcService><판시사항><![CDATA[]]></판시사항><결정요지><![CDATA[]]></결정요지>'
           '<전문><![CDATA[]]></전문></DetcService>')
    _, call = _tools(monkeypatch, _service_fake({"detc": xml}))
    for sections in (None, "full", "full", "summary"):   # repeated calls hit the cache
        out = call("detc_service", id="150756", type=fmt, sections=sections)
        assert out.get("warning") == "empty_body", (sections, out)


def _law_fake(old_law_id, old_name):
    class Fake(FakeClient):
        def _service(self, target, params, response_type):
            if target == "law" and params.get("MST") == "999":
                d = json.loads(load("law_283335_nojo.json"))
                d["법령"]["기본정보"]["법령ID"] = old_law_id
                d["법령"]["기본정보"]["법령명_한글"] = old_name
                return self._ok(json.dumps(d, ensure_ascii=False))
            return super()._service(target, params, response_type)
    return Fake


@pytest.mark.unit
def test_diff_other_law_without_article_gives_no_verdict(monkeypatch):
    _, call = _tools(monkeypatch, _law_fake("009999", "전혀 다른 법"))
    out = call("article_amendment_diff", mst_old="999", mst_new="283335", article=35, article_branch=5)
    assert out["status"] == "error" and out["error_code"] == ErrorCode.VALIDATION_ERROR
    assert "009999" in out["message"] and "has_changes" not in out


@pytest.mark.unit
def test_diff_renamed_law_keeps_its_verdict(monkeypatch):
    _, call = _tools(monkeypatch, _law_fake("000798", "구 저작권법"))
    out = call("article_amendment_diff", mst_old="999", mst_new="283335", article=35, article_branch=5)
    assert out["status"] == "ok" and "added" in out["summary"]
    assert "warning" not in out


@pytest.mark.unit
def test_range_and_explicit_repeat_are_deduplicated():
    body = (f"{_a('sfon1', '「신탁법」')} {_a('sfon2', '제46조부터 제48조')}까지 및 {_a('sfon2', '제47조')}")
    cits = _extract(body, "민법")
    assert [c.target_article for c in cits] == [46, 47, 48]
    plain = _extract(f"{_a('sfon1', '「신탁법」')} {_a('sfon2', '제46조')}, {_a('sfon2', '제46조')}", "민법")
    assert [c.target_article for c in plain] == [46, 46]   # repeats outside ranges are kept


@pytest.mark.unit
def test_range_clones_have_no_borrowed_ref_id():
    cits = _extract(f"{_a('sfon2', '제33조부터 제35조')}까지")
    assert cits[0].to_dict()["ref_id"] == "1"
    assert [c.to_dict()["ref_id"] for c in cits[1:]] == [None, None]


@pytest.mark.unit
def test_lnkLsOrdJo_non_numeric_jobr_is_validation_error(monkeypatch):
    _, call = _tools(monkeypatch)
    out = call("lnkLsOrdJo_search", knd="002118", jo=20, jobr="abc")
    assert out["error_code"] == ErrorCode.VALIDATION_ERROR and "jobr" in out["message"]
    assert FakeClient.calls == []


@pytest.mark.unit
def test_diff_other_law_with_article_on_both_sides_is_a_validation_error(monkeypatch):
    class Fake(FakeClient):
        def _service(self, target, params, response_type):
            if target == "law" and params.get("MST") == "888":
                res = super()._service(target, {**params, "MST": "283335"}, response_type)
                d = json.loads(res["raw_content"])
                d["법령"]["기본정보"]["법령ID"] = "009999"
                d["법령"]["기본정보"]["법령명_한글"] = "전혀 다른 법"
                return self._ok(json.dumps(d, ensure_ascii=False))
            return super()._service(target, params, response_type)

    _, call = _tools(monkeypatch, Fake)
    out = call("article_amendment_diff", mst_old="888", mst_new="283335", article=35, article_branch=5)
    assert out["status"] == "error" and out["error_code"] == ErrorCode.VALIDATION_ERROR, out
    assert "009999" in out["message"] and "has_changes" not in out
