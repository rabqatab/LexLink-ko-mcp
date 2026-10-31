"""
Shared helpers for LexLink MCP tools.

Extracts common patterns from server.py to reduce duplication.
All helpers preserve exact existing behavior.
"""

import asyncio
import concurrent.futures
import copy
import functools
import inspect
import json
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


SLIM_MAX_BYTES = 20_000  # PlayMCP budget: bytes of the tool text as JSON-RPC re-escaped on the wire
SLIM_MIN_STRING = 200    # strings are cut to at least this many characters first
SLIM_FALLBACK_STRING = 40  # last-resort minimum once nothing else can shrink
SLIM_KEEP_KEYS = frozenset({"status", "id", "mst", "error_code", "request_id", "upstream_type"})
SLIM_NOTE = "SLIM_RESPONSE 크기 한도(20KB)로 일부가 생략되었습니다. "
SLIM_NO_PARAMS_HINT = "이 도구로는 나머지를 받을 수 없음; SLIM_RESPONSE 해제 환경 사용"


def slim_hint(params) -> str:
    """Note text telling the caller how to get the rest, using only parameters the tool has."""
    options = []
    if "jo" in params:
        options.append("jo로 조문 지정")
    if "sections" in params:
        options.append('sections="summary"')
    if "page" in params or "display" in params:
        options.append("page/display로 나누어 조회")
    if not options:
        return SLIM_NOTE + SLIM_NO_PARAMS_HINT
    return SLIM_NOTE + "나머지는 " + ", ".join(options) + "(으)로 받으세요."


def _json_size(value) -> int:
    """Bytes of the tool text for ``value`` as it goes over the wire: the pretty JSON
    re-escaped as a JSON-RPC string (quotes, newlines and backslashes grow)."""
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return len(json.dumps(text, ensure_ascii=False).encode("utf-8"))


def _item_size(value, depth: int) -> int:
    """Wire bytes ``value`` takes inside the pretty JSON at nesting ``depth`` (indent included)."""
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return len(json.dumps(text, ensure_ascii=False).encode("utf-8")) + 2 * depth * (text.count("\n") + 1) + 2


def _note_cut(log: list, where: str, before: int, after: int, unit: str) -> None:
    """Record a cut in ``log``; repeated cuts of the same field merge into one entry."""
    for entry in log:
        if entry[0] == where:
            entry[2] = after
            return
    log.append([where, before, after, unit])


def _cut_text(text: str, keep: int) -> str:
    """First ``keep`` characters; markup is cut after its last complete closing tag."""
    if text.lstrip()[:1] == "<":
        idx = text.rfind("</", 0, keep)
        end = text.find(">", idx) if idx > 0 else -1
        if 0 < end < keep:
            return text[:end + 1]
    return text[:keep]


def _shrink_once(node, excess: int, path: str, log: list, floor: int = 0, depth: int = 0,
                 min_str: int = SLIM_MIN_STRING, drop_keys: bool = False) -> bool:
    """Shrink the largest shrinkable part of ``node`` by about ``excess`` bytes.

    Cuts whole trailing list items or the tail of a long string, so the result
    stays valid JSON. A part is cut down toward the size of its next-largest
    sibling (``floor``) first, so one big list does not shrink to a single item
    while others stay whole. With ``drop_keys`` (last resort) unprotected entries
    are removed. Records what changed in ``log``; False when nothing can shrink.
    """
    children = [(k, v, _json_size(v)) for k, v in
                (node.items() if isinstance(node, dict) else enumerate(node))]
    children.sort(key=lambda kv: kv[2], reverse=True)
    for rank, (key, child, size) in enumerate(children):
        where = f"{path}.{key}" if path else str(key)
        sibling = children[1][2] if rank == 0 and len(children) > 1 else children[0][2]
        level_floor = max(floor, sibling if rank == 0 else 0)
        want = min(excess, max(size - level_floor, excess // 4, 1))  # bytes to free here
        if isinstance(child, str) and len(child) > min_str:
            keep = max(min_str, len(child) - max(want // 3, 1) - 1)
            node[key] = _cut_text(child, keep)
            _note_cut(log, where, len(child), len(node[key]), "자")
            return True
        if isinstance(child, list) and len(child) > 1:
            total = len(child)
            drop = 1
            freed = _item_size(child[-1], depth + 1)
            while total - drop > 1 and freed < want:
                drop += 1
                freed += _item_size(child[-drop], depth + 1)
            del child[total - drop:]
            _note_cut(log, where, total, total - drop, "건")
            return True
        if isinstance(child, (dict, list)) and child and _shrink_once(
                child, excess, where, log, level_floor, depth + 1, min_str, drop_keys):
            return True
        if drop_keys and not (isinstance(node, dict) and key in SLIM_KEEP_KEYS):
            del node[key]
            _note_cut(log, where, 1, 0, "건")
            return True
    return False


def enforce_slim_limit(result, limit: int = SLIM_MAX_BYTES, note: str = SLIM_NOTE + SLIM_NO_PARAMS_HINT):
    """Keep a tool result within ``limit`` wire bytes when SLIM_RESPONSE is enabled.

    No-op by default and for non-dict or already small results. Otherwise
    shrinks a copy (drops trailing list items, cuts long strings, as a last
    resort drops unprotected keys; always valid JSON) and adds ``truncated: true``,
    ``truncated_fields`` and a ``truncated_note`` saying how to fetch the rest.
    ``raw_content`` stays a string: JSON text is shrunk as data and dumped back,
    markup is cut after a closing tag with ``raw_content_partial: true``.
    """
    if not slim_enabled() or not isinstance(result, dict) or _json_size(result) <= limit:
        return result
    work = copy.deepcopy(result)
    as_data = False  # work["raw_content"] holds parsed JSON while it is shrunk
    if work.get("ranked_data"):
        work.pop("raw_content", None)  # parsed copy exists
    elif isinstance(work.get("raw_content"), str) and work["raw_content"].lstrip()[:1] in ("{", "["):
        try:
            work["raw_content"] = json.loads(work["raw_content"])
            as_data = True
        except ValueError:
            pass

    def materialize() -> dict:
        """``work`` as it will be returned (raw_content back to a JSON string)."""
        if not as_data:
            return work
        final = dict(work)
        final["raw_content"] = json.dumps(work["raw_content"], ensure_ascii=False)
        return final

    log: list = []
    reserve = 900  # room for the truncated_* fields added below
    for min_str, drop_keys in ((SLIM_MIN_STRING, False), (SLIM_FALLBACK_STRING, False), (SLIM_FALLBACK_STRING, True)):
        while True:
            final = materialize()
            excess = _json_size(final) - (limit - reserve)
            if excess <= 0:
                break
            if as_data:  # data inside raw_content counts for more once it is escaped text
                excess = max(1, excess * _json_size(work) // max(_json_size(final), 1))
            if not _shrink_once(work, excess, "", log, min_str=min_str, drop_keys=drop_keys):
                break
        if _json_size(materialize()) <= limit - reserve:
            break
    out = materialize()
    if isinstance(out.get("raw_content"), str) and not as_data and any(e[0] == "raw_content" for e in log):
        out["raw_content_partial"] = True
    out["truncated"] = True
    out["truncated_fields"] = [f"{w}: {b}{u} 중 {a}{u}만 표시" for w, b, a, u in log[-8:]]
    out["truncated_note"] = note
    if _json_size(out) > limit:  # still too big (protected keys): keep only the identifiers
        out = {k: v for k, v in out.items() if k in SLIM_KEEP_KEYS and not isinstance(v, (dict, list))}
        out["truncated"] = True
        out["truncated_note"] = note
    return out


def mark_slim_cut(result: dict, note: str) -> dict:
    """Flag a result that SLIM_RESPONSE shortened: ``truncated: true`` plus how to get the rest."""
    result["truncated"] = True
    notes = result.setdefault("truncated_notes", [])
    if note not in notes:
        notes.append(note)
    return result


def slim_limited(func):
    """Decorator: run ``enforce_slim_limit`` on the tool's dict result (sync or async).

    The note names only parameters the tool really has (see ``slim_hint``).
    """
    note = slim_hint(inspect.signature(func).parameters)

    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return enforce_slim_limit(await func(*args, **kwargs), note=note)
        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        return enforce_slim_limit(func(*args, **kwargs), note=note)
    return sync_wrapper


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

OUTCOME_NOTE = "휴리스틱 추정이며 인용 가능한 판결 결과가 아닙니다. 판결요지에는 주문이 없는 경우가 많아 '불명'이 흔합니다."

# Position-based outcome detection. Each rule is (label, priority, regex with a
# named group "k" marking the keyword, post-check(text, match) -> bool). The earliest
# keyword position wins; ties go to the lower priority number. Every regex needs a
# disposition ending, so negations/modals (기각하지 아니한다, 기각할 수 없다,
# 인용될 수 없다, 기각될 것이다, 각하되어야 한다, 파기사유가 없...) never match.
# All patterns are linear: no nested quantifiers, bounded look-around done in code.
_VERB = r"(?:한다|하였|했|하고|하며|합니다|함(?!에|으로|께))"
_APPLICANT_RE = re.compile(r"청구|상고|항소|신청|재심|심판|이의|재항고|항고|주장")


def _has_applicant(text: str, m: "re.Match") -> bool:
    start = m.start("k")
    return bool(_APPLICANT_RE.search(text, max(0, start - 40), start))


def _remand_follows(text: str, m: "re.Match") -> bool:
    return "환송" in text[m.end():m.end() + 40]


_OUTCOME_RULES = [
    ("파기환송", 0, re.compile(r"(?P<k>파기)\s*환송"), None),
    ("파기환송", 0, re.compile(rf"(?P<k>파기)\s*(?:하고|하며|하여|[,，])"), _remand_follows),
    ("파기자판", 1, re.compile(r"(?P<k>파기)\s*자판"), None),
    ("파기", 2, re.compile(rf"(?P<k>파기)\s*{_VERB}"), None),
    ("일부인용", 0, re.compile(r"(?P<k>일부)\s*(?:를|만을|만|은|는)?\s*인용(?!\s*(?:하지|되지|할\s*수|될\s*수))"), None),
    ("일부기각", 0, re.compile(r"(?P<k>일부)\s*(?:를|만을|만|은|는)?\s*기각(?!\s*(?:하지|되지|할\s*수|될\s*수))"), None),
    ("각하", 3, re.compile(rf"(?<!기)(?P<k>각하)\s*(?:{_VERB}|판결|결정)"), None),
    ("각하", 3, re.compile(r"(?:청구|상고|항소|항고|신청)\s*(?P<k>각하)(?!\s*(?:하지|할|되|사유|이유))"), None),
    ("기각", 3, re.compile(rf"(?P<k>기각)\s*(?:{_VERB}|판결|결정)"), None),
    ("기각", 3, re.compile(r"(?:청구|상고|항소|항고|신청)\s*(?P<k>기각)(?!\s*(?:하지|할|되|사유|이유))"), None),
    ("인용", 3, re.compile(rf"(?<!일부)(?<!일부 )(?P<k>인용)\s*(?:{_VERB}|하는\s*(?:판결|결정)|판결|결정)"), _has_applicant),
    ("취소", 3, re.compile(rf"(?P<k>취소)\s*(?:{_VERB}|판결|결정)"), None),
    ("취소", 3, re.compile(r"처분[을를]\s*(?P<k>취소)(?!\s*(?:하지|할|되|해야|하여야|를|소송))"), None),
]


# Legal term suffix patterns (Korean legal jargon indicators)
LEGAL_TERM_SUFFIXES = re.compile(
    r'[\uAC00-\uD7A3]{2,}(?:자|인|권|의무|행위|사항|절차|요건|책임|위반|처분|규정|조항|법률|계약|소송|재판|판결|채권|채무|손해|배상|이행|해제|해지|취소|무효|유효)'
)


def extract_outcome(text: str) -> str:
    """Extract court decision outcome from 판결요지 text (position-based).

    Heuristic, not a citable result: the earliest genuine disposition wins
    ("항소를 기각하고 상고를 각하한다" -> 기각). A keyword counts only with a
    disposition ending (기각한다/하였다/하고/함, 파기하고 ...); negations and
    modals (하지 아니, 할 수 없, 될 수 없, 될 것, 되어야, 사유가 없) and
    mentions such as "취소소송", "원심판결 인용" are ignored. 파기 followed by
    환송 within 40 characters is 파기환송; "일부를 인용" is 일부인용.
    Returns "불명" when unclear (common, since 판결요지 often has no 주문).
    """
    if not text:
        return "불명"
    best = None  # (position, priority, label)
    for label, priority, pattern, check in _OUTCOME_RULES:
        for m in pattern.finditer(text):
            if check is not None and not check(text, m):
                continue
            cand = (m.start("k"), priority, label)
            if best is None or cand < best:
                best = cand
            break  # first valid hit is the earliest for this rule
    return best[2] if best else "불명"


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
