"""Unit tests for upstream body error detection in client.py (HTTP 200 with errors inside)."""

import httpx
import pytest

from lexlink.client import LawAPIClient, detect_upstream_body_error
from lexlink.errors import ErrorCode

# Captured from https://www.law.go.kr/DRF/lawService.do?target=eflaw&MST=283335 (2026-10-25)
NOT_SUBSCRIBED_HTML = (
    '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" '
    '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\r\n'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="ko" xml:lang="ko">\r\n<head>\r\n'
    '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">\r\n'
    '<script type="text/javascript" src="/DRF/js/common/jquery/jquery.js"></script>\r\n'
    '<title>국가법령정보 공동활용</title>\r\n</head>\r\n<body>\r\n'
    '<div id="error500">\r\n<div class="error_box">\r\n'
    '<h2>미신청된 목록/본문에 대한 접근입니다.</h2>\r\n'
    '<p>국가법령정보 공동활용 사이트에서 신청 후 이용하여 주시기 바랍니다.</p>\r\n'
    '</div>\r\n</div>\r\n</body>\r\n</html>'
)

GENERIC_ERROR_HTML = (
    '<!DOCTYPE html><html lang="ko"><head><title>국가법령정보 공동활용</title></head><body>'
    '<div id="error500"><h2>요청하신 페이지를 처리하는 중 오류가 발생했습니다.</h2></div>'
    '</body></html>'
)

PLAIN_HTML = "<html><body><table><tr><td>법령</td></tr></table></body></html>"

AUTH_FAIL_XML = (
    '<?xml version="1.0" encoding="UTF-8"?><Law><result>'
    '사용자 정보 검증에 실패하였습니다.</result></Law>'
)

OK_JSON = '{"LawSearch": {"totalCnt": "1", "law": [{"법령명한글": "저작권법"}]}}'
OK_XML = '<?xml version="1.0" encoding="UTF-8"?><LawSearch><totalCnt>1</totalCnt></LawSearch>'
EMPTY_JSON_OBJECT = "{}"

ANTIBOT_HTML = (
    "<html><head><script>var x={t:'/DRF/lawSe',h:'arch.do?OC=x',o:'&target=law'};"
    "location.assign(x.t+x.h+x.o);</script></head></html>"
)


@pytest.mark.unit
def test_not_subscribed_page_is_structured_error():
    err = detect_upstream_body_error(NOT_SUBSCRIBED_HTML, "JSON", request_id="rid", target="eflaw")
    assert err is not None
    assert err["status"] == "error"
    assert err["error_code"] == ErrorCode.API_NOT_SUBSCRIBED
    assert err["request_id"] == "rid"
    assert "미신청" in err["message"]
    assert "not been applied" in err["message"]
    hints = " ".join(err["hints"])
    assert "OPEN API 신청" in hints
    # eflaw-specific alternatives
    assert "law_service" in hints and "eflaw_josub" in hints


@pytest.mark.unit
def test_not_subscribed_hints_without_eflaw_alternatives():
    err = detect_upstream_body_error(NOT_SUBSCRIBED_HTML, "XML", target="prec")
    assert err["error_code"] == ErrorCode.API_NOT_SUBSCRIBED
    assert "eflaw_josub" not in " ".join(err["hints"])
    assert err["upstream_target"] == "prec"


@pytest.mark.unit
def test_generic_error500_page_is_structured_error():
    err = detect_upstream_body_error(GENERIC_ERROR_HTML, "JSON", target="law")
    assert err["error_code"] == ErrorCode.UPSTREAM_HTML_ERROR
    assert "오류가 발생했습니다" in err["message"]
    assert err["upstream_headline"].startswith("요청하신 페이지")


@pytest.mark.unit
def test_html_body_when_structured_format_requested():
    for fmt in ("JSON", "XML"):
        err = detect_upstream_body_error(PLAIN_HTML, fmt, target="drlaw")
        assert err is not None, fmt
        assert err["error_code"] == ErrorCode.UPSTREAM_HTML_ERROR
        assert fmt in err["message"]


@pytest.mark.unit
def test_html_body_is_fine_when_html_requested():
    assert detect_upstream_body_error(PLAIN_HTML, "HTML", target="drlaw") is None


@pytest.mark.unit
def test_empty_body_is_structured_error():
    for body in ("", "   ", "\r\n", None):
        err = detect_upstream_body_error(body, "JSON", target="bogusTarget", endpoint="/DRF/lawSearch.do")
        assert err["error_code"] == ErrorCode.EMPTY_RESPONSE
        hints = " ".join(err["hints"])
        assert "target" in hints and "lawSearch/lawService" in hints
        assert "bogusTarget" in hints


@pytest.mark.unit
def test_auth_failure_still_detected():
    err = detect_upstream_body_error(AUTH_FAIL_XML, "XML")
    assert err["error_code"] == ErrorCode.UPSTREAM_ERROR
    assert "인증 실패" in err["message"]


@pytest.mark.unit
def test_normal_payloads_pass_through():
    assert detect_upstream_body_error(OK_JSON, "JSON") is None
    assert detect_upstream_body_error(OK_XML, "XML") is None
    # "{}" is a (useless but) valid JSON body — article detection happens downstream
    assert detect_upstream_body_error(EMPTY_JSON_OBJECT, "JSON") is None


@pytest.mark.unit
def test_antibot_page_still_parsed_by_client():
    """Anti-bot JS redirect handling must stay intact (not swallowed by HTML detection)."""
    assert LawAPIClient._parse_antibot_url(ANTIBOT_HTML) == "/DRF/lawSearch.do?OC=x&target=law"
    sub = "<html><script>var x={o:'/DRF/lawSeXXXarch.do',c:10},z=3;location.assign(...)</script></html>"
    assert LawAPIClient._parse_antibot_url(sub) == "/DRF/lawSearch.do"


# --- end-to-end through LawAPIClient.get with a mocked transport ---------------

def _client_with_body(body: str, status_code: int = 200) -> LawAPIClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body, request=request)

    client = LawAPIClient(base_url="http://law.test")
    client.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return client


@pytest.mark.integration
def test_client_get_returns_not_subscribed_error():
    client = _client_with_body(NOT_SUBSCRIBED_HTML)
    out = client.get("/DRF/lawService.do", {"OC": "x", "target": "eflaw", "MST": "283335"}, "JSON")
    assert out["status"] == "error"
    assert out["error_code"] == ErrorCode.API_NOT_SUBSCRIBED
    assert "raw_content" not in out
    assert out["request_id"]


@pytest.mark.integration
def test_client_get_returns_empty_response_error():
    client = _client_with_body("")
    out = client.get("/DRF/lawSearch.do", {"OC": "x", "target": "nope"}, "JSON")
    assert out["status"] == "error"
    assert out["error_code"] == ErrorCode.EMPTY_RESPONSE


@pytest.mark.integration
def test_client_get_passes_through_json():
    client = _client_with_body(OK_JSON)
    out = client.get("/DRF/lawSearch.do", {"OC": "x", "target": "law"}, "JSON")
    assert out["status"] == "ok"
    assert out["raw_content"] == OK_JSON
    assert out["upstream_type"] == "JSON"


@pytest.mark.integration
def test_client_get_no_match_warning_kept():
    body = '<?xml version="1.0"?><Law><result>일치하는 법령이 없습니다.</result></Law>'
    client = _client_with_body(body)
    # lawService.do: now NOT_FOUND (MST message kept)
    out = client.get("/DRF/lawService.do", {"OC": "x", "target": "law", "MST": "1"}, "XML")
    assert out["status"] == "error"
    assert out["error_code"] == "NOT_FOUND"
    assert "MST" in out["message"]
    # other endpoints keep the ok + warning shape
    out = client.get("/DRF/lawSearch.do", {"OC": "x", "target": "law"}, "XML")
    assert out["status"] == "ok"
    assert out["warning"] == "no_match"
