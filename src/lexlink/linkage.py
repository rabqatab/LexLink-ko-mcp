"""
Pure helpers for the 법령정보 지식베이스 linkage tools and the
자치법규 기준 법령 연계 (ordinance-law linkage) search tool.

Everything here is side-effect free so it can be unit-tested offline:
- jo code normalization ("35", "35의5", "제35조의5", "003505" → "003505")
- 용어관계코드 (trmRltCd) validation
- mode selection for ordinLsCon_search (query / law_id / org → upstream target)
- attaching parsed JSON/XML data to a lawService.do response
"""

import json
import re
from typing import Any, Optional, Union

from ._helpers import ToolValidationError
from .parser import parse_xml_response
from .validation import format_article_number


# 용어관계코드 (trmRltCd) accepted by lstrmRlt / dlytrmRlt
TRM_RLT_CODES = {
    "140301": "동의어",
    "140302": "반의어",
    "140303": "상위어",
    "140304": "하위어",
    "140305": "연관어",
}
_TRM_RLT_BY_NAME = {name: code for code, name in TRM_RLT_CODES.items()}

# "35", "35의5", "제35조", "제35조의5"
_JO_TEXT_RE = re.compile(r"^제?\s*(\d{1,4})\s*조?\s*(?:의\s*(\d{1,2}))?$")


def normalize_jo_code(jo: Union[str, int, None]) -> str:
    """Normalize an article reference to the 6-digit JO code (XXXXYY).

    Accepts: 35, "35", "35의5", "제35조의5", "003505" (already 6 digits).
    Raises ToolValidationError with hints when the value is missing or malformed.
    """
    hints = [
        "Use the article number: jo='35' (제35조)",
        "Branch articles: jo='35의5' (제35조의5)",
        "Or the 6-digit upstream code: jo='003505' (4-digit article + 2-digit branch)",
    ]
    if jo is None or str(jo).strip() == "":
        raise ToolValidationError("'jo' (article number) is required", hints=hints)

    text = str(jo).strip()

    if text.isdigit():
        if len(text) == 6:
            article, branch = int(text[:4]), int(text[4:])
        elif len(text) <= 4:
            article, branch = int(text), 0
        else:
            raise ToolValidationError(
                f"Ambiguous article code '{text}': use 1-4 digits for an article "
                "number or exactly 6 digits for the upstream JO code",
                hints=hints,
            )
    else:
        m = _JO_TEXT_RE.match(text)
        if not m:
            raise ToolValidationError(
                f"Invalid article reference '{text}'", hints=hints
            )
        article = int(m.group(1))
        branch = int(m.group(2)) if m.group(2) else 0

    try:
        return format_article_number(article, branch)
    except ValueError as e:
        raise ToolValidationError(str(e), hints=hints)


def validate_trm_rlt_cd(value: Union[str, int, None]) -> Optional[str]:
    """Validate/normalize 용어관계코드. Accepts the 6-digit code or its Korean name.

    Returns None when value is empty so callers can simply skip the param.
    """
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if text in TRM_RLT_CODES:
        return text
    if text in _TRM_RLT_BY_NAME:
        return _TRM_RLT_BY_NAME[text]
    options = ", ".join(f"{c} ({n})" for c, n in TRM_RLT_CODES.items())
    raise ToolValidationError(
        f"Invalid trm_rlt_cd '{text}'",
        hints=[f"Valid values: {options}", "Omit trm_rlt_cd to get all relation types"],
    )


def require_query_or_mst(query: Optional[str], mst: Optional[str], tool_name: str) -> None:
    """lawService.do term-linkage targets need either query (term text) or MST."""
    if (query is None or str(query).strip() in ("", "*")) and not mst:
        raise ToolValidationError(
            f"{tool_name}: provide 'query' (term text) or 'mst' (term 일련번호)",
            hints=[
                "query: the exact term, e.g. query='공정한이용'",
                "mst: a term MST from a previous linkage result, e.g. mst='1470403'",
            ],
        )


# ordinLsCon_search mode → upstream target on lawSearch.do
ORDIN_LINK_MODES = {
    "query": "lnkOrd",     # search linked ordinances by ordinance name
    "law_id": "lnkLsOrd",  # ordinances linked to a statute (knd=법령ID)
    "org": "lnkOrg",       # ordinances of a local government (org code)
}


def select_ordin_link_mode(
    query: Optional[str],
    law_id: Union[str, int, None],
    org: Union[str, int, None],
) -> tuple[str, dict[str, str], str]:
    """Pick the upstream target for ordinLsCon_search.

    Exactly one of query / law_id / org must be given.

    Returns:
        (target, extra_params, ranking_query)
        ranking_query is the text used for relevance ranking ("*" disables it).
    """
    provided = {}
    if query is not None and str(query).strip() != "":
        provided["query"] = str(query).strip()
    if law_id is not None and str(law_id).strip() != "":
        provided["law_id"] = str(law_id).strip()
    if org is not None and str(org).strip() != "":
        provided["org"] = str(org).strip()

    hints = [
        "query='주차장'  → ordinances whose name matches (target lnkOrd)",
        "law_id='001823' → ordinances linked to that statute 법령ID (target lnkLsOrd)",
        "org='3270000'   → ordinances of that local-government code (target lnkOrg)",
    ]
    if len(provided) == 0:
        raise ToolValidationError(
            "ordinLsCon_search requires exactly one of 'query', 'law_id', or 'org'",
            hints=hints,
        )
    if len(provided) > 1:
        raise ToolValidationError(
            "ordinLsCon_search accepts only one mode at a time; got "
            + ", ".join(sorted(provided)),
            hints=hints,
        )

    (mode, value), = provided.items()
    target = ORDIN_LINK_MODES[mode]
    if mode == "query":
        return target, {"query": value}, value
    if mode == "law_id":
        return target, {"knd": value}, "*"
    return target, {"org": value}, "*"


def attach_parsed_data(response: dict, response_type: str) -> dict:
    """Add 'parsed_data' (dict) to a lawService.do response when the body parses.

    JSON: unwraps the single root key (e.g. lstrmRltService).
    XML: parse_xml_response().
    Leaves the response untouched on errors / HTML / empty bodies.
    """
    if response.get("status") != "ok":
        return response
    raw = response.get("raw_content")
    if not raw or not isinstance(raw, str):
        return response

    parsed: Any = None
    if response_type == "JSON":
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and len(data) == 1:
                parsed = next(iter(data.values()))
            else:
                parsed = data
        except ValueError:
            parsed = None
    elif response_type == "XML":
        try:
            parsed = parse_xml_response(raw)
        except Exception:
            parsed = None

    if parsed:
        response["parsed_data"] = parsed
    return response
