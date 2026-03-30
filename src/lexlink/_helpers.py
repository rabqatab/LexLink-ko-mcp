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
