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


def slim_enabled() -> bool:
    """True only when SLIM_RESPONSE is one of 1/true/yes/on (case-insensitive, whitespace-trimmed)."""
    return os.getenv("SLIM_RESPONSE", "").strip().lower() in {"1", "true", "yes", "on"}


def slim_response(response: dict) -> dict:
    """Remove redundant raw XML when parsed data exists.
    When SLIM_RESPONSE is enabled (see slim_enabled), removes 'raw_content' only if 'ranked_data' exists.
    """
    if not slim_enabled():
        return response
    result = response.copy()
    if "ranked_data" in result:
        result.pop("raw_content", None)
        result.pop("id_note", None)  # the note explains raw_content ids
    return result


def compact_limit(n: int) -> Optional[int]:
    """Size cap for compact deployments: n when SLIM_RESPONSE is enabled (see slim_enabled), else None (no cap). None works in slices."""
    return n if slim_enabled() else None


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


def validate_paging(page, display) -> tuple[int, int]:
    """Return ``(page, display)`` as ints; page < 1 or display < 1 is a validation error."""
    try:
        p = int(str(page).strip()) if page not in (None, "") else 1
        d = int(str(display).strip()) if display not in (None, "") else 20
    except (TypeError, ValueError):
        raise ToolValidationError(
            f"page/display는 정수여야 합니다 (page={page!r}, display={display!r})",
            hints=["page는 1 이상, display는 1~100 사이의 정수를 사용하세요"],
        )
    if p < 1 or d < 1:
        raise ToolValidationError(
            f"page와 display는 1 이상이어야 합니다 (page={p}, display={d}). "
            f"page and display must be >= 1.",
            hints=["page는 1부터 시작합니다", "display는 1~100 사이로 지정하세요 (100 초과는 100으로 제한)"],
        )
    return p, d


def run_ranked_paging(
    *,
    fetch,
    upstream_params: dict,
    page: int,
    display: int,
    over_fetch_key: str,
    response_type: str,
    load,
    rank,
):
    """Page a ranked (over-fetched) search with a stable row order.

    Row order: the relevance-ranked first 100 upstream rows (the window), then
    upstream rows 101+ in upstream order. For ``offset = (page-1)*display``:

    - inside the window: rank the window and slice (ranking_applied None);
    - beyond it: fetch the size-100 upstream page(s) covering the slice
      (ranking_applied False);
    - straddling it: ranked tail + head of upstream page 2 ("partial").

    ``fetch(params) -> response``; ``load(response) -> (parsed, items) | None``;
    ``rank(items) -> items``. Returns ``(response, parsed, rows, applied)`` where
    ``parsed`` is None when nothing could be parsed (response returned as is,
    including any error response from a failed fetch).
    """
    W = OVER_FETCH_WINDOW
    offset = (page - 1) * display

    def request(upstream_page: int) -> dict:
        q = dict(upstream_params)
        q["page"] = str(upstream_page)
        q[over_fetch_key] = str(W)
        # JSON format ignores numOfRows - must also set display
        if response_type == "JSON":
            q["display"] = str(W)
        return fetch(q)

    if offset + display <= W:
        resp = request(1)
        loaded = load(resp) if resp.get("status") == "ok" else None
        if not loaded or not loaded[1]:
            return resp, None, None, None
        parsed, items = loaded
        return resp, parsed, rank(items)[offset:offset + display], None

    if offset >= W:
        first = offset // W + 1
        last = (offset + display - 1) // W + 1
        base_resp = base_parsed = None
        combined: list = []
        for up in range(first, last + 1):
            resp = request(up)
            if resp.get("status") != "ok":
                return resp, None, None, None
            loaded = load(resp)
            if base_resp is None:
                base_resp = resp
            if not loaded:
                return base_resp, None, None, False
            if base_parsed is None:
                base_parsed = loaded[0]
            combined.extend(loaded[1])
        start = offset - (first - 1) * W
        return base_resp, base_parsed, combined[start:start + display], False

    # straddles the window boundary
    resp1 = request(1)
    loaded1 = load(resp1) if resp1.get("status") == "ok" else None
    if not loaded1 or not loaded1[1]:
        return resp1, None, None, None
    parsed1, items1 = loaded1
    ranked1 = rank(items1)
    if len(items1) < W:  # whole result set fits in the window
        return resp1, parsed1, ranked1[offset:offset + display], None
    tail = ranked1[offset:W]
    resp2 = request(2)
    if resp2.get("status") != "ok":
        return resp2, None, None, None
    loaded2 = load(resp2)
    head = loaded2[1][:offset + display - W] if loaded2 else []
    return resp1, parsed1, tail + head, "partial"


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


NO_MORE_RESULTS_HINT = "no_more_results: 요청한 page가 마지막 페이지를 넘었습니다. 더 낮은 page를 사용하세요"


def add_no_more_results_hint(response: dict, page: int, display: int) -> dict:
    """Hint ``no_more_results`` when the page starts past a non-empty result set."""
    if not isinstance(response, dict) or response.get("status") != "ok":
        return response
    total = _total_count(response)
    if total and (page - 1) * display >= total:
        hints = list(response.get("hints") or [])
        hints.append(NO_MORE_RESULTS_HINT)
        response["hints"] = hints
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

    page, display = validate_paging(snake_params.get("page", 1), display)
    upstream_params = map_params_to_upstream(snake_params)

    original_display = display
    ranking_enabled = (
        response_type in ("XML", "JSON")
        and ranking_field is not None
        and list_type is not None
        and should_apply_ranking(resolved_query)
    )
    use_paging = ranking_enabled and over_fetch and display < OVER_FETCH_WINDOW

    cache = get_cache()
    client_holder: list = []

    def fetch(params: dict) -> dict:
        cached = cache.get(target, params)
        if cached is not None:
            return cached
        if not client_holder:
            client_holder.append(get_client())
        resp = client_holder[0].get("/DRF/lawSearch.do", params, response_type)
        cache.put(target, params, resp)
        return dict(resp)

    def parse(resp: dict):
        raw_content = resp.get("raw_content", "")
        if not raw_content:
            return None
        if response_type == "JSON":
            import json as _json
            try:
                json_data = _json.loads(raw_content)
                # JSON responses have a root key (e.g., "LawSearch", "PrecSearch")
                return list(json_data.values())[0] if json_data else None
            except (ValueError, IndexError):
                return None
        return parse_xml_response(raw_content)

    state = {"category": item_category}

    def extract(parsed: dict) -> list:
        if list_type == "law":
            return extract_law_list(parsed)
        if list_type == "items":
            items = extract_items_list(parsed, state["category"])
            if not items:
                # Fallback: item_category didn't match the response's
                # list key (e.g. target "ttSpecialDecc" vs list key "decc").
                # If the response has exactly one list-of-dicts, use it.
                detected = detect_items_key(parsed)
                if detected:
                    state["category"] = detected
                    items = extract_items_list(parsed, detected)
            return items
        items = parsed.get(list_type, [])
        return items if isinstance(items, list) else ([items] if items else [])

    def store(parsed: dict, rows: list) -> dict:
        if list_type == "law":
            parsed = update_law_list(parsed, rows)
            parsed["numOfRows"] = str(original_display)
        elif list_type == "items":
            parsed = update_items_list(parsed, rows, state["category"])
            parsed["display"] = str(original_display)
        else:
            parsed[list_type] = rows
            parsed["numOfRows"] = str(original_display)
        parsed["page"] = str(page)
        return parsed

    def load(resp: dict):
        parsed = parse(resp)
        if not parsed:
            return None
        return parsed, extract(parsed)

    applied = None
    if use_paging:
        response, parsed_data, rows, applied = run_ranked_paging(
            fetch=fetch, upstream_params=upstream_params, page=page, display=display,
            over_fetch_key=over_fetch_key, response_type=response_type, load=load,
            rank=lambda items: rank_search_results(items, query, ranking_field),
        )
        if parsed_data is not None:
            response["ranked_data"] = store(parsed_data, rows)
            if list_type == "law" and rows:
                resolver.learn_from_results(rows)
            if post_rank_hook and rows:
                post_rank_hook(rows)
    else:
        response = fetch(upstream_params)
        if response.get("status") == "ok" and response_type in ("XML", "JSON"):
            parsed_data = parse(response)
            if parsed_data:
                if ranking_enabled:
                    items = extract(parsed_data)
                    if items:
                        # display >= 100 (or over_fetch off): rank within the page upstream returned
                        ranked_items = rank_search_results(items, query, ranking_field)
                        if len(ranked_items) > original_display:
                            ranked_items = ranked_items[:original_display]
                        response["ranked_data"] = store(parsed_data, ranked_items)
                        if list_type == "law" and ranked_items:
                            resolver.learn_from_results(ranked_items)
                        if post_rank_hook:
                            post_rank_hook(ranked_items)
                    else:
                        response["ranked_data"] = parsed_data  # empty page: still expose it
                else:
                    response["ranked_data"] = parsed_data

    if applied is not None:
        response["ranking_applied"] = applied
    add_no_more_results_hint(response, page, display)
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

OUTCOME_NOTE = (
    "결과는 각 판결의 '주문'만으로 분류한 휴리스틱이며 인용 가능한 판결 결과가 아닙니다. "
    "주문을 찾지 못하거나 해석이 애매하면 '불명'으로 둡니다. 승소율이 아닙니다: "
    "대법원의 '상고기각'은 원심 유지(상고인 패소)일 뿐 원고 승소를 뜻하지 않고, "
    "'파기환송'은 최종 결론이 아니라 원심으로 되돌려 보낸 것이며, "
    "'각하'는 본안 판단 없이 종결된 것입니다. 심급·당사자별로 해석해야 합니다."
)

# Legal term suffix patterns (Korean legal jargon indicators)
LEGAL_TERM_SUFFIXES = re.compile(
    r'[\uAC00-\uD7A3]{2,}(?:자|인|권|의무|행위|사항|절차|요건|책임|위반|처분|규정|조항|법률|계약|소송|재판|판결|채권|채무|손해|배상|이행|해제|해지|취소|무효|유효)'
)


# The 주문 ends at ANY following 【...】 heading (이유, 청구취지 및 항소취지, ...)
# or at a known [..] heading; the body is capped so a missing heading cannot
# swallow the judgment.
_ORDER_SECTION_RE = re.compile(
    r"[【\[]\s*주\s*문\s*[】\]](?P<body>.{0,4000}?)"
    r"(?=【[^】]{1,40}】|\[\s*(?:이\s*유|[가-힣 ]{0,15}취지|원심[가-힣 ]{0,6}|별\s*지[^\]]{0,20})\s*\]|$)",
    re.S,
)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_PAGI_RE = re.compile(r"파기\s*(?:한다|하고|하며|하여|함|환송|자판|[,，])")
_REMAND_RE = re.compile(
    r"파기.{0,300}?(?:환송|이송)\s*(?:한다|하고|함)"
    r"|(?:원심|제1심|원)\s*(?:판결|결정)[^.]{0,100}?취소.{0,300}?환송\s*(?:한다|하고|함)"
)
_PAGI_DISPOSED_RE = re.compile(r"파기\s*자판|파기.{0,300}?(?:기각|취소|지급하라|처한다|정한다|무죄|각하)")
_CHANGE_RE = re.compile(r"(?:원심|제1심|원|제\s*1\s*심)\s*(?:판결|결정|명령|심판)[^.]{0,100}?(?:변경|취소)")
_APPEAL_REJECT_RE = re.compile(r"(?:항소|(?<!재)(?<!특별)항고)[을를]?\s*(?:모두\s*)?기각\s*(?:한다|하고|함)")
_SUPREME_REJECT_RE = re.compile(r"(?:상고|재항고|특별항고)[을를]?\s*(?:모두\s*)?기각\s*(?:한다|하고|함)")
_PROSECUTION_REJECT_RE = re.compile(r"공소[을를]?\s*기각")
_CRIMINAL_RE = re.compile(r"배상명령|에 처한다|무죄|선고를 유예|집행을 유예|추징|몰수|피고인")
_ACQUIT_RE = re.compile(r"무죄[를을]?\s*선고|피고인은\s*무죄")
_CONVICT_RE = re.compile(r"(?:징역|금고|구류|벌금|과료)[^.]{0,200}?처한다")
_GRANT_RE = re.compile(r"(?:청구|신청)[을를]?\s*(?:모두\s*)?인용|지급하라|이행하라|인도하라|지급한다")
_PARTIAL_RE = re.compile(r"일부\s*(?:를|만을|만)?\s*(?:인용|기각)|나머지\s*[가-힣 ]{0,10}[을를]?\s*(?:모두\s*)?기각")
_REJECT_RE = re.compile(r"(?:청구|신청|심판청구|재심)[을를]?\s*(?:모두\s*)?기각\s*(?:한다|하고|함)")
_DISMISS_RE = re.compile(r"각하\s*(?:한다|하고|함)")
_REVOKE_RE = re.compile(r"(?:처분|판정|재결|심결)[을를]\s*취소\s*(?:한다|하고|함)")


def extract_order(text: str) -> str:
    """Return the 주문 (disposition) section of a judgment's 판례내용, or ''."""
    if not text:
        return ""
    m = _ORDER_SECTION_RE.search(text)
    if not m:
        return ""
    body = _BR_RE.sub(" ", m.group("body"))
    return re.sub(r"\s+", " ", body).strip()


def classify_order(order: str) -> str:
    """Classify a 주문 string into an outcome label; '불명' when unclear.

    Only the 주문 is read (never recitals/이유), and conflicting or unfamiliar
    orders give '불명' rather than a guess. Precedence: any 파기 (-> 파기환송 /
    파기자판 / 파기) or 취소·환송 outranks 기각; a 원심/제1심 판결 변경·취소 is
    원판결변경 (a trailing "나머지 ... 기각" is only a modifier); then 항소기각,
    상고기각; criminal orders only 무죄/유죄/공소기각; civil orders 일부인용,
    인용, 기각, 각하, 취소 (처분). Not a win rate: 상고기각 means the lower
    ruling stands.
    """
    if not order:
        return "불명"
    if _REMAND_RE.search(order):
        return "파기환송"
    if _PAGI_RE.search(order):
        return "파기자판" if _PAGI_DISPOSED_RE.search(order) else "파기"
    if _CHANGE_RE.search(order):
        return "원판결변경"
    criminal = bool(_CRIMINAL_RE.search(order))
    grant = bool(_GRANT_RE.search(order))
    reject = bool(_REJECT_RE.search(order))
    dismiss = bool(_DISMISS_RE.search(order))
    for pattern, label in ((_APPEAL_REJECT_RE, "항소기각"), (_SUPREME_REJECT_RE, "상고기각")):
        if pattern.search(order):
            # civil: 항소기각 plus a grant/dismissal is a compound order -> don't guess
            return "불명" if (grant or dismiss) and not criminal else label
    if criminal or _PROSECUTION_REJECT_RE.search(order):
        found = [label for label, pattern in (("무죄", _ACQUIT_RE), ("유죄", _CONVICT_RE),
                                              ("공소기각", _PROSECUTION_REJECT_RE)) if pattern.search(order)]
        return found[0] if len(found) == 1 else "불명"
    if _PARTIAL_RE.search(order) and (grant or reject):
        return "일부인용" if grant or "인용" in order else "불명"
    if grant + reject + dismiss > 1:
        return "불명"
    if grant:
        return "인용"
    if reject:
        return "기각"
    if dismiss:
        return "각하"
    if _REVOKE_RE.search(order):
        return "취소"
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
            factor = sent.strip()[:compact_limit(100)]
            if factor and factor not in factors:
                factors.append(factor)
    return factors[:compact_limit(10)]


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
