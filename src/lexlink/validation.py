"""
Parameter validation functions for law.go.kr API parameters.

This module provides validation for date ranges to ensure they meet
the API's format requirements before sending requests upstream.
"""

import re


def validate_date_range(date_range: str, param_name: str) -> None:
    """
    Validate date range format (YYYYMMDD~YYYYMMDD).

    The law.go.kr API expects date ranges in the format YYYYMMDD~YYYYMMDD
    with no spaces and a tilde separator.

    Args:
        date_range: Date range string (e.g., "20240101~20241231")
        param_name: Parameter name for error message (e.g., "ef_yd")

    Raises:
        ValueError: If format is invalid

    Examples:
        >>> validate_date_range("20240101~20241231", "ef_yd")  # Valid
        >>> validate_date_range("2024-01-01~2024-12-31", "ef_yd")  # Invalid
        ValueError: ef_yd must be in format YYYYMMDD~YYYYMMDD, got: 2024-01-01~2024-12-31
    """
    pattern = r"^\d{8}~\d{8}$"

    if not re.match(pattern, date_range):
        raise ValueError(
            f"{param_name} must be in format YYYYMMDD~YYYYMMDD "
            f"(e.g., '20240101~20241231'), got: {date_range}"
        )

    # Additional validation: check start <= end
    start_str, end_str = date_range.split("~")
    start_date = int(start_str)
    end_date = int(end_str)

    if start_date > end_date:
        raise ValueError(
            f"{param_name} start date must be <= end date, "
            f"got: {start_str} > {end_str}"
        )
