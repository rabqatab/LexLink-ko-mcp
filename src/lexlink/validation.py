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


def format_article_number(article: int, branch: int = 0) -> str:
    """
    Format article number for law.go.kr API (XXXXXX format).

    Korean legal document structure:
    - 조 (Jo) = Article (main structural unit)
    - 가지조문 = Branch article (e.g., 제15조의2 = Article 15-2)

    The API uses 6-digit format XXXXXX where:
    - First 4 digits = Main article number (zero-padded, 0001-9999)
    - Last 2 digits = Branch article suffix (00 for main, 01-99 for branches)

    Args:
        article: Main article number (1-9999)
        branch: Branch article number (0-99), where:
                - 0 = Main article (조)
                - 1+ = Branch articles (조의1, 조의2, etc.)

    Returns:
        Formatted 6-digit string for the jo parameter

    Raises:
        ValueError: If article or branch number is out of valid range

    Examples:
        >>> format_article_number(2)      # 제2조 (Article 2)
        '000200'
        >>> format_article_number(20)     # 제20조 (Article 20)
        '002000'
        >>> format_article_number(15, 2)  # 제15조의2 (Article 15-2, branch)
        '001502'
        >>> format_article_number(15, 3)  # 제15조의3 (Article 15-3, branch)
        '001503'
        >>> format_article_number(100)    # 제100조 (Article 100)
        '010000'
    """
    if not (1 <= article <= 9999):
        raise ValueError(f"Article number must be 1-9999, got: {article}")
    if not (0 <= branch <= 99):
        raise ValueError(f"Branch number must be 0-99, got: {branch}")

    return f"{article:04d}{branch:02d}"
