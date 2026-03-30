"""
Shared helpers for LexLink MCP tools.

Extracts common patterns from server.py to reduce duplication.
All helpers preserve exact existing behavior.
"""

import functools
import inspect
import logging
import os
import re
from typing import Optional, Union

from mcp.types import ToolAnnotations

from .errors import ErrorCode, create_error_response

logger = logging.getLogger(__name__)


# Shared tool annotations — all LexLink tools are read-only, non-destructive, idempotent
TOOL_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
)


def stringify_id(*values: Optional[Union[str, int]]) -> tuple:
    """Convert id/mst/jo values to strings if they are integers.
    LLMs may extract numbers as ints from XML, but API params expect strings.
    """
    return tuple(str(v) if v is not None else None for v in values)


class ToolValidationError(ValueError):
    """ValueError subclass that carries hints for the error response."""
    def __init__(self, message: str, hints: Optional[list[str]] = None):
        super().__init__(message)
        self.hints = hints


def handle_tool_error(func):
    """Decorator wrapping tool functions with standardized error handling.
    Catches ToolValidationError (with hints), ValueError (without hints),
    and Exception (unexpected errors). Works with both sync and async functions.
    """
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ToolValidationError as e:
                logger.warning(f"Validation error in {func.__name__}: {e}")
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=str(e),
                    hints=e.hints,
                )
            except ValueError as e:
                logger.warning(f"Validation error in {func.__name__}: {e}")
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=str(e),
                )
            except Exception as e:
                logger.exception(f"Unexpected error in {func.__name__}: {e}")
                return create_error_response(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Unexpected error: {str(e)}",
                )
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ToolValidationError as e:
                logger.warning(f"Validation error in {func.__name__}: {e}")
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=str(e),
                    hints=e.hints,
                )
            except ValueError as e:
                logger.warning(f"Validation error in {func.__name__}: {e}")
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=str(e),
                )
            except Exception as e:
                logger.exception(f"Unexpected error in {func.__name__}: {e}")
                return create_error_response(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Unexpected error: {str(e)}",
                )
        return sync_wrapper


def slim_response(response: dict) -> dict:
    """Remove redundant raw XML when parsed data exists.
    When SLIM_RESPONSE=true, removes 'raw_content' only if 'ranked_data' exists.
    """
    if not os.getenv("SLIM_RESPONSE"):
        return response
    result = response.copy()
    if "ranked_data" in result:
        result.pop("raw_content", None)
    return result


from .params import map_params_to_upstream
from .parser import parse_xml_response, extract_law_list, update_law_list, extract_items_list, update_items_list
from .ranking import rank_search_results, should_apply_ranking


def run_search(
    *,
    get_client,
    target: str,
    query: str,
    snake_params: dict,
    response_type: str = "XML",
    display: int = 20,
    ranking_field: Optional[str] = None,
    list_type: Optional[str] = None,
    item_category: Optional[str] = None,
    over_fetch_key: str = "numOfRows",
    over_fetch: bool = True,
    post_rank_hook=None,
) -> dict:
    """Common search tool logic.
    Handles: param mapping, API call, XML parsing, relevance ranking (3 pipelines),
    trimming, slim_response.

    Ranking pipelines based on list_type:
    - "law": extract_law_list/update_law_list, over_fetch via numOfRows
    - "items": extract_items_list/update_items_list, over_fetch via display
    - other string (e.g. "admrul"): inline key access on parsed_data
    - None: parse-only mode (no ranking)
    """
    upstream_params = map_params_to_upstream(snake_params)

    original_display = display
    ranking_enabled = (
        response_type in ("XML", "JSON")
        and ranking_field is not None
        and list_type is not None
        and should_apply_ranking(query)
    )

    if ranking_enabled and over_fetch and original_display < 100:
        upstream_params[over_fetch_key] = "100"
        # JSON format ignores numOfRows — must also set display for JSON over-fetch
        if response_type == "JSON":
            upstream_params["display"] = "100"
        logger.debug(f"Ranking enabled: fetching 100 results instead of {original_display}")

    client = get_client()
    response = client.get("/DRF/lawSearch.do", upstream_params, response_type)

    if response.get("status") == "ok" and response_type in ("XML", "JSON"):
        raw_content = response.get("raw_content", "")
        if raw_content:
            # Parse response based on format
            if response_type == "JSON":
                import json as _json
                try:
                    json_data = _json.loads(raw_content)
                    # JSON responses have a root key (e.g., "LawSearch", "PrecSearch")
                    # Extract the inner object as parsed_data
                    parsed_data = list(json_data.values())[0] if json_data else None
                except (ValueError, IndexError):
                    parsed_data = None
            else:
                parsed_data = parse_xml_response(raw_content)
            if parsed_data:
                if ranking_enabled:
                    if list_type == "law":
                        items = extract_law_list(parsed_data)
                    elif list_type == "items":
                        items = extract_items_list(parsed_data, item_category)
                    else:
                        items = parsed_data.get(list_type, [])
                        if not isinstance(items, list):
                            items = [items] if items else []

                    if items:
                        ranked_items = rank_search_results(items, query, ranking_field)

                        if len(ranked_items) > original_display:
                            ranked_items = ranked_items[:original_display]
                            logger.debug(f"Trimmed results from {len(items)} to {original_display}")

                        if list_type == "law":
                            parsed_data = update_law_list(parsed_data, ranked_items)
                            parsed_data["numOfRows"] = str(original_display)
                        elif list_type == "items":
                            parsed_data = update_items_list(parsed_data, ranked_items, item_category)
                            parsed_data["display"] = str(original_display)
                        else:
                            parsed_data[list_type] = ranked_items
                            parsed_data["numOfRows"] = str(original_display)

                        response["ranked_data"] = parsed_data

                        if post_rank_hook:
                            post_rank_hook(ranked_items)
                else:
                    response["ranked_data"] = parsed_data

    return slim_response(response)


def run_service(
    *,
    get_client,
    target: str,
    snake_params: dict,
    response_type: str = "XML",
    sections: Optional[str] = None,
    full_text_fields: Optional[list[str]] = None,
) -> dict:
    """Common service tool logic. Handles: param mapping, API call, section filtering.

    Args:
        sections: "summary" to exclude full-text fields (reduces response size for
                  PlayMCP 20KB limit), "full" or None for complete response.
        full_text_fields: List of field names to strip when sections="summary".
                         These are the verbose prose fields (판례내용, 전문, 이유, etc.)
    """
    upstream_params = map_params_to_upstream(snake_params)
    client = get_client()
    response = client.get("/DRF/lawService.do", upstream_params, response_type)

    # Section filtering: strip full-text fields when sections="summary"
    if sections == "summary" and full_text_fields and response.get("status") == "ok":
        raw = response.get("raw_content", "")
        if raw and response_type == "XML":
            # Strip XML tags for full-text fields
            for field in full_text_fields:
                raw = re.sub(
                    rf'<{re.escape(field)}>.*?</{re.escape(field)}>',
                    f'<{field}>[sections=summary: excluded for size — use sections="full" to retrieve]</{field}>',
                    raw, flags=re.DOTALL,
                )
            response["raw_content"] = raw
            response["sections"] = "summary"
            response["excluded_fields"] = full_text_fields
        elif raw and response_type == "JSON":
            try:
                import json as _json
                data = _json.loads(raw)
                # Walk the JSON tree and null out full-text fields
                def _strip(obj):
                    if isinstance(obj, dict):
                        for field in full_text_fields:
                            if field in obj:
                                obj[field] = f'[sections=summary: excluded for size — use sections="full" to retrieve]'
                        for v in obj.values():
                            _strip(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            _strip(item)
                _strip(data)
                response["raw_content"] = _json.dumps(data, ensure_ascii=False)
                response["sections"] = "summary"
                response["excluded_fields"] = full_text_fields
            except:
                pass  # If JSON parsing fails, return unmodified

    return response


# ============================================================
# Public Legal Assistance Helpers
# ============================================================

# Outcome keywords for Korean court decisions
OUTCOME_KEYWORDS = {
    "인용": "accepted",
    "기각": "rejected",
    "파기환송": "overturned_remanded",
    "파기자판": "overturned_self_decided",
    "파기": "overturned",
    "각하": "dismissed",
    "취소": "cancelled",
    "일부인용": "partially_accepted",
    "일부기각": "partially_rejected",
}

# Legal term suffix patterns (Korean legal jargon indicators)
LEGAL_TERM_SUFFIXES = re.compile(
    r'[\uAC00-\uD7A3]{2,}(?:자|인|권|의무|행위|사항|절차|요건|책임|위반|처분|규정|조항|법률|계약|소송|재판|판결|채권|채무|손해|배상|이행|해제|해지|취소|무효|유효)'
)


def extract_outcome(text: str) -> str:
    """Extract court decision outcome from 판결요지 text using keyword matching."""
    if not text:
        return "불명"
    for keyword in OUTCOME_KEYWORDS:
        if keyword in text:
            return keyword
    return "불명"


def extract_key_factors(text: str) -> list[str]:
    """Extract key judgment factors from 판시사항 text."""
    if not text:
        return []
    factors = []
    sentences = re.split(r'[.。\n]', text)
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 10:
            continue
        if re.search(r'여부|인지\s|을\s고려|를\s고려|에\s비추어|이\s있는지|수\s있는지|해당하는지|성립하는지', sent):
            factor = sent.strip()[:100]
            if factor and factor not in factors:
                factors.append(factor)
    return factors[:10]


def extract_legal_terms(text: str) -> list[str]:
    """Extract candidate legal terms from Korean legal text for simplification."""
    if not text:
        return []
    matches = LEGAL_TERM_SUFFIXES.findall(text)
    seen = set()
    terms = []
    for m in matches:
        if m not in seen and len(m) >= 2:
            seen.add(m)
            terms.append(m)
    return terms[:20]


def compute_text_diff(old_text: str, new_text: str) -> tuple[list, str, str]:
    """Compute line-level diff between two text versions.
    Returns: (changes_list, unified_diff_string, summary_string)
    """
    import difflib

    old_lines = old_text.strip().splitlines()
    new_lines = new_text.strip().splitlines()

    changes = []
    added = deleted = modified = 0

    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        elif tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                ol = old_lines[i1 + k] if i1 + k < i2 else None
                nl = new_lines[j1 + k] if j1 + k < j2 else None
                if ol and nl:
                    changes.append({"type": "modified", "old_line": ol, "new_line": nl})
                    modified += 1
                elif nl:
                    changes.append({"type": "added", "old_line": None, "new_line": nl})
                    added += 1
                else:
                    changes.append({"type": "deleted", "old_line": ol, "new_line": None})
                    deleted += 1
        elif tag == "insert":
            for k in range(j1, j2):
                changes.append({"type": "added", "old_line": None, "new_line": new_lines[k]})
                added += 1
        elif tag == "delete":
            for k in range(i1, i2):
                changes.append({"type": "deleted", "old_line": old_lines[k], "new_line": None})
                deleted += 1

    unified = "\n".join(difflib.unified_diff(
        old_lines, new_lines, lineterm="", fromfile="old", tofile="new",
    ))

    summary = f"{modified} lines modified, {added} lines added, {deleted} lines deleted"
    return changes, unified, summary
