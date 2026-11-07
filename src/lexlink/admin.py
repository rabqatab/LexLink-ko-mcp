"""
Operator admin API for the HTTP server (HTTP endpoints, not MCP tools).

Requests to ``/admin/...`` need ``Authorization: Bearer <admin token>`` (tokens
from LEXLINK_ADMIN_TOKENS; non-admin tokens get 403, missing/invalid 401 from
the auth middleware). Host/Origin are validated like the MCP endpoint and
rate limits apply (see http_security.RateLimitMiddleware). Every request is
logged as ``method: "admin:<action>"`` without bodies or secrets.

Endpoints:
    GET    /admin/logs          request log rows (filters below), newest first
    GET    /admin/tokens        list env + issued tokens (never token values)
    POST   /admin/tokens        {"name": "..."} -> issue a user token (shown once)
    DELETE /admin/tokens/<name> revoke an issued token and end its sessions

``/admin/logs`` query: ``date`` (YYYY-MM-DD) or ``from``/``to`` (inclusive; default
today), ``limit`` (1-1000, default 100), and equality filters ``token`` (name),
``token_id``, ``tool_name``, ``status``, ``client_name``, ``method``.

Adding an admin function: write ``async def handler(ctx, req) -> Reply`` and
decorate it with ``@admin_route("GET", "/admin/<path>", "<action>")``; auth,
host checks, rate limiting and logging are already done by then. Use
``Reply(status, body)`` for the result and raise ``AdminError(status, code,
message)`` for failures.
"""

import asyncio
import json
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import parse_qsl

from starlette.requests import Request

from .http_security import _json_response, is_admin_path
from .tokens import NAME_RE, TokenError, TokenRegistry

MAX_BODY_BYTES = 4096
MAX_LOG_LIMIT = 1000
DEFAULT_LOG_LIMIT = 100
MAX_LOG_DAYS = 366
_LOG_FILTERS = ("token_id", "tool_name", "status", "client_name", "method")
_NAME_ARG_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class AdminError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class Reply:
    status: int
    body: dict
    headers: tuple = ()


@dataclass
class AdminContext:
    """What handlers may touch; one per app."""
    registry: TokenRegistry
    log_dir_fn: Callable[[], Any]
    flush_logs: Callable[[], None]
    end_sessions: Callable[[str], Awaitable[int]]


@dataclass
class AdminRequest:
    scope: dict
    query: dict = field(default_factory=dict)
    path_args: dict = field(default_factory=dict)
    _receive: Any = None

    async def json_body(self) -> dict:
        """Parsed JSON object body (<= MAX_BODY_BYTES); AdminError 400 otherwise."""
        buf = bytearray()
        while True:
            msg = await self._receive()
            if msg["type"] != "http.request":
                break
            buf += msg.get("body", b"")
            if len(buf) > MAX_BODY_BYTES:
                raise AdminError(413, "body_too_large", "request body too large")
            if not msg.get("more_body"):
                break
        try:
            data = json.loads(bytes(buf) or b"{}")
        except ValueError:
            raise AdminError(400, "invalid_json", "body must be a JSON object") from None
        if not isinstance(data, dict):
            raise AdminError(400, "invalid_json", "body must be a JSON object")
        return data


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

@dataclass
class _Route:
    method: str
    pattern: "re.Pattern[str]"
    action: str
    handler: Callable


_ROUTES: list[_Route] = []


def admin_route(method: str, pattern: str, action: str):
    """Register ``handler(ctx, req) -> Reply``; ``<name>`` segments become path_args."""
    regex = re.compile(
        "^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "/?$")

    def deco(fn):
        _ROUTES.append(_Route(method, regex, action, fn))
        return fn
    return deco


def _resolve(method: str, path: str):
    """(route, path_args, path_known). path_known: some route matches the path."""
    known = False
    for r in _ROUTES:
        m = r.pattern.match(path)
        if m is None:
            continue
        known = True
        if r.method == method:
            return r, m.groupdict(), True
    return None, {}, known


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _parse_day(raw: str, what: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise AdminError(400, "invalid_date", f"{what} must be YYYY-MM-DD") from None


def _read_logs(log_dir, days: list[date], filters: dict, limit: int):
    """Last ``limit`` matching rows over ``days`` (chronological), plus the match count."""
    rows: deque = deque(maxlen=limit)
    matched = 0
    for day in days:
        path = log_dir / f"{day.isoformat()}.jsonl"
        try:
            f = open(path, encoding="utf-8")
        except OSError:
            continue
        with f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                if any(row.get(k) != v for k, v in filters.items()):
                    continue
                matched += 1
                rows.append(row)
    return list(rows), matched


@admin_route("GET", "/admin/logs", "logs")
async def logs(ctx: AdminContext, req: AdminRequest) -> Reply:
    q = req.query
    if "date" in q and ("from" in q or "to" in q):
        raise AdminError(400, "invalid_range", "use either date or from/to")
    if "date" in q:
        start = end = _parse_day(q["date"], "date")
    else:
        today = date.today()
        start = _parse_day(q["from"], "from") if "from" in q else today
        end = _parse_day(q["to"], "to") if "to" in q else today
    if end < start:
        raise AdminError(400, "invalid_range", "'to' is before 'from'")
    if (end - start).days >= MAX_LOG_DAYS:
        raise AdminError(400, "invalid_range", f"range is limited to {MAX_LOG_DAYS} days")
    try:
        limit = int(q.get("limit", DEFAULT_LOG_LIMIT))
    except ValueError:
        limit = 0
    if not 1 <= limit <= MAX_LOG_LIMIT:
        raise AdminError(400, "invalid_limit", f"limit must be 1-{MAX_LOG_LIMIT}")

    filters = {k: q[k] for k in _LOG_FILTERS if k in q}
    if "token" in q:
        ids = ctx.registry.ids_for_name(q["token"])
        if "token_id" in filters and filters["token_id"] not in ids:
            ids = []
        if len(ids) == 1:
            filters["token_id"] = ids[0]
        else:
            return Reply(200, {"from": start.isoformat(), "to": end.isoformat(),
                               "matched": 0, "returned": 0, "rows": []})
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    def work():
        ctx.flush_logs()  # entries of the last requests may still be queued
        return _read_logs(ctx.log_dir_fn(), days, filters, limit)

    rows, matched = await asyncio.to_thread(work)
    rows.reverse()  # newest first
    for row in rows:
        tid = row.get("token_id")
        name = ctx.registry.name_for(tid) if isinstance(tid, str) else None
        if name is not None:
            row["token_name"] = name
    return Reply(200, {"from": start.isoformat(), "to": end.isoformat(),
                       "matched": matched, "returned": len(rows), "rows": rows})


@admin_route("GET", "/admin/tokens", "list_tokens")
async def list_tokens(ctx: AdminContext, req: AdminRequest) -> Reply:
    return Reply(200, {"tokens": ctx.registry.list_tokens()})


@admin_route("POST", "/admin/tokens", "issue_token")
async def issue_token(ctx: AdminContext, req: AdminRequest) -> Reply:
    body = await req.json_body()
    name = body.get("name")
    if isinstance(name, str) and NAME_RE.fullmatch(name):
        req.scope["state"]["admin_target"] = name
    rec, token = ctx.registry.issue(name)
    return Reply(201, {
        **rec.public(), "token": token,
        "note": "This is the only time the token is shown; store it now.",
    }, headers=((b"cache-control", b"no-store"),))


@admin_route("DELETE", "/admin/tokens/<name>", "revoke_token")
async def revoke_token(ctx: AdminContext, req: AdminRequest) -> Reply:
    name = req.path_args["name"]
    if not _NAME_ARG_RE.fullmatch(name):
        raise AdminError(400, "invalid_name", "name must match [a-z0-9][a-z0-9_-]{0,62}")
    if NAME_RE.fullmatch(name):
        req.scope["state"]["admin_target"] = name
    rec, newly = ctx.registry.revoke(name)
    ended = await ctx.end_sessions(rec.token_id)
    return Reply(200, {**rec.public(), "already_revoked": not newly, "sessions_ended": ended})


# ---------------------------------------------------------------------------
# ASGI glue
# ---------------------------------------------------------------------------

class AdminMiddleware:
    """Serves ``/admin/*`` and passes everything else to ``app``.

    Sits inside auth, logging and rate limiting. ``security`` is a
    ``TransportSecurityMiddleware`` (same Host/Origin rules as the MCP app).
    """

    def __init__(self, app, ctx: AdminContext, security):
        self.app = app
        self.ctx = ctx
        self.security = security

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not is_admin_path(scope):
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        method, path = scope.get("method", ""), scope.get("path", "")
        route, path_args, path_known = _resolve(method, path)
        state["admin_action"] = route.action if route else "unknown"

        denied = await self.security.validate_request(Request(scope), is_post=False)
        if denied is not None:
            await denied(scope, receive, send)
            return
        if not state.get("is_admin"):
            await _json_response(send, 403, {
                "error": "forbidden", "message": "An admin token is required"})
            return
        if route is None:
            if path_known:
                await _json_response(send, 405, {
                    "error": "method_not_allowed", "message": "Method not allowed"})
            else:
                await _json_response(send, 404, {
                    "error": "not_found", "message": "Unknown admin endpoint"})
            return

        query = dict(parse_qsl(scope.get("query_string", b"").decode("latin-1")))
        req = AdminRequest(scope, query, path_args, receive)
        try:
            reply = await route.handler(self.ctx, req)
        except (AdminError, TokenError) as exc:
            reply = Reply(exc.status, {"error": exc.code, "message": exc.message})
        await _json_response(send, reply.status, reply.body, reply.headers)
