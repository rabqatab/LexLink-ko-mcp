"""
HTTP client for law.go.kr Open API.

This module provides a robust HTTP client with timeout handling,
error normalization, and request logging.
"""

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

            # Return response
            return self._passthrough_response(response, request_id, response_type)

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
                message=f"Unexpected error: {str(e)}",
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
        format_type: str
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

        Returns:
            Response with raw content, or error if upstream body contains error
        """
        body = response.text

        # Detect auth failure (HTTP 200 but body says auth failed)
        if "사용자 정보 검증에 실패하였습니다" in body:
            logger.warning(f"Upstream auth failure detected in response body")
            return create_error_response(
                error_code=ErrorCode.UPSTREAM_ERROR,
                message="법제처 API 인증 실패: 사용자 정보 검증에 실패하였습니다",
                request_id=request_id,
                hints=[
                    "서버 IP가 open.law.go.kr에 등록되어 있는지 확인하세요",
                    "OC 값이 올바른지 확인하세요 (이메일 ID 부분만 사용)",
                    "Register your server IP at open.law.go.kr",
                ]
            )

        # Detect "no matching law" (HTTP 200 but body says no match)
        if "일치하는 법령이 없습니다" in body:
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
