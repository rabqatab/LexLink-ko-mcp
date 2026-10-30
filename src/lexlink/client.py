"""
HTTP client for law.go.kr Open API.

This module provides a robust HTTP client with timeout handling,
error normalization, and request logging.
"""

import json
import logging
import re
import time
import uuid
from typing import Literal
from urllib.parse import urlencode

import httpx

from .errors import ErrorCode, create_error_response, get_http_error_hints


# Set up module logger
logger = logging.getLogger(__name__)

# httpx logs full request URLs (including OC) at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# OC redaction
# ---------------------------------------------------------------------------

_OC_SEP = r"\?|&amp;|&|\\u0026"
_OC_PARAM_RE = re.compile(
    rf'(?P<sep>{_OC_SEP})OC=[^&"\'<>\s\\]*(?P<after>(?:&amp;|&|\\u0026)(?=[^&\s]))?',
    re.I,
)


def _oc_sub(m: "re.Match[str]") -> str:
    sep, after = m.group("sep"), m.group("after")
    if sep == "?":
        # keep "?" only when another param follows
        return "?" if after else ""
    # &OC=x (&next) -> &next ; &OC=x (end) -> removed
    return sep if after else ""


# Structural OC removal (independent of the OC value and its length).
_TAG_WITH_OC_NAME_RE = re.compile(
    r"""<[^<>]*(?<![\w-])name\s*=\s*(?:"OC"|'OC'|OC(?![\w-]))[^<>]*>""", re.I
)
_VALUE_ATTR_RE = re.compile(
    r"""(?<![\w-])value\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'<>=`]+)""", re.I
)
_OC_ASSIGN_RE = re.compile(
    r"""(?<![\w-])(?P<key>(?P<kq>["']?)OC(?P=kq)\s*[:=]\s*)(?P<q>["'])(?:(?!(?P=q)).)*(?P=q)""",
    re.I,
)


def _blank_value_attr(m: "re.Match[str]") -> str:
    return _VALUE_ATTR_RE.sub('value=""', m.group(0))


def _blank_oc_assign(m: "re.Match[str]") -> str:
    q = m.group("q")
    return f"{m.group('key')}{q}{q}"


def redact_oc(text: str, oc: str | None = None) -> str:
    """Remove the OC credential from ``text`` (HTML, JSON, JS or URLs).

    Structural removal runs first and does not depend on ``oc``:
      * HTML fields with ``name="OC"`` (any quote style, ``value`` before or
        after ``name``): the value is blanked, the tag is kept;
      * JS/JSON assignments such as ``OC = 'x'``, ``"OC":"x"``, ``oc: "x"``
        (value blanked; ``DOC="x"`` and similar are untouched);
      * the ``OC=`` query parameter in URLs (``?``, ``&``, ``&amp;``, ``\\u0026``).

    Then, if ``oc`` is given, remaining literal occurrences become ``***``:
      * ``len(oc) >= 6``: plain replacement;
      * shorter values are replaced only when delimited by a quote, ``=`` or
        ``&`` on the left and a quote, ``&``, ``<``, ``>`` or whitespace on the
        right. A short value inside prose is left alone on purpose, so that
        e.g. oc="law" never alters the word "law" in English statute text and
        oc="g4c" never alters Korean prose.
    """
    if not text:
        return text
    text = _TAG_WITH_OC_NAME_RE.sub(_blank_value_attr, text)
    text = _OC_ASSIGN_RE.sub(_blank_oc_assign, text)
    text = _OC_PARAM_RE.sub(_oc_sub, text)
    if oc:
        if len(oc) >= 6:
            text = text.replace(oc, "***")
        else:
            text = re.sub(
                rf"""(?<=["'=&]){re.escape(oc)}(?=["'&<>\s])""", "***", text
            )
    return text


# ---------------------------------------------------------------------------
# Upstream body error detection (HTTP 200 with an error inside the body)
# ---------------------------------------------------------------------------

AUTH_FAILURE_MARKER = "사용자 정보 검증에 실패하였습니다"
NOT_SUBSCRIBED_MARKER = "미신청된 목록/본문에 대한 접근입니다"
ERROR_PAGE_MARKER_RE = re.compile(r'id\s*=\s*["\']error\d{3}["\']', re.I)
_HTML_START_RE = re.compile(r"^\s*(?:<!doctype\s+html|<html)", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
NO_MATCH_RE = re.compile(r"일치하는 \S+ 없습니다")


def _html_headline(body: str) -> str | None:
    """Pull the first <h1>/<h2>/<h3>/<title> text out of an HTML error page."""
    for tag in ("h2", "h1", "h3", "title"):
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.I | re.S)
        if m:
            text = _TAG_RE.sub("", m.group(1)).strip()
            if text:
                return text
    return None


def _not_subscribed_hints(target: str | None) -> list[str]:
    hints = [
        "OC 계정이 이 API(target)를 신청하지 않았습니다. open.law.go.kr 로그인 후 "
        "[OPEN API] → [OPEN API 신청]에서 해당 법령종류(목록/본문)를 체크해 신청하세요.",
        "The OC account has not applied for this API target at open.law.go.kr "
        "(OPEN API → OPEN API 신청). Approval is per law type and per 목록/본문.",
    ]
    if target == "eflaw":
        hints.append(
            "대안: law_service(공포일 기준 본문) 또는 eflaw_josub(시행일 기준 조문 단위 조회)는 "
            "별도 신청 항목이므로 그대로 동작할 수 있습니다."
        )
        hints.append(
            "Alternative: use law_service (announcement-date full text) or eflaw_josub "
            "(effective-date article lookup) while the eflaw 본문 API is pending approval."
        )
    elif target:
        hints.append(f"신청 상태를 확인할 target: {target}")
    return hints


def _service_not_found(request_id: str | None, target: str | None, message: str) -> dict:
    """NOT_FOUND for a bodyless success on lawService.do (wrong id / unknown target)."""
    return create_error_response(
        error_code=ErrorCode.NOT_FOUND,
        message=message,
        hints=[
            "ID(일련번호 등)가 잘못되었을 수 있습니다. 검색 도구 결과의 실제 키(일련번호 등)를 사용하세요",
            "target 이름이 업스트림에서 알 수 없는 값일 수 있습니다",
            *([f"요청 target: {target}"] if target else []),
        ],
        request_id=request_id,
        upstream_target=target,
    )


def _json_body_is_empty(text: str) -> bool:
    """True when ``text`` is a JSON object that is {} or has only empty values."""
    try:
        data = json.loads(text)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    return all(v in ("", None, [], {}) for v in data.values())


def detect_upstream_body_error(
    body: str | None,
    format_type: str,
    *,
    request_id: str | None = None,
    target: str | None = None,
    endpoint: str | None = None,
) -> dict | None:
    """
    Inspect a 2xx response body for law.go.kr error conditions.

    law.go.kr signals many failures with HTTP 200:
      - 0-byte body            → unknown target / wrong endpoint       (EMPTY_RESPONSE)
      - 사용자 정보 검증 실패   → OC / IP not authorised                (UPSTREAM_ERROR)
      - 미신청된 목록/본문      → API not applied for by the OC account (API_NOT_SUBSCRIBED)
      - <div id="error500">    → generic upstream error page            (UPSTREAM_HTML_ERROR)
      - any HTML page when XML/JSON was requested                       (UPSTREAM_HTML_ERROR)

    Returns a structured error dict (status="error") or None when the body looks
    like a normal payload. Anti-bot JS redirect pages are handled before this
    (see LawAPIClient._follow_antibot) and are not re-classified here.
    """
    fmt = (format_type or "").upper()
    text = body or ""

    # 1) Empty body with HTTP 200 → upstream did not recognise the target
    if text.strip() == "" and endpoint == "/DRF/lawService.do":
        return _service_not_found(
            request_id, target,
            "법제처 API가 본문 조회에 빈 응답을 반환했습니다. ID가 잘못되었거나 "
            "해당 target을 알 수 없습니다. law.go.kr returned an empty body for a service call.",
        )
    if text.strip() == "":
        return create_error_response(
            error_code=ErrorCode.EMPTY_RESPONSE,
            message="법제처 API가 빈 응답(0바이트)을 반환했습니다. "
                    "law.go.kr returned an empty body (HTTP 200).",
            hints=[
                "target 이름 또는 엔드포인트(lawSearch/lawService) 확인 — 알 수 없는 target이면 빈 응답이 돌아옵니다",
                "Check the target name and endpoint (lawSearch.do vs lawService.do)",
                *( [f"요청 target: {target}, endpoint: {endpoint}"] if target or endpoint else [] ),
            ],
            request_id=request_id,
            upstream_target=target,
        )

    # 2) Auth failure (existing behaviour, kept as UPSTREAM_ERROR)
    if AUTH_FAILURE_MARKER in text:
        return create_error_response(
            error_code=ErrorCode.UPSTREAM_ERROR,
            message="법제처 API 인증 실패: 사용자 정보 검증에 실패하였습니다",
            request_id=request_id,
            hints=[
                "서버 IP가 open.law.go.kr에 등록되어 있는지 확인하세요",
                "OC 값이 올바른지 확인하세요 (이메일 ID 부분만 사용)",
                "Register your server IP at open.law.go.kr",
            ],
        )

    # 3) "미신청" page: OC account has not applied for this API
    if NOT_SUBSCRIBED_MARKER in text:
        return create_error_response(
            error_code=ErrorCode.API_NOT_SUBSCRIBED,
            message="법제처 Open API 미신청: 미신청된 목록/본문에 대한 접근입니다. "
                    "This API target has not been applied for by the OC account.",
            hints=_not_subscribed_hints(target),
            request_id=request_id,
            upstream_target=target,
        )

    is_html = bool(_HTML_START_RE.match(text)) or "<html" in text[:2048].lower()

    # 4) Generic law.go.kr error page (<div id="error500"> etc.)
    if ERROR_PAGE_MARKER_RE.search(text):
        headline = _html_headline(text)
        return create_error_response(
            error_code=ErrorCode.UPSTREAM_HTML_ERROR,
            message="법제처 API가 오류 페이지를 반환했습니다"
                    + (f": {headline}" if headline else "")
                    + ". law.go.kr returned an error page.",
            hints=[
                "요청 인자(ID/MST/JO 등)와 target 이름이 올바른지 확인하세요",
                "잠시 후 다시 시도하세요 (업스트림 일시 오류일 수 있음)",
                "Check request parameters and retry; this is an upstream (law.go.kr) error page",
            ],
            request_id=request_id,
            upstream_target=target,
            upstream_headline=headline,
        )

    # 5) HTML body when a structured format was requested
    if is_html and fmt in ("XML", "JSON"):
        headline = _html_headline(text)
        return create_error_response(
            error_code=ErrorCode.UPSTREAM_HTML_ERROR,
            message=f"{fmt} 응답을 요청했지만 법제처 API가 HTML 페이지를 반환했습니다"
                    + (f" ({headline})" if headline else "")
                    + f". Expected {fmt} but law.go.kr returned HTML.",
            hints=[
                "이 target은 HTML 전용이거나, 인증/신청 문제 또는 안티봇 페이지일 수 있습니다",
                "type='HTML'로 재시도하거나 OC 신청 상태(open.law.go.kr)를 확인하세요",
                "This target may be HTML-only, or the account/IP is not authorised for it",
            ],
            request_id=request_id,
            upstream_target=target,
            upstream_headline=headline,
        )

    # 6) "일치하는 …가 없습니다" on a service (본문) call: id missing or body not provided.
    # Length bound keeps real judgments that quote the phrase from tripping this.
    if endpoint == "/DRF/lawService.do" and len(text) < 500 and NO_MATCH_RE.search(text):
        if "일치하는 법령이 없습니다" in text:
            message = (
                "일치하는 법령이 없습니다. MST(법령일련번호)가 최신인지 확인하세요. "
                "법령 개정 시 MST가 변경됩니다."
            )
            hints = [
                "법령 개정 시 MST(법령일련번호)가 바뀝니다. 검색 도구로 현행 MST를 다시 확인하세요",
                "업스트림은 '존재하지 않는 ID'와 '본문 미제공'을 구분하지 않습니다",
            ]
        elif target == "prec":
            message = (
                "해당 판례의 본문을 가져올 수 없습니다. 존재하지 않는 판례일련번호이거나, "
                "국가법령정보센터 API가 본문을 제공하지 않는 판례일 수 있습니다"
                "(예: 데이터출처명 국세법령정보시스템)."
            )
            hints = [
                "업스트림은 '존재하지 않는 ID'와 '본문 미제공 판례'를 구분하지 않습니다",
                "prec_search 결과의 데이터출처명을 확인하세요",
                'prec_search(dat_src_nm="대법원")으로 본문 제공 출처만 검색할 수 있습니다',
            ]
        else:
            message = f"일치하는 자료가 없습니다 (target={target}). ID를 확인하세요."
            hints = [
                "업스트림은 '존재하지 않는 ID'와 '본문 미제공'을 구분하지 않습니다",
                "검색 도구 결과의 실제 키(일련번호 등)를 사용하세요",
            ]
        return create_error_response(
            error_code=ErrorCode.NOT_FOUND,
            message=message,
            hints=hints,
            request_id=request_id,
            upstream_target=target,
        )

    # 7) JSON object with no content on a service call ({} or only empty values)
    if (
        endpoint == "/DRF/lawService.do"
        and (fmt == "JSON" or text.lstrip().startswith("{"))
        and _json_body_is_empty(text)
    ):
        return _service_not_found(
            request_id, target,
            "법제처 API가 본문 조회에 빈 JSON 객체를 반환했습니다. ID가 잘못되었거나 "
            "해당 target을 알 수 없습니다. law.go.kr returned an empty JSON object.",
        )

    return None


class LawAPIClient:
    """HTTP client for law.go.kr API with error handling and logging."""

    def __init__(self, base_url: str = "http://www.law.go.kr", timeout: int = 15):
        """
        Initialize HTTP client.

        Args:
            base_url: Base URL for law.go.kr API
            timeout: HTTP request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def build_url(self, endpoint: str, params: dict) -> str:
        """
        Build complete URL with query parameters.

        Args:
            endpoint: API endpoint path (e.g., "/DRF/lawSearch.do")
            params: Query parameters (already mapped to upstream format)

        Returns:
            Complete URL with encoded query string

        Example:
            >>> client = LawAPIClient()
            >>> client.build_url("/DRF/lawSearch.do", {"OC": "g4c", "target": "eflaw"})
            'http://www.law.go.kr/DRF/lawSearch.do?OC=g4c&target=eflaw'
        """
        # Don't encode tilde in date ranges (safe="~")
        query_string = urlencode(params, safe="~")
        return f"{self.base_url}{endpoint}?{query_string}"

    def get(
        self,
        endpoint: str,
        params: dict,
        response_type: Literal["HTML", "XML", "JSON"] = "JSON"
    ) -> dict:
        """
        Execute GET request to law.go.kr API with comprehensive error handling.

        Args:
            endpoint: API endpoint (e.g., "/DRF/lawSearch.do")
            params: Query parameters (must include OC)
            response_type: Expected response format (HTML, XML, or JSON)

        Returns:
            Normalized response dict with status, data, or error

        Examples:
            Success response:
            {
                "status": "ok",
                "request_id": "uuid",
                "upstream_type": "JSON",
                "data": {...}  # or "raw_content" for HTML/XML
            }

            Error response:
            {
                "status": "error",
                "request_id": "uuid",
                "error_code": "TIMEOUT",
                "message": "Request to law.go.kr timed out",
                "hints": [...]
            }
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Ensure type parameter is set
        params["type"] = response_type

        url = self.build_url(endpoint, params)

        # Log request (no PII - only presence indicators)
        logger.info(
            f"API Request: {endpoint}",
            extra={
                "request_id": request_id,
                "endpoint": endpoint,
                "has_oc": "OC" in params,  # Boolean, not value
                "response_type": response_type,
                "param_count": len(params),
            }
        )

        try:
            response = self.client.get(url)
            response.raise_for_status()
            response = self._follow_antibot(response)

            elapsed_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"API Response: {response.status_code}",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "elapsed_ms": elapsed_ms,
                }
            )

            # Return response (with upstream body error detection)
            return self._passthrough_response(
                response, request_id, response_type,
                target=params.get("target"), endpoint=endpoint,
                oc=params.get("OC"),
            )

        except httpx.TimeoutException:
            logger.error(
                "API Timeout",
                extra={"request_id": request_id, "timeout_s": self.timeout}
            )
            return create_error_response(
                error_code=ErrorCode.TIMEOUT,
                message=f"Request to law.go.kr timed out after {self.timeout}s",
                hints=[
                    "The upstream API may be slow or unavailable",
                    "Try reducing the query scope (fewer results)",
                    "Retry after a few seconds",
                    f"Consider increasing timeout (currently {self.timeout}s)",
                ],
                request_id=request_id,
                timeout_s=self.timeout,
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                f"API HTTP Error: {e.response.status_code}",
                extra={
                    "request_id": request_id,
                    "status_code": e.response.status_code,
                }
            )
            return create_error_response(
                error_code=ErrorCode.UPSTREAM_ERROR,
                message=f"law.go.kr API returned error: {e.response.status_code}",
                hints=get_http_error_hints(e.response.status_code),
                request_id=request_id,
                upstream_status=e.response.status_code,
            )

        except Exception as e:
            logger.exception(
                "Unexpected error in HTTP client",
                extra={"request_id": request_id}
            )
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {redact_oc(str(e), params.get('OC'))}",
                hints=[
                    "This is an internal server error",
                    "Check server logs for details",
                    "Report this issue if it persists",
                ],
                request_id=request_id,
            )

    def _follow_antibot(self, response: httpx.Response, max_hops: int = 3) -> httpx.Response:
        """
        Follow law.go.kr JS anti-bot redirects.

        law.go.kr sometimes returns HTML pages with JavaScript redirects
        instead of API data. This method detects and follows them.

        Some endpoints (e.g., aiSearch) don't support the tokenized redirect
        path and return 404. In that case, retry the original URL — the
        anti-bot hop typically sets a session cookie that lets the retry
        succeed.
        """
        original_url = str(response.request.url)

        for i in range(max_hops):
            if "location.assign" not in response.text:
                return response

            path = self._parse_antibot_url(response.text)
            if not path:
                logger.warning(f"Anti-bot page detected but could not parse redirect (hop {i+1})")
                return response

            logger.info(f"Following anti-bot redirect (hop {i+1})")
            response = self.client.get(f"{self.base_url}{path}")

            if response.status_code == 404:
                logger.info("Anti-bot redirect got 404, retrying original URL")
                response = self.client.get(original_url)
                response.raise_for_status()
                return response

            response.raise_for_status()

        return response

    @staticmethod
    def _parse_antibot_url(html: str) -> str | None:
        """
        Parse redirect URL from law.go.kr anti-bot JavaScript.

        Handles two known patterns:
        - Pattern A (concat): x={t:'...', h:'...', o:'...'}; return x.t+x.h+x.o
        - Pattern B (substr): x={o:'...', c:N}; z=M; return o.substr(0,c)+o.substr(c+z)
        """
        # Pattern A: three-part concatenation (t + h + o)
        m = re.search(r"t:'([^']*)',h:'([^']*)'", html)
        if m:
            # Also need 'o' value
            mo = re.search(r"o:'([^']*)'", html)
            if mo:
                return m.group(1) + m.group(2) + mo.group(1)

        # Pattern B: substring slicing
        m = re.search(r"o:'([^']*)',c:(\d+)},z=(\d+)", html)
        if m:
            o, c, z = m.group(1), int(m.group(2)), int(m.group(3))
            return o[:c] + o[c + z:]

        return None

    def _passthrough_response(
        self,
        response: httpx.Response,
        request_id: str,
        format_type: str,
        target: str | None = None,
        endpoint: str | None = None,
        oc: str | None = None,
    ) -> dict:
        """
        Return response content, detecting upstream errors in the body.

        law.go.kr returns HTTP 200 even for auth failures and empty results,
        embedding the error inside XML/JSON body. This method detects known
        error patterns and returns proper error status.

        Args:
            response: HTTP response from law.go.kr
            request_id: Request ID for tracking
            format_type: Response format ("HTML", "XML", or "JSON")
            target: Upstream target name (for context-specific hints)
            endpoint: Endpoint path (for context-specific hints)

        Returns:
            Response with raw content, or error if upstream body contains error
        """
        body = redact_oc(response.text, oc)
        error = detect_upstream_body_error(
            body, format_type, request_id=request_id, target=target, endpoint=endpoint
        )
        if error is not None:
            logger.warning(
                f"Upstream body error detected: {error['error_code']}",
                extra={"request_id": request_id, "target": target},
            )
            return error

        # Detect "no matching law" (HTTP 200 but body says no match)
        # (lawService.do reports this as NOT_FOUND via detect_upstream_body_error)
        if endpoint != "/DRF/lawService.do" and "일치하는 법령이 없습니다" in body:
            return {
                "status": "ok",
                "request_id": request_id,
                "upstream_type": format_type,
                "raw_content": body,
                "warning": "no_match",
                "message": "일치하는 법령이 없습니다. MST(법령일련번호)가 최신인지 확인하세요. 법령 개정 시 MST가 변경됩니다.",
            }

        return {
            "status": "ok",
            "request_id": request_id,
            "upstream_type": format_type,
            "raw_content": body,
        }
