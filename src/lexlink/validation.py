"""
Parameter validation functions for law.go.kr API parameters.

This module provides validation for date ranges to ensure they meet
the API's format requirements before sending requests upstream.
"""

import json
import re
from typing import Optional, Union


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


# ---------------------------------------------------------------------------
# jo (article number) input normalization
# ---------------------------------------------------------------------------

JO_FORMAT_HINTS = [
    "조문 번호는 6자리 코드(앞 4자리 조번호 + 뒤 2자리 가지번호)로 전달됩니다. 예: 제35조 → 003500, 제35조의5 → 003505",
    "다음 형식은 자동 변환됩니다: 35, '35', '35의5', '제35조의5', '35-5', '(35,5)', '003505'",
    "Article codes are 6 digits: 4-digit article + 2-digit branch (제35조의5 → 003505)",
]


class JoFormatError(ValueError):
    """Raised when a jo (article number) value cannot be normalized."""

    def __init__(self, message: str, hints: Optional[list[str]] = None):
        super().__init__(message)
        self.hints = hints if hints is not None else list(JO_FORMAT_HINTS)


# 제35조의5 / 35조의5 / 35의5 / 35조 / 35 (optional whitespace, full-width-free)
_JO_KOREAN_RE = re.compile(
    r"^제?\s*(\d{1,4})\s*조?\s*(?:의\s*(\d{1,2}))?$"
)
# 35-5, 35_5, 35.5, 35/5, 35:5, 35,5, (35,5), [35, 5]
_JO_SEPARATED_RE = re.compile(
    r"^[\(\[]?\s*(\d{1,4})\s*[-_./:,]\s*(\d{1,2})\s*[\)\]]?$"
)


def normalize_jo(value: Union[str, int, None]) -> Optional[str]:
    """
    Normalize a user-supplied article number to the 6-digit law.go.kr JO code.

    Accepted forms (all → "003505" unless noted):
        35              → "003500"   (int or str: main article)
        "35의5"         → "003505"
        "제35조의5"     → "003505"
        "제35조"        → "003500"
        "35-5", "35,5", "(35,5)", "35.5" → "003505"
        "003505"        → "003505"   (already a 6-digit code: passed through)
        "0035"          → "003500"   (1-4 digit string: treated as article number)

    Returns None for None / empty input (meaning "no jo filter").

    Raises:
        JoFormatError: if the value is not a recognizable article reference
                       (carries `.hints` for the structured error response).
    """
    if value is None:
        return None

    text = str(value).strip()
    if text == "":
        return None

    # Normalize full-width digits / punctuation that LLMs or copy-paste may produce
    text = text.translate(str.maketrans("０１２３４５６７８９（）～－", "0123456789()~-"))
    text = re.sub(r"\s+", " ", text)

    # Exactly 6 digits: already the upstream code
    if re.fullmatch(r"\d{6}", text):
        article, branch = int(text[:4]), int(text[4:])
        if article < 1:
            raise JoFormatError(
                f"jo 6자리 코드의 조번호(앞 4자리)가 0입니다: {text}"
            )
        return text

    # 5 digits is ambiguous (e.g. "35505" could be 355의5 or 35의50) — reject
    if re.fullmatch(r"\d{5}", text):
        raise JoFormatError(
            f"jo 값 '{text}'은(는) 5자리여서 해석이 모호합니다. 6자리 코드(예: 003505) 또는 '35의5' 형식으로 전달하세요."
        )

    m = _JO_KOREAN_RE.fullmatch(text) or _JO_SEPARATED_RE.fullmatch(text)
    if not m:
        raise JoFormatError(
            f"jo 값 '{text}'을(를) 조문 번호로 해석할 수 없습니다. "
            f"Could not parse '{text}' as an article number."
        )

    article = int(m.group(1))
    branch = int(m.group(2)) if m.group(2) is not None else 0

    try:
        return format_article_number(article, branch)
    except ValueError as e:
        raise JoFormatError(f"jo 값 '{text}' 범위 오류: {e}") from e


def describe_jo(code: str) -> str:
    """Render a 6-digit JO code as human-readable Korean (003505 → 제35조의5)."""
    if not code or not re.fullmatch(r"\d{6}", code):
        return str(code)
    article, branch = int(code[:4]), int(code[4:])
    return f"제{article}조의{branch}" if branch else f"제{article}조"


# Matches a real article element (<조문>, <조문 id=...>, <조문단위>), but NOT
# 기본정보 fields such as <조문시행일자문자열> / <조문별시행일자>.
_XML_ARTICLE_RE = re.compile(r"<조문(?:단위)?(?:\s[^>]*)?>")


def response_has_article(raw_content: Optional[str], response_type: str) -> bool:
    """
    Check whether a lawService (law/eflaw/lawjosub/eflawjosub) body contains
    article content.

    law.go.kr returns HTTP 200 and only `기본정보` (or `{}`) when the requested
    JO does not exist, so a successful HTTP call does not imply the article exists.

    Args:
        raw_content: Response body
        response_type: "JSON", "XML" or "HTML" (HTML is assumed to be present)
    """
    if not raw_content or not raw_content.strip():
        return False

    rtype = (response_type or "").upper()

    if rtype == "JSON":
        try:
            data = json.loads(raw_content)
        except ValueError:
            return False
        return _json_has_article(data)

    if rtype == "XML":
        return bool(_XML_ARTICLE_RE.search(raw_content))

    # HTML (or unknown): cannot judge structurally — treat as present
    return True


def _json_has_article(node, depth: int = 0) -> bool:
    """Recursively look for a non-empty 조문 / 조문단위 key (max depth 3)."""
    if depth > 3 or not isinstance(node, dict):
        return False
    for key in ("조문", "조문단위"):
        val = node.get(key)
        if val not in (None, "", [], {}):
            return True
    return any(_json_has_article(v, depth + 1) for v in node.values() if isinstance(v, dict))


def extract_law_name(raw_content: Optional[str], response_type: str) -> Optional[str]:
    """Best-effort extraction of 법령명_한글 from a lawService body (for error context)."""
    if not raw_content:
        return None
    m = re.search(r"법령명_한글[\"']?\s*[:>]\s*(?:<!\[CDATA\[)?\s*[\"']?([^\"'<\]]+)", raw_content)
    return m.group(1).strip() if m else None
