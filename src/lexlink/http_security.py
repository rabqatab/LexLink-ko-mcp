"""
HTTP hardening for the LexLink HTTP/SSE server (pure ASGI, no BaseHTTPMiddleware).

Provides:
    - BearerAuthMiddleware: constant-time bearer token check (fail closed)
    - RateLimitMiddleware: per-token concurrency + sliding-window limits
    - SessionBindingMiddleware: MCP session id -> token binding (Streamable HTTP + SSE)
    - build_transport_security(): Host/Origin validation settings for FastMCP
    - resolve_client_ip(): X-Forwarded-For handling for trusted proxies

All middlewares only act on ``scope["type"] == "http"``; lifespan is passed
straight through, websocket scopes are closed with 1008 by the auth middleware, and no response body is ever
buffered, so streaming (SSE) works unchanged.

Environment variables:
    LEXLINK_AUTH_TOKENS       "name:token,name2:token2"
    LEXLINK_ALLOW_NO_AUTH     must be exactly "true" to start without tokens
    LEXLINK_ALLOWED_HOSTS     comma list of allowed Host header values
    LEXLINK_ALLOWED_ORIGINS   comma list of allowed Origin header values
    LEXLINK_TRUSTED_PROXIES   comma list of exact peer IPs allowed to set X-Forwarded-For
    LEXLINK_MAX_CONCURRENCY   concurrent POST requests per token (default 8)
    LEXLINK_RATE_LIMIT_PER_MIN  POST requests per minute per token (default 60)
    LEXLINK_MAX_SESSIONS      bound MCP sessions kept in memory (default 10000)
    LEXLINK_SESSION_IDLE_TTL_SEC  idle Streamable HTTP sessions are terminated after
                              this many seconds without activity (default 3600, 0 disables)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import re
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl
from uuid import UUID

logger = logging.getLogger(__name__)

NO_AUTH_TOKEN_ID = "noauth"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _csv_env(name: str) -> list[str]:
    return [p.strip() for p in os.getenv(name, "").split(",") if p.strip()]


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from None


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a number, got {raw!r}") from None
    if not math.isfinite(value) or value < 0:
        raise RuntimeError(f"{name} must be a finite number >= 0, got {raw!r}")
    return value


def token_id_for(token: str) -> str:
    """Stable, non-reversible id for a token (sha256 hex, first 12 chars)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def parse_auth_tokens(raw: str) -> list[str]:
    """Parse ``"name:token,name2:token2"`` into a list of token values.

    Raises RuntimeError on any malformed entry or duplicate name/token.
    Names are only used for validation; they are never logged or stored.
    """
    names: set[str] = set()
    tokens: list[str] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, token = entry.partition(":")
        name, token = name.strip(), token.strip()
        if not sep or not name or not token:
            raise RuntimeError(
                "LEXLINK_AUTH_TOKENS has a malformed entry; expected 'name:token' "
                "pairs separated by commas"
            )
        if name in names or token in tokens:
            raise RuntimeError("LEXLINK_AUTH_TOKENS has a duplicate name or token")
        names.add(name)
        tokens.append(token)
    if not tokens:
        raise RuntimeError(
            "LEXLINK_AUTH_TOKENS is set but contains no 'name:token' entries"
        )
    return tokens


def load_auth_tokens() -> Optional[list[str]]:
    """Read auth config from the environment.

    Returns the token list, or None when running without auth
    (LEXLINK_ALLOW_NO_AUTH=true). Raises RuntimeError (fail closed) otherwise.
    """
    raw = os.getenv("LEXLINK_AUTH_TOKENS", "").strip()
    if raw:
        return parse_auth_tokens(raw)
    if os.getenv("LEXLINK_ALLOW_NO_AUTH", "") == "true":
        logger.warning(
            "!!! LEXLINK_ALLOW_NO_AUTH=true: the server is running WITHOUT "
            "authentication. Anyone who can reach it can use the server's OC "
            "quota. Use only for PlayMCP no-auth registration, behind rate limits. !!!"
        )
        return None
    raise RuntimeError(
        "HTTP mode requires authentication: set LEXLINK_AUTH_TOKENS="
        "'name:token,...' or, only for PlayMCP no-auth registration, "
        "LEXLINK_ALLOW_NO_AUTH=true"
    )


def build_transport_security():
    """TransportSecuritySettings from LEXLINK_ALLOWED_HOSTS/ORIGINS, or None.

    None leaves FastMCP's default (DNS-rebinding protection for localhost only).
    Protection is never disabled.
    """
    hosts = _csv_env("LEXLINK_ALLOWED_HOSTS")
    if not hosts and _csv_env("LEXLINK_ALLOWED_ORIGINS"):
        raise RuntimeError(
            "LEXLINK_ALLOWED_ORIGINS requires LEXLINK_ALLOWED_HOSTS to be set "
            "(origins are not enforced without host validation settings)"
        )
    if not hosts:
        logger.warning(
            "LEXLINK_ALLOWED_HOSTS is not set: FastMCP's default only accepts "
            "localhost Host headers, so requests via a public domain will be "
            "rejected (421). Set LEXLINK_ALLOWED_HOSTS to your public host(s)."
        )
        return None
    from mcp.server.transport_security import TransportSecuritySettings

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=_csv_env("LEXLINK_ALLOWED_ORIGINS"),
    )


def resolve_client_ip(scope: dict, trusted_proxies: frozenset[str]) -> Optional[str]:
    """Client IP: X-Forwarded-For only if the peer is a trusted proxy.

    Takes the rightmost XFF address that is not itself a trusted proxy.
    """
    client = scope.get("client")
    peer = client[0] if client else None
    if peer is None or peer not in trusted_proxies:
        return peer
    parts: list[str] = []
    for k, v in scope.get("headers", []):
        if k == b"x-forwarded-for":
            parts.extend(p.strip() for p in v.decode("latin-1").split(","))
    for addr in reversed(parts):
        if addr and addr not in trusted_proxies:
            return addr
    return peer


# ---------------------------------------------------------------------------
# ASGI helpers
# ---------------------------------------------------------------------------

async def _json_response(send, status: int, body: dict, extra_headers=()) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode()),
        *extra_headers,
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


def _header(scope: dict, name: bytes) -> Optional[bytes]:
    for k, v in scope.get("headers", []):
        if k == name:
            return v
    return None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class BearerAuthMiddleware:
    """Require ``Authorization: Bearer <token>`` matching one configured token.

    ``tokens=None`` means no-auth mode (explicitly allowed by the caller).
    Sets ``scope["state"]["token_id"]`` (sha256 prefix, never the token/name).
    """

    def __init__(self, app, tokens: Optional[list[str]]):
        self.app = app
        self._tokens = (
            None if tokens is None
            else [(t.encode("utf-8"), token_id_for(t)) for t in tokens]
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            # websocket (or unknown) scopes are never authorised here
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        state = scope.setdefault("state", {})
        if self._tokens is None:
            state["token_id"] = NO_AUTH_TOKEN_ID
            await self.app(scope, receive, send)
            return

        presented = b""
        auth = _header(scope, b"authorization")
        if auth is not None:
            scheme, _, value = auth.partition(b" ")
            if scheme.lower() == b"bearer":
                presented = value.strip()

        matched: Optional[str] = None
        for token, tid in self._tokens:  # no early exit
            if hmac.compare_digest(presented, token):
                matched = tid
        if matched is None:
            await _json_response(
                send, 401,
                {"error": "unauthorized", "message": "Missing or invalid bearer token"},
                [(b"www-authenticate", b"Bearer")],
            )
            return
        state["token_id"] = matched
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------

class RateLimitMiddleware:
    """Per-token concurrency and sliding-window per-minute limits (POST only).

    In-memory, single process. State changes happen without awaits in between,
    so no locking is needed on the asyncio event loop.
    """

    WINDOW_SECONDS = 60.0

    def __init__(self, app, max_concurrency: Optional[int] = None,
                 per_minute: Optional[int] = None, clock=time.monotonic):
        self.app = app
        self.max_concurrency = (
            _int_env("LEXLINK_MAX_CONCURRENCY", 8) if max_concurrency is None else max_concurrency
        )
        self.per_minute = (
            _int_env("LEXLINK_RATE_LIMIT_PER_MIN", 60) if per_minute is None else per_minute
        )
        self._clock = clock
        self._inflight: dict[str, int] = {}
        self._hits: dict[str, deque] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        key = scope.get("state", {}).get("token_id", NO_AUTH_TOKEN_ID)
        now = self._clock()

        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.WINDOW_SECONDS:
            hits.popleft()
        if self.per_minute > 0 and len(hits) >= self.per_minute:
            retry = max(1, math.ceil(self.WINDOW_SECONDS - (now - hits[0])))
            await _json_response(
                send, 429,
                {"error": "rate_limited", "message": "Too many requests per minute"},
                [(b"retry-after", str(retry).encode())],
            )
            return
        if self.max_concurrency > 0 and self._inflight.get(key, 0) >= self.max_concurrency:
            await _json_response(
                send, 429,
                {"error": "too_many_concurrent_requests",
                 "message": "Too many concurrent requests"},
                [(b"retry-after", b"1")],
            )
            return

        hits.append(now)
        self._inflight[key] = self._inflight.get(key, 0) + 1
        try:
            await self.app(scope, receive, send)
        finally:
            left = self._inflight.get(key, 1) - 1
            if left > 0:
                self._inflight[key] = left
            else:
                self._inflight.pop(key, None)


# ---------------------------------------------------------------------------
# Session binding
# ---------------------------------------------------------------------------

# Byte-identical to what mcp's StreamableHTTPSessionManager sends for an
# unknown session id (404, application/json), so a foreign id is
# indistinguishable from a non-existent one.
_STREAMABLE_NOT_FOUND = (
    b'{"jsonrpc":"2.0","id":"server-error",'
    b'"error":{"code":-32600,"message":"Session not found"}}'
)
# Same for SSE POST /messages/ (starlette Response without media_type: no
# content-type header at all).
_SSE_NOT_FOUND = b"Could not find session"
_SSE_ENDPOINT_RE = re.compile(rb"session_id=([0-9A-Za-z-]{32,36})")
_SSE_SCAN_LIMIT = 4096


def _sse_key(raw: str) -> str:
    """Canonical key for an SSE session id (UUID hex, however it is spelled)."""
    try:
        return "sse:" + UUID(hex=raw).hex
    except ValueError:
        return "sse:" + raw


@dataclass
class _SessionMeta:
    """Activity record of one bound Streamable HTTP session."""
    last: float
    active: int = 0           # requests (incl. open GET streams) in flight
    expiring: bool = False    # terminate in progress; requests get the 404
    host: bytes = b"localhost"  # last Host header that passed validation
    doomed: bool = False      # unusable (creating response was not 2xx): terminate ASAP
    backoff: float = 0.0      # current retry delay after failed terminates
    next_try: float = 0.0     # no terminate attempt before this clock value


_EXPIRED_MEMORY = 4096  # tombstones of expired ids (bounded, oldest dropped)
_MAX_BACKOFF = 900.0    # failed-terminate retry delay cap (15 minutes)


def _default_host() -> bytes:
    """Host header for internal DELETEs when no validated one is known."""
    hosts = _csv_env("LEXLINK_ALLOWED_HOSTS")
    if not hosts:
        return b"localhost"
    first = hosts[0]
    if first.endswith(":*"):
        first = first[:-2] + ":80"
    return first.encode("latin-1", "replace")


def _is_sse_messages(scope: dict) -> bool:
    return scope.get("path", "").rstrip("/") == "/messages"


class SessionBindingMiddleware:
    """Bind MCP session ids to the token that created them.

    Streamable HTTP: any request without an ``mcp-session-id`` header may make
    mcp create a session (whatever the method, path or query), so every such
    request reserves a cap slot before the app runs (503 at the cap; the
    reservation is released in ``finally`` or when it turns into a binding).
    If the response carries ``mcp-session-id`` the id is bound to
    ``scope["state"]["token_id"]`` before the response is forwarded. When
    that response is not 2xx the session is unusable: it is terminated right
    after the response (``terminate`` + ``release``); on failure the binding
    stays and the sweeper retries. Later requests naming a session bound to
    another token get the app's own "unknown session" 404 and never reach the
    app; a request naming several different ids gets that 404 too, so the id
    the app uses is the one that was checked.
    SSE: the ``session_id`` in the first ``endpoint`` event of ``GET /sse`` is
    bound the same way (recorded before the chunk is forwarded) and enforced
    on the ``session_id`` query of ``/messages/`` only. When the stream ends
    the binding is removed and the id is tombstoned, so later POSTs get the
    unknown-session 404 for every token.

    Memory: at most ``max_sessions`` bindings plus reservations. Entries are
    never evicted while the session may still exist; at the cap new sessions
    are refused with 503. Bindings are removed only after a confirmed
    terminate (idle expiry / unusable session) or an owner DELETE answered
    2xx. A 404 never frees a binding: dead sessions are freed by idle expiry
    or terminate (which treats 404 as gone).

    Idle expiry (``idle_ttl`` seconds, 0/None disables; needs ``terminate``):
    per session we track last activity and requests in flight; a session with
    a request in flight or an open GET stream is never idle. A background
    sweep (``run_sweeper``) and a lazy check expire idle sessions. Expiry
    marks the session ``expiring`` (requests get the standard 404), then
    ``await terminate(id, host)``; only after 2xx/404 is the binding removed
    and ``release(id)`` called. On failure the binding is kept and the retry
    is delayed exponentially per session (sweep interval, doubling, capped at
    15 minutes) with one concise warning line (no traceback, no session id).
    ``host`` is only taken from requests whose response was not 421/404, and
    defaults to the first LEXLINK_ALLOWED_HOSTS entry.
    Expired ids are remembered (bounded). Works in no-auth mode too.

    In-memory, single process.
    """

    def __init__(self, app, max_sessions: Optional[int] = None,
                 idle_ttl: Optional[float] = None, clock=time.monotonic,
                 terminate=None, release=None):
        self.app = app
        self.max_sessions = (
            _int_env("LEXLINK_MAX_SESSIONS", 10000) if max_sessions is None else max_sessions
        )
        self.idle_ttl = (
            _float_env("LEXLINK_SESSION_IDLE_TTL_SEC", 3600.0) if idle_ttl is None else idle_ttl
        )
        self._clock = clock
        self._terminate = terminate
        self._release = release
        self._default_host = _default_host()
        self._bindings: dict[str, str] = {}
        self._meta: dict[str, _SessionMeta] = {}
        self._reserved = 0
        self._expired: "OrderedDict[str, None]" = OrderedDict()
        self.sweep_task: Optional[asyncio.Task] = None

    @property
    def expiry_enabled(self) -> bool:
        return bool(self.idle_ttl) and self.idle_ttl > 0 and self._terminate is not None

    @property
    def sweeper_enabled(self) -> bool:
        """Sweeping is needed for idle expiry and for retrying failed terminates."""
        return self._terminate is not None

    @property
    def sweep_interval(self) -> float:
        return min(self.idle_ttl / 4, 60.0) if self.idle_ttl and self.idle_ttl > 0 else 60.0

    def _foreign(self, key: str, token_id: str) -> bool:
        owner = self._bindings.get(key)
        return owner is not None and not hmac.compare_digest(
            owner.encode("utf-8"), token_id.encode("utf-8"))

    def _drop(self, sid: str) -> None:
        self._bindings.pop(sid, None)
        self._meta.pop(sid, None)
        if self._release is not None:
            try:
                self._release(sid)
            except Exception:
                logger.warning("session release hook failed", exc_info=True)

    def _tombstone(self, key: str) -> None:
        self._expired[key] = None
        while len(self._expired) > _EXPIRED_MEMORY:
            self._expired.popitem(last=False)

    def _is_gone(self, key: str) -> bool:
        m = self._meta.get(key)
        return key in self._expired or (m is not None and m.expiring)

    def _is_idle(self, m: _SessionMeta, now: float) -> bool:
        if m.active != 0 or m.expiring or now < m.next_try:
            return False
        if m.doomed:
            return True
        return bool(self.idle_ttl) and self.idle_ttl > 0 and now - m.last >= self.idle_ttl

    async def _expire(self, sid: str) -> bool:
        """Terminate a session; True when it is gone (binding removed)."""
        m = self._meta.get(sid)
        if m is None or m.expiring or self._terminate is None:
            return False
        m.expiring = True
        done = False
        problem = ""
        try:
            status = await self._terminate(sid, m.host)
            done = status is not None and (200 <= status < 300 or status == 404)
            if not done:
                problem = f"status {status}"
        except Exception as exc:
            problem = type(exc).__name__
        finally:
            if done:
                self._drop(sid)
                self._tombstone(sid)
            else:
                m.expiring = False  # keep the binding; retry after backoff
                m.backoff = min(
                    max(m.backoff * 2, self.sweep_interval), _MAX_BACKOFF)
                m.next_try = self._clock() + m.backoff
                if problem:
                    logger.warning(
                        "session terminate failed (%s); retry in %.0fs",
                        problem, m.backoff)
        return done

    async def sweep(self) -> int:
        """Terminate every idle/unusable session once; returns how many were removed."""
        if not self.sweeper_enabled:
            return 0
        now = self._clock()
        removed = 0
        for sid, m in list(self._meta.items()):
            if self._is_idle(m, now) and await self._expire(sid):
                removed += 1
        return removed

    async def run_sweeper(self) -> None:
        """Periodic sweep (interval min(ttl/4, 60) s) until cancelled."""
        while True:
            await asyncio.sleep(self.sweep_interval)
            try:
                await self.sweep()
            except Exception:
                logger.warning("session sweep failed", exc_info=True)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token_id = scope.get("state", {}).get("token_id", NO_AUTH_TOKEN_ID)
        method = scope.get("method")
        sse_messages = _is_sse_messages(scope)

        header_ids = [
            v.decode("latin-1") for k, v in scope.get("headers", [])
            if k == b"mcp-session-id"
        ]
        # query session_id is only meaningful (and enforced) on SSE /messages/
        query_ids = [
            v for k, v in parse_qsl(
                scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
            if k == "session_id"
        ] if sse_messages else []

        async def reject():
            if query_ids and not header_ids:
                await self._reject(send, None, _SSE_NOT_FOUND)
            else:
                await self._reject(send, b"application/json", _STREAMABLE_NOT_FOUND)

        distinct = list(dict.fromkeys(header_ids))
        # several different ids: the app would use the first, we cannot be sure
        # which one is meant -> standard 404, nothing is checked against a wrong id
        if len(distinct) > 1:
            await reject()
            return

        # expired / being expired / ended SSE: standard 404 for every token
        if any(self._is_gone(i) for i in distinct) or any(
                _sse_key(i) in self._expired for i in query_ids):
            await reject()
            return
        if any(self._foreign(i, token_id) for i in distinct) or any(
                self._foreign(_sse_key(i), token_id) for i in query_ids):
            await reject()
            return

        # lazy expiry: do not depend on the sweep's timing
        if self.expiry_enabled:
            now = self._clock()
            for i in distinct:
                m = self._meta.get(i)
                if m is not None and self._is_idle(m, now):
                    await self._expire(i)
            if any(self._is_gone(i) for i in distinct):
                await reject()
                return

        # Every request without a session header may create a session in mcp.
        creating = not header_ids and not sse_messages
        reserved = False

        def unreserve():
            nonlocal reserved
            if reserved:
                reserved = False
                self._reserved -= 1

        if creating:
            if self._count() >= self.max_sessions and self.sweeper_enabled:
                await self.sweep()  # idle sessions may free slots right now
            if self._count() >= self.max_sessions:
                await _json_response(
                    send, 503,
                    {"error": "too_many_sessions", "message": "Session limit reached"},
                    [(b"retry-after", b"30")],
                )
                return
            self._reserved += 1
            reserved = True

        host = _header(scope, b"host")
        now = self._clock()
        tracked = [i for i in distinct if i in self._meta]
        for i in tracked:
            self._meta[i].active += 1
            self._meta[i].last = now
        created: Optional[str] = None
        doomed: Optional[str] = None

        status = 0
        sse_buf: Optional[bytearray] = bytearray() if (creating and method == "GET") else None
        sse_key: Optional[str] = None

        async def wrapped_send(message):
            nonlocal status, sse_buf, sse_key, created, doomed
            if message["type"] == "http.response.start":
                status = message["status"]
                if creating:
                    for k, v in message.get("headers", []):
                        if k.lower() == b"mcp-session-id":
                            sid = v.decode("latin-1")
                            if sid not in self._bindings:
                                self._bindings[sid] = token_id
                                self._meta[sid] = _SessionMeta(
                                    last=self._clock(), active=1,
                                    host=self._validated_host(host, status),
                                    doomed=not 200 <= status < 300)
                                unreserve()
                                created = sid
                                if not 200 <= status < 300:
                                    doomed = sid
                            break
                if sse_buf is not None and status != 200:
                    sse_buf = None
            elif message["type"] == "http.response.body" and sse_buf is not None:
                sse_buf += message.get("body", b"")
                m = _SSE_ENDPOINT_RE.search(bytes(sse_buf))
                if m is not None and b"\n" in sse_buf[m.end():]:
                    sse_key = _sse_key(m.group(1).decode("ascii"))
                    self._bindings[sse_key] = token_id
                    unreserve()
                    sse_buf = None
                elif len(sse_buf) > _SSE_SCAN_LIMIT:
                    sse_buf = None  # not an SSE endpoint stream; stop scanning
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            unreserve()
            end = self._clock()
            for i in [*tracked, *([created] if created else [])]:
                m = self._meta.get(i)
                if m is not None:
                    m.active = max(0, m.active - 1)
                    m.last = end
                    # host is only trusted after the app accepted the request
                    if host and i in tracked and status not in (0, 404, 421):
                        m.host = host
            if sse_key is not None:
                self._bindings.pop(sse_key, None)
                self._tombstone(sse_key)
        # Owner DELETE answered 2xx: the app terminated the id it was given.
        if (method == "DELETE" and 200 <= status < 300 and distinct
                and self._bindings.get(distinct[0]) == token_id):
            self._drop(distinct[0])
        if doomed is not None and doomed in self._meta:
            await self._expire(doomed)

    def _count(self) -> int:
        return len(self._bindings) + self._reserved

    def _validated_host(self, host: Optional[bytes], status: int) -> bytes:
        if host and status not in (404, 421):
            return host
        return self._default_host

    @staticmethod
    async def _reject(send, ctype: Optional[bytes], body: bytes) -> None:
        headers = [(b"content-length", str(len(body)).encode())]
        if ctype is not None:
            headers.append((b"content-type", ctype))
        await send({"type": "http.response.start", "status": 404, "headers": headers})
        await send({"type": "http.response.body", "body": body})
