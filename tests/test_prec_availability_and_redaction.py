"""Unit tests: NOT_FOUND for bodyless case text, OC redaction, summary fallback, cache isolation."""

import glob
import json
import logging
import re

import httpx
import pytest

from lexlink._helpers import annotate_prec_body_availability, run_service
from lexlink.cache import get_cache
from lexlink.client import LawAPIClient, detect_upstream_body_error, redact_oc
from lexlink.errors import ErrorCode

FAKE_OC = "unit-test-oc"
SERVICE = "/DRF/lawService.do"

NO_MATCH_JSON = '{"Law":"일치하는 판례가 없습니다.  판례일련번호를 확인하여 주시기 바랍니다."}'
NO_MATCH_XML = '<?xml version="1.0" encoding="UTF-8"?><Law>일치하는 판례가 없습니다.</Law>'


@pytest.fixture(autouse=True)
def _fresh_cache():
    get_cache().invalidate()
    yield
    get_cache().invalidate()


# --- redact_oc ---------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("src,expected", [
    ("/DRF/lawService.do?OC=abc&target=prec&ID=1", "/DRF/lawService.do?target=prec&ID=1"),
    ("?target=prec&OC=abc&ID=1", "?target=prec&ID=1"),
    ("?target=prec&OC=abc", "?target=prec"),
    ("?OC=abc", ""),
    ("?OC=abc&amp;target=prec", "?target=prec"),
    ("?target=x&amp;OC=abc&amp;ID=1", "?target=x&amp;ID=1"),
    ("?target=x&oc=abc&ID=1", "?target=x&ID=1"),
    ("?a=1\\u0026OC=abc\\u0026b=2", "?a=1\\u0026b=2"),
    ("?a=1&DOC=1", "?a=1&DOC=1"),
    ('{"u":"/x?OC=abc"}', '{"u":"/x"}'),
])
def test_redact_oc_table(src, expected):
    assert redact_oc(src) == expected


@pytest.mark.unit
def test_redact_oc_literal_value_only_when_long():
    assert redact_oc("token unit-test-oc here", FAKE_OC) == "token *** here"
    assert redact_oc("legal g4c text", "g4c") == "legal g4c text"


def _client_with_body(body: str) -> LawAPIClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, request=request)

    client = LawAPIClient(base_url="http://law.test")
    client.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return client


@pytest.mark.unit
def test_client_get_redacts_oc_json_and_xml():
    url = f"/DRF/lawService.do?OC={FAKE_OC}&target=prec&ID=1&type=HTML"
    json_body = json.dumps({"PrecSearch": {"prec": [{"판례상세링크": url, "법령상세링크": url}]}})
    xml_body = (
        f"<PrecSearch><prec><판례상세링크>/DRF/lawService.do?OC={FAKE_OC}&amp;target=prec&amp;ID=1"
        f"</판례상세링크><법령상세링크>/DRF/lawService.do?target=law&amp;OC={FAKE_OC}</법령상세링크>"
        "</prec></PrecSearch>"
    )
    for body, rtype in ((json_body, "JSON"), (xml_body, "XML")):
        out = _client_with_body(body).get(
            "/DRF/lawSearch.do", {"OC": FAKE_OC, "target": "prec", "query": "x"}, rtype
        )
        assert out["status"] == "ok"
        assert FAKE_OC not in out["raw_content"]
        assert "target=prec" in out["raw_content"] or "target=law" in out["raw_content"]


@pytest.mark.unit
def test_client_get_exception_message_redacted():
    def handler(request):
        raise RuntimeError(f"boom {request.url}")

    client = LawAPIClient(base_url="http://law.test")
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    out = client.get(SERVICE, {"OC": FAKE_OC, "target": "prec", "ID": "1"}, "JSON")
    assert out["status"] == "error"
    assert FAKE_OC not in out["message"]


# --- NOT_FOUND ---------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("body,rtype", [(NO_MATCH_JSON, "JSON"), (NO_MATCH_XML, "XML")])
def test_prec_no_match_is_not_found(body, rtype):
    out = _client_with_body(body).get(
        SERVICE, {"OC": FAKE_OC, "target": "prec", "ID": "1"}, rtype
    )
    assert out["status"] == "error"
    assert out["error_code"] == ErrorCode.NOT_FOUND
    assert "국세법령정보시스템" in out["message"]
    assert any("dat_src_nm" in h for h in out["hints"])


@pytest.mark.unit
@pytest.mark.parametrize("target,word", [("detc", "결정례"), ("expc", "해석례")])
def test_other_targets_no_match_is_not_found(target, word):
    err = detect_upstream_body_error(
        f'{{"Law":"일치하는 {word}가 없습니다."}}', "JSON",
        request_id="r", target=target, endpoint=SERVICE,
    )
    assert err["error_code"] == ErrorCode.NOT_FOUND
    assert target in err["message"]


@pytest.mark.unit
def test_long_real_body_quoting_phrase_stays_ok():
    body = json.dumps({"PrecService": {
        "판시사항": "x", "판례내용": "원심은 일치하는 증거가 없습니다 라고 판단하였다. " + "가" * 600,
    }}, ensure_ascii=False)
    assert len(body) > 500
    out = _client_with_body(body).get(SERVICE, {"OC": FAKE_OC, "target": "prec", "ID": "1"}, "JSON")
    assert out["status"] == "ok"


@pytest.mark.unit
def test_no_match_search_endpoint_not_flagged():
    assert detect_upstream_body_error(
        NO_MATCH_JSON, "JSON", target="prec", endpoint="/DRF/lawSearch.do"
    ) is None


@pytest.mark.unit
def test_no_law_match_is_not_found_on_service_ok_on_search():
    body = '{"Law":"일치하는 법령이 없습니다."}'
    out = _client_with_body(body).get(SERVICE, {"OC": FAKE_OC, "target": "law", "MST": "1"}, "JSON")
    assert out["status"] == "error"
    assert out["error_code"] == ErrorCode.NOT_FOUND
    assert "MST" in out["message"]
    out = _client_with_body(body).get("/DRF/lawSearch.do", {"OC": FAKE_OC, "target": "law"}, "JSON")
    assert out["status"] == "ok"
    assert out["warning"] == "no_match"


class _StubClient:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def get(self, endpoint, params, response_type):
        self.calls += 1
        return dict(self.response)


def _svc(stub, rtype="JSON", **kw):
    return run_service(
        get_client=lambda: stub, target="prec",
        snake_params={"oc": FAKE_OC, "target": "prec", "id": "1", "type": rtype},
        response_type=rtype,
        **kw,
    )


@pytest.mark.unit
def test_not_found_not_cached():
    resp = _client_with_body(NO_MATCH_JSON).get(
        SERVICE, {"OC": FAKE_OC, "target": "prec", "ID": "1"}, "JSON"
    )
    stub = _StubClient(resp)
    assert _svc(stub, rtype="JSON")["status"] == "error"
    assert _svc(stub, rtype="JSON")["status"] == "error"
    assert stub.calls == 2


# --- summary fallback & cache mutation --------------------------------------

JSON_EMPTY = json.dumps({"PrecService": {"판시사항": "", "판결요지": "", "판례내용": "본문입니다"}}, ensure_ascii=False)
JSON_FULL = json.dumps({"PrecService": {"판시사항": "사항", "판결요지": "요지", "판례내용": "본문입니다"}}, ensure_ascii=False)
XML_EMPTY = ("<PrecService><판시사항><![CDATA[]]></판시사항><판결요지><![CDATA[]]></판결요지>"
             "<판례내용><![CDATA[본문입니다]]></판례내용></PrecService>")
XML_FULL = ("<PrecService><판시사항><![CDATA[사항]]></판시사항><판결요지>요지</판결요지>"
            "<판례내용><![CDATA[본문입니다]]></판례내용></PrecService>")
REQ = ["판시사항", "판결요지"]


def _ok(raw, rtype):
    return {"status": "ok", "upstream_type": rtype, "raw_content": raw}


@pytest.mark.unit
@pytest.mark.parametrize("raw,rtype", [(JSON_EMPTY, "JSON"), (XML_EMPTY, "XML")])
def test_summary_fallback_keeps_body(raw, rtype):
    out = _svc(_StubClient(_ok(raw, rtype)), sections="summary",
               full_text_fields=["판례내용"], summary_required_fields=REQ, rtype=rtype)
    assert out["sections"] == "summary_fallback"
    assert "본문입니다" in out["raw_content"]
    assert "판례내용" in out["warning"]


@pytest.mark.unit
@pytest.mark.parametrize("raw,rtype", [(JSON_FULL, "JSON"), (XML_FULL, "XML")])
def test_normal_summary_strips_and_does_not_poison_cache(raw, rtype):
    stub = _StubClient(_ok(raw, rtype))
    kw = dict(full_text_fields=["판례내용"])
    summ = _svc(stub, sections="summary", summary_required_fields=REQ, rtype=rtype, **kw)
    assert summ["sections"] == "summary"
    assert "본문입니다" not in summ["raw_content"]
    full = _svc(stub, rtype=rtype, **kw)
    assert "본문입니다" in full["raw_content"]
    assert "sections" not in full


# --- annotate ---------------------------------------------------------------

@pytest.mark.unit
def test_annotate_list_and_single_dict():
    resp = {"ranked_data": {"prec": [
        {"데이터출처명": "국세법령정보시스템"}, {"데이터출처명": "대법원"}]}}
    out = annotate_prec_body_availability(resp)
    assert out["ranked_data"]["prec"][0]["본문제공"] == "API 미제공"
    assert "본문제공" not in out["ranked_data"]["prec"][1]
    single = {"ranked_data": {"prec": {"데이터출처명": "국세법령정보시스템"}}}
    assert annotate_prec_body_availability(single)["ranked_data"]["prec"]["본문제공"] == "API 미제공"
    assert annotate_prec_body_availability({"status": "ok"}) == {"status": "ok"}


# --- logging ----------------------------------------------------------------

@pytest.mark.unit
def test_httpx_logger_not_verbose():
    import lexlink.client  # noqa: F401
    assert logging.getLogger("httpx").level >= logging.WARNING


@pytest.mark.unit
def test_fixtures_only_use_placeholder_oc():
    files = glob.glob("tests/fixtures/*")
    assert files
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for m in re.finditer(r"OC=([^&\"\s<>\\]*)", fh.read(), re.I):
                assert m.group(1) == "test", f
