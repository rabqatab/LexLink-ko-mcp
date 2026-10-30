"""
Shared helpers for LexLink MCP tools.

Extracts common patterns from server.py to reduce duplication.
All helpers preserve exact existing behavior.
"""

import asyncio
import concurrent.futures
import functools
import inspect
import logging
import os
import re
import traceback
from typing import Optional, Union

from mcp.types import ToolAnnotations

from .client import redact_oc
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


def run_coroutine_sync(coro):
    """Run ``coro`` to completion from sync code and return its result.

    Uses ``asyncio.run`` inside a dedicated worker thread, so it works both
    with and without an already running event loop (FastMCP runs sync tools on
    its loop; ``run_until_complete`` there raises RuntimeError). Exceptions from
    the coroutine propagate to the caller.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _redacted_error_text(e: BaseException, kwargs: dict) -> str:
    """str(e) with the OC credential removed (argument or OC env var)."""
    return redact_oc(str(e), kwargs.get("oc") or os.getenv("OC"))


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
                msg = _redacted_error_text(e, kwargs)
                logger.warning(f"Validation error in {func.__name__}: {msg}")
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=msg,
                    hints=e.hints,
                )
            except ValueError as e:
                msg = _redacted_error_text(e, kwargs)
                logger.warning(f"Validation error in {func.__name__}: {msg}")
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=msg,
                )
            except Exception as e:
                msg = _redacted_error_text(e, kwargs)
                logger.error(
                    f"Unexpected error in {func.__name__}: {msg}\n"
                    + "".join(traceback.format_tb(e.__traceback__))
                )
                return create_error_response(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Unexpected error: {msg}",
                )
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ToolValidationError as e:
                msg = _redacted_error_text(e, kwargs)
                logger.warning(f"Validation error in {func.__name__}: {msg}")
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=msg,
                    hints=e.hints,
                )
            except ValueError as e:
                msg = _redacted_error_text(e, kwargs)
                logger.warning(f"Validation error in {func.__name__}: {msg}")
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=msg,
                )
            except Exception as e:
                msg = _redacted_error_text(e, kwargs)
                logger.error(
                    f"Unexpected error in {func.__name__}: {msg}\n"
                    + "".join(traceback.format_tb(e.__traceback__))
                )
                return create_error_response(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Unexpected error: {msg}",
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
from .cache import get_cache
from .resolver import get_resolver
from .ranking import rank_search_results, should_apply_ranking


ID_NOTE = (
    "raw_content의 id는 행 번호입니다. service 호출에는 판례일련번호·법령ID·"
    "법령일련번호(MST) 등 실제 키를 쓰세요."
)


def rename_row_ids_to_rank(response: dict) -> dict:
    """Rename each ranked_data row's ``id`` (upstream row index 1,2,3) to ``rank``.

    Upstream search rows carry ``id`` = row number, not a key usable in service
    calls. Only ``ranked_data`` is touched (raw_content stays as returned);
    rows without ``id`` are left alone. Handles list and single-dict rows.
    Adds ``id_note`` only when raw_content is kept and some row had an ``id``.
    Call after ranking, hooks and any raw_content rewrite.
    """
    ranked = response.get("ranked_data") if isinstance(response, dict) else None
    if not isinstance(ranked, dict):
        return response
    renamed = False
    for value in ranked.values():
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            if isinstance(row, dict) and "id" in row:
                # rebuild so "rank" keeps the position of "id"
                items = [("rank" if k == "id" else k, v) for k, v in row.items()]
                row.clear()
                row.update(items)
                renamed = True
    if renamed and response.get("raw_content"):
        response["id_note"] = ID_NOTE
    return response


def detect_items_key(parsed_data: dict) -> Optional[str]:
    """Find the single list-of-dicts key in a parsed search response.

    Upstream list keys don't always match the target name (e.g. target
    "ttSpecialDecc" → root "Decc", list "decc"; "moelCgmExpc" → "cgmExpc").
    Returns the key when exactly one candidate exists, else None.
    """
    if not isinstance(parsed_data, dict):
        return None
    candidates = [
        k for k, v in parsed_data.items()
        if (isinstance(v, list) and v and all(isinstance(i, dict) for i in v))
        or (isinstance(v, dict) and v and k.lower() not in ("basicinfo", "기본정보"))
    ]
    # Prefer real lists over single-item dicts
    lists = [k for k in candidates if isinstance(parsed_data[k], list)]
    if len(lists) == 1:
        return lists[0]
    if not lists and len(candidates) == 1:
        return candidates[0]
    return None


OVER_FETCH_WINDOW = 100  # upstream max rows per request


def plan_ranking_pages(
    upstream_params: dict,
    *,
    ranking_enabled: bool,
    over_fetch: bool,
    display: int,
    over_fetch_key: str,
    response_type: str,
) -> tuple[bool, int, bool]:
    """Decide how to page a ranked (over-fetched) search.

    Mutates ``upstream_params`` for the over-fetch case. Returns
    ``(ranking_enabled, offset, ranking_skipped)``:

    - page*display <= 100: force upstream page 1 with 100 rows, rank them all and
      let the caller slice ``[offset : offset + display]`` (offset = (page-1)*display).
    - page*display > 100: the window cannot reach this page; skip ranking and
      forward page/display unchanged (``ranking_skipped`` True).
    """
    if not (ranking_enabled and over_fetch and display < OVER_FETCH_WINDOW):
        return ranking_enabled, 0, False
    try:
        page = max(int(upstream_params.get("page") or 1), 1)
    except (TypeError, ValueError):
        page = 1
    if page * display > OVER_FETCH_WINDOW:
        return False, 0, True
    upstream_params["page"] = "1"
    upstream_params[over_fetch_key] = str(OVER_FETCH_WINDOW)
    # JSON format ignores numOfRows — must also set display for JSON over-fetch
    if response_type == "JSON":
        upstream_params["display"] = str(OVER_FETCH_WINDOW)
    return True, (page - 1) * display, False


NO_RESULTS_MESSAGE = "검색 결과가 없습니다."
NO_RESULTS_HINTS = [
    "검색어를 줄이거나 핵심 단어만 사용해 보세요",
    "약칭 대신 정식 명칭으로 검색해 보세요",
]
NO_RESULTS_BODY_HINT = "search=2(본문 검색)로 다시 시도해 보세요"


def _total_count(response: dict) -> Optional[int]:
    """totalCnt from ranked_data or raw_content, None when not found."""
    ranked = response.get("ranked_data")
    if isinstance(ranked, dict) and ranked.get("totalCnt") not in (None, ""):
        try:
            return int(str(ranked["totalCnt"]).strip())
        except ValueError:
            pass
    raw = response.get("raw_content")
    if isinstance(raw, str):
        m = re.search(r'totalCnt["\']?\s*[:>=]\s*["\']?\s*(\d+)', raw)
        if m:
            return int(m.group(1))
    return None


def add_no_results_guidance(response: dict, *, body_search: bool = False) -> dict:
    """Add warning/message/hints to an ok search response whose total is 0."""
    if not isinstance(response, dict) or response.get("status") != "ok":
        return response
    if _total_count(response) != 0:
        return response
    response["warning"] = "no_results"
    response["message"] = NO_RESULTS_MESSAGE
    response["hints"] = list(NO_RESULTS_HINTS) + ([NO_RESULTS_BODY_HINT] if body_search else [])
    return response


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
    finalize_ids: bool = True,
) -> dict:
    """Common search tool logic.
    Handles: law name resolution, caching, param mapping, API call, XML/JSON parsing,
    relevance ranking (3 pipelines), alias learning, trimming, slim_response.
    """
    # Resolve law name aliases (e.g., "자통법" → "자본시장과 금융투자업에 관한 법률")
    resolver = get_resolver()
    resolved_query = resolver.resolve(query)
    if resolved_query != query:
        snake_params["query"] = resolved_query
        logger.info(f"Resolved query: '{query}' → '{resolved_query}'")

    upstream_params = map_params_to_upstream(snake_params)

    original_display = display
    ranking_enabled = (
        response_type in ("XML", "JSON")
        and ranking_field is not None
        and list_type is not None
        and should_apply_ranking(resolved_query)
    )

    ranking_enabled, page_offset, ranking_skipped = plan_ranking_pages(
        upstream_params, ranking_enabled=ranking_enabled, over_fetch=over_fetch,
        display=original_display, over_fetch_key=over_fetch_key,
        response_type=response_type,
    )
    if ranking_skipped:
        logger.debug("page*display > 100: ranking skipped, forwarding page/display unchanged")

    # Check cache before making API call
    cache = get_cache()
    cached = cache.get(target, upstream_params)
    if cached is not None:
        response = cached
    else:
        client = get_client()
        response = client.get("/DRF/lawSearch.do", upstream_params, response_type)
        # Cache the raw response
        cache.put(target, upstream_params, response)

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
                        if not items:
                            # Fallback: item_category didn't match the response's
                            # list key (e.g. target "ttSpecialDecc" vs list key "decc").
                            # If the response has exactly one list-of-dicts, use it.
                            detected = detect_items_key(parsed_data)
                            if detected:
                                item_category = detected
                                items = extract_items_list(parsed_data, item_category)
                    else:
                        items = parsed_data.get(list_type, [])
                        if not isinstance(items, list):
                            items = [items] if items else []

                    if items:
                        ranked_items = rank_search_results(items, query, ranking_field)

                        if len(ranked_items) > original_display or page_offset:
                            ranked_items = ranked_items[page_offset:page_offset + original_display]
                            logger.debug(f"Trimmed results from {len(items)} to {len(ranked_items)}")

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

                        # Learn aliases from law search results
                        if list_type == "law" and ranked_items:
                            resolver.learn_from_results(ranked_items)

                        if post_rank_hook:
                            post_rank_hook(ranked_items)
                else:
                    response["ranked_data"] = parsed_data

    if ranking_skipped:
        response["ranking_applied"] = False
    add_no_results_guidance(
        response,
        body_search=str(snake_params.get("search", "")) in ("1", "2") and target != "aiSearch",
    )
    if finalize_ids:
        rename_row_ids_to_rank(response)
    return slim_response(response)


def _fields_empty(raw: str, response_type: str, fields: list[str]) -> bool:
    """True when every field in ``fields`` is missing or blank in the body."""
    if response_type == "JSON":
        try:
            import json as _json
            data = _json.loads(raw)
            root = list(data.values())[0] if isinstance(data, dict) and data else {}
            if not isinstance(root, dict):
                return False
        except Exception:
            return False
        return all(not str(root.get(f) or "").strip() for f in fields)
    if response_type == "XML":
        for f in fields:
            fe = re.escape(f)
            for m in re.finditer(rf'<{fe}>(.*?)</{fe}>', raw, flags=re.DOTALL):
                inner = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', m.group(1), flags=re.DOTALL)
                if inner.strip():
                    return False
        return True
    return False


# Precedent 데이터출처명 values whose body the law.go.kr API does not provide
PREC_NO_BODY_SOURCES = {"국세법령정보시스템"}


def annotate_prec_body_availability(response: dict) -> dict:
    """Mark prec search items whose body is not served by the API."""
    ranked = response.get("ranked_data") if isinstance(response, dict) else None
    items = ranked.get("prec") if isinstance(ranked, dict) else None
    if isinstance(items, dict):
        items = [items]
    for item in items or []:
        if isinstance(item, dict) and item.get("데이터출처명") in PREC_NO_BODY_SOURCES:
            item["본문제공"] = "API 미제공"
    return response


def run_service(
    *,
    get_client,
    target: str,
    snake_params: dict,
    response_type: str = "XML",
    sections: Optional[str] = None,
    full_text_fields: Optional[list[str]] = None,
    summary_required_fields: Optional[list[str]] = None,
) -> dict:
    """Common service tool logic. Handles: param mapping, API call, section filtering.

    Args:
        sections: "summary" to exclude full-text fields (reduces response size for
                  PlayMCP 20KB limit), "full" or None for complete response.
        full_text_fields: List of field names to strip when sections="summary".
                         These are the verbose prose fields (판례내용, 전문, 이유, etc.)
        summary_required_fields: Fields that make a summary useful (e.g. 판시사항,
                         판결요지). If all are empty, full_text_fields are kept and
                         sections="summary_fallback" is reported.
    """
    upstream_params = map_params_to_upstream(snake_params)

    # Check cache (only for full responses — summary mode always fetches fresh then strips)
    cache = get_cache()
    if sections != "summary":
        cached = cache.get(target, upstream_params)
        if cached is not None:
            return cached

    client = get_client()
    response = client.get("/DRF/lawService.do", upstream_params, response_type)

    # Cache the full response before section filtering
    cache.put(target, upstream_params, response)

    # Section filtering must not mutate the cached full response
    response = dict(response)

    # Section filtering: strip full-text fields when sections="summary"
    if sections == "summary" and full_text_fields and response.get("status") == "ok":
        raw = response.get("raw_content", "")
        if (
            raw and summary_required_fields
            and _fields_empty(raw, response_type, summary_required_fields)
        ):
            response["sections"] = "summary_fallback"
            response["warning"] = (
                "판시사항·판결요지가 비어 있어 판례내용을 포함함 "
                "(sections=summary 요청이지만 본문 전체를 반환합니다)."
            )
        elif raw and response_type == "XML":
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

OUTCOME_NOTE = "휴리스틱 추정이며 인용 가능한 판결 결과가 아닙니다. 판결요지에는 주문이 없는 경우가 많아 '불명'이 흔합니다."

_DISPOSITION_VERB = r"(?:한다|하였|했|하고|합니다|함)"
_APPLICANT = r"(?:청구|상고|항소|신청|재심|심판청구|이의|재항고|항고)"
# Specific keywords first; plain 기각/각하/인용/취소 need disposition context.
_OUTCOME_PATTERNS = [
    ("파기환송", re.compile(r"파기\s*환송")),
    ("파기자판", re.compile(r"파기\s*자판")),
    ("일부인용", re.compile(r"일부\s*인용")),
    ("일부기각", re.compile(r"일부\s*기각")),
    ("파기", re.compile(r"파기(?!\s*(?:환송|자판))")),
    # (?<!기): "기각하였다" contains "각하"
    ("각하", re.compile(rf"{_APPLICANT}[^.\n]{{0,30}}(?<!기)각하|(?<!기)각하\s*{_DISPOSITION_VERB}|(?<!기)각하\s*(?:판결|결정)")),
    ("기각", re.compile(rf"{_APPLICANT}[^.\n]{{0,30}}기각|기각\s*{_DISPOSITION_VERB}|기각\s*(?:판결|결정)")),
    ("인용", re.compile(rf"{_APPLICANT}[^.\n]{{0,30}}(?<!일부)인용(?!\s*(?:하지|되지|된|하여|함으로))|(?<!일부)인용\s*{_DISPOSITION_VERB}(?!지)|인용\s*(?:판결|결정)")),
    ("취소", re.compile(rf"{_APPLICANT}[^.\n]{{0,30}}취소|취소\s*{_DISPOSITION_VERB}|취소\s*(?:판결|결정)")),
]

# Legal term suffix patterns (Korean legal jargon indicators)
LEGAL_TERM_SUFFIXES = re.compile(
    r'[\uAC00-\uD7A3]{2,}(?:자|인|권|의무|행위|사항|절차|요건|책임|위반|처분|규정|조항|법률|계약|소송|재판|판결|채권|채무|손해|배상|이행|해제|해지|취소|무효|유효)'
)


def extract_outcome(text: str) -> str:
    """Extract court decision outcome from 판결요지 text using keyword matching.

    Heuristic, not a citable result: specific keywords are checked first and
    plain 기각/각하/인용/취소 require disposition context (e.g. "청구를 기각한다").
    "원심판결 인용", "인용하지", "인용된", "을 인용하여" are not outcomes.
    Returns "불명" when unclear (common, since 판결요지 often has no 주문).
    """
    if not text:
        return "불명"
    for keyword, pattern in _OUTCOME_PATTERNS:
        if pattern.search(text):
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
