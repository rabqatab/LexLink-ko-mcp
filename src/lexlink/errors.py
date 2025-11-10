"""
Error codes and standardized error response builders.

This module provides consistent error handling across the LexLink server,
ensuring users receive actionable error messages with resolution hints.
"""

from typing import Optional


class ErrorCode:
    """Standardized error codes for LexLink."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    """Parameter validation failed (format, range, type)."""

    TIMEOUT = "TIMEOUT"
    """HTTP request to law.go.kr API timed out."""

    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    """law.go.kr API returned an error response."""

    INTERNAL_ERROR = "INTERNAL_ERROR"
    """Unexpected server error (should not occur in normal operation)."""


def create_error_response(
    error_code: str,
    message: str,
    hints: Optional[list[str]] = None,
    request_id: Optional[str] = None,
    **extra
) -> dict:
    """
    Create standardized error response.

    Args:
        error_code: Error code from ErrorCode class
        message: Human-readable error message
        hints: Optional list of resolution suggestions
        request_id: Optional request ID for tracking
        **extra: Additional context fields

    Returns:
        Error response dict with status="error"

    Example:
        >>> create_error_response(
        ...     ErrorCode.VALIDATION_ERROR,
        ...     "Invalid date format",
        ...     hints=["Use format YYYYMMDD~YYYYMMDD", "Example: 20240101~20241231"],
        ...     request_id="123-456"
        ... )
        {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid date format",
            "hints": ["Use format YYYYMMDD~YYYYMMDD", "Example: 20240101~20241231"],
            "request_id": "123-456"
        }
    """
    response = {
        "status": "error",
        "error_code": error_code,
        "message": message,
    }

    if hints:
        response["hints"] = hints

    if request_id:
        response["request_id"] = request_id

    # Add any extra fields
    response.update(extra)

    return response


def get_http_error_hints(status_code: int) -> list[str]:
    """
    Get contextual hints based on HTTP status code from upstream API.

    Args:
        status_code: HTTP status code from law.go.kr

    Returns:
        List of actionable hints for the user

    Example:
        >>> get_http_error_hints(403)
        [
            "Check that OC parameter is provided and valid",
            "Verify OC format: email local part only (g4c@korea.kr → g4c)",
            ...
        ]
    """
    hints_map = {
        403: [
            "Check that OC parameter is provided and valid",
            "Verify OC format: email local part only (g4c@korea.kr → g4c)",
            "Check if your IP is blocked by law.go.kr",
        ],
        404: [
            "Verify the law ID or MST exists",
            "Check endpoint URL is correct",
            "Try searching for the law first to get valid ID",
        ],
        429: [
            "Rate limit exceeded - too many requests",
            "Wait a few seconds before retrying",
            "Reduce query frequency",
        ],
        500: [
            "law.go.kr internal error - not your fault",
            "Retry after a few seconds",
            "Try a different query to isolate issue",
        ],
        502: [
            "law.go.kr gateway error - service may be down",
            "Retry after a minute",
            "Check law.go.kr service status",
        ],
        503: [
            "law.go.kr service unavailable",
            "Retry after a minute",
            "Service may be undergoing maintenance",
        ],
    }

    return hints_map.get(
        status_code,
        [f"Unexpected HTTP {status_code} error - check logs for details"]
    )
