"""
HTTP client for law.go.kr Open API.

This module provides a robust HTTP client with timeout handling,
error normalization, and request logging.
"""

import logging
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
        self.client = httpx.Client(timeout=timeout)

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
        response_type: Literal["HTML", "XML", "JSON"] = "XML"
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

            elapsed_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"API Response: {response.status_code}",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "elapsed_ms": elapsed_ms,
                }
            )

            # Return response (XML or HTML)
            # Note: JSON format is not supported by law.go.kr API despite documentation
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

    def _passthrough_response(
        self,
        response: httpx.Response,
        request_id: str,
        format_type: str
    ) -> dict:
        """
        Return response content as-is for client-side parsing.

        Note: law.go.kr API does not support JSON format despite documentation.
        JSON requests return HTML error pages, which are passed through.

        Args:
            response: HTTP response from law.go.kr
            request_id: Request ID for tracking
            format_type: Response format ("HTML", "XML", or "JSON")

        Returns:
            Response with raw content
        """
        return {
            "status": "ok",
            "request_id": request_id,
            "upstream_type": format_type,
            "raw_content": response.text,
        }
