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
# Same for SSE POST /messages/ (starlette Response default text/plain).
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
    expiring: bool = False    # idle expiry in progress; requests get the 404
    host: bytes = b"localhost"  # last Host header that passed validation


_EXPIRED_MEMORY = 4096  # tombstones of expired ids (bounded, oldest dropped)


class SessionBindingMiddleware:
    """Bind MCP session ids to the token that created them.

    Streamable HTTP: the ``mcp-session-id`` response header of a request that
    carried none is recorded against ``scope["state"]["token_id"]`` before the
    response is forwarded. Later requests naming a session bound to another
    token get the app's own "unknown session" 404 and never reach the app.
    SSE: the ``session_id`` in the first ``endpoint`` event of ``GET /sse`` is
    bound the same way (recorded before the chunk is forwarded, so the client
    cannot POST before the binding exists) and enforced on the
    ``session_id`` query parameter; removed when the stream ends.

    Memory: at most ``max_sessions`` bindings. Entries are never evicted while
    the session may still exist (an evicted binding would turn into an
    unbound session any token could use); at the cap new sessions are
    refused with 503 instead. Bindings are removed on owner DELETE (2xx), when
    the app answers 404 for a bound id (terminated/crashed session), on idle
    expiry and when an SSE stream ends. Ids unknown to the binding table pass
    to the app, which answers 404 itself.

    Idle expiry (``idle_ttl`` seconds, 0/None disables; needs ``terminate``):
    Streamable HTTP sessions otherwise live until the client DELETEs them.
    Per session we track the last activity (request start and end) and a
    counter of requests in flight; a session with a request in flight or an
    open GET stream is never idle. A background sweep (``run_sweeper``,
    started by create_app's lifespan) and a lazy check on every request for an
    idle session expire it. Expiry first marks the session ``expiring``
    (requests meanwhile get the standard unknown-session 404, whatever the
    token, and never reach the app), then ``await terminate(id, host)`` which
    must end the real session (create_app sends an internal DELETE to the
    inner app). Only when that returned 2xx/404 is the binding removed and
    ``release(id)`` called; on failure the mark is cleared, the binding kept
    (so an unbound live session cannot exist) and the next sweep retries.
    Expired ids are remembered (bounded) so every later request, owner
    included, gets the byte-identical standard 404 and the client opens a
    new session. Works in no-auth mode too (bindings are tracked there, only
    their enforcement is a no-op).
    SSE sessions need no expiry: the GET /sse stream *is* the session (mcp
    frees it when the stream ends, and the binding ends with the stream), so
    a connected client is alive by definition and POSTs to /messages/ do not
    need to count as liveness.

    In-memory, single process; no awaits between table reads and writes
    except around ``terminate``, which is guarded by the ``expiring`` mark.
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
        self._bindings: dict[str, str] = {}
        self._meta: dict[str, _SessionMeta] = {}
        self._expired: "OrderedDict[str, None]" = OrderedDict()
        self.sweep_task: Optional[asyncio.Task] = None

    @property
    def expiry_enabled(self) -> bool:
        return bool(self.idle_ttl) and self.idle_ttl > 0 and self._terminate is not None

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

    def _is_idle(self, m: _SessionMeta, now: float) -> bool:
        return m.active == 0 and not m.expiring and now - m.last >= self.idle_ttl

    async def _expire(self, sid: str) -> bool:
        """Terminate an idle session; True when it is gone (binding removed)."""
        m = self._meta.get(sid)
        if m is None or m.expiring or self._terminate is None:
            return False
        m.expiring = True
        done = False
        try:
            status = await self._terminate(sid, m.host)
            done = status is not None and (200 <= status < 300 or status == 404)
            if not done:
                logger.warning("idle session terminate returned %s; will retry", status)
        except Exception:
            logger.warning("idle session terminate failed; will retry", exc_info=True)
        finally:
            if done:
                self._drop(sid)
                self._expired[sid] = None
                while len(self._expired) > _EXPIRED_MEMORY:
                    self._expired.popitem(last=False)
            else:
                m.expiring = False  # keep the binding; next sweep retries
        return done

    async def sweep(self) -> int:
        """Expire every idle session once; returns how many were removed."""
        if not self.expiry_enabled:
            return 0
        now = self._clock()
        removed = 0
        for sid, m in list(self._meta.items()):
            if self._is_idle(m, now) and await self._expire(sid):
                removed += 1
        return removed

    async def run_sweeper(self) -> None:
        """Periodic sweep (interval min(ttl/4, 60) s) until cancelled."""
        interval = min(self.idle_ttl / 4, 60.0)
        while True:
            await asyncio.sleep(interval)
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

        header_ids = [
            v.decode("latin-1") for k, v in scope.get("headers", [])
            if k == b"mcp-session-id"
        ]
        query_ids = [
            v for k, v in parse_qsl(
                scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
            if k == "session_id"
        ]

        async def reject():
            if query_ids and not header_ids:
                await self._reject(send, b"text/plain; charset=utf-8", _SSE_NOT_FOUND)
            else:
                await self._reject(send, b"application/json", _STREAMABLE_NOT_FOUND)

        # expired / being expired: standard 404 for every token, owner included
        if any(i in self._expired or (i in self._meta and self._meta[i].expiring)
               for i in header_ids):
            await reject()
            return
        if any(self._foreign(i, token_id) for i in header_ids) or any(
                self._foreign(_sse_key(i), token_id) for i in query_ids):
            await reject()
            return

        # lazy expiry: do not depend on the sweep's timing
        if self.expiry_enabled:
            now = self._clock()
            for i in dict.fromkeys(header_ids):
                m = self._meta.get(i)
                if m is not None and self._is_idle(m, now):
                    await self._expire(i)
            if any(i in self._expired or (i in self._meta and self._meta[i].expiring)
                   for i in header_ids):
                await reject()
                return

        creating = not header_ids and method in ("POST", "GET") and not query_ids
        if creating and len(self._bindings) >= self.max_sessions and self.expiry_enabled:
            await self.sweep()  # idle sessions may free slots right now
        if creating and len(self._bindings) >= self.max_sessions:
            await _json_response(
                send, 503,
                {"error": "too_many_sessions", "message": "Session limit reached"},
                [(b"retry-after", b"30")],
            )
            return

        host = _header(scope, b"host")
        now = self._clock()
        tracked = [i for i in dict.fromkeys(header_ids) if i in self._meta]
        for i in tracked:
            m = self._meta[i]
            m.active += 1
            m.last = now
            if host:
                m.host = host
        created: Optional[str] = None

        status = 0
        sse_buf: Optional[bytearray] = bytearray() if (creating and method == "GET") else None
        sse_key: Optional[str] = None

        async def wrapped_send(message):
            nonlocal status, sse_buf, sse_key, created
            if message["type"] == "http.response.start":
                status = message["status"]
                if creating:
                    for k, v in message.get("headers", []):
                        if k.lower() == b"mcp-session-id":
                            sid = v.decode("latin-1")
                            self._bindings[sid] = token_id
                            self._meta[sid] = _SessionMeta(
                                last=self._clock(), active=1, host=host or b"localhost")
                            created = sid
                            break
                if sse_buf is not None and status != 200:
                    sse_buf = None
            elif message["type"] == "http.response.body" and sse_buf is not None:
                sse_buf += message.get("body", b"")
                m = _SSE_ENDPOINT_RE.search(bytes(sse_buf))
                if m is not None and b"\n" in sse_buf[m.end():]:
                    sse_key = _sse_key(m.group(1).decode("ascii"))
                    self._bindings[sse_key] = token_id
                    sse_buf = None
                elif len(sse_buf) > _SSE_SCAN_LIMIT:
                    sse_buf = None  # not an SSE endpoint stream; stop scanning
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            end = self._clock()
            for i in [*tracked, *([created] if created else [])]:
                m = self._meta.get(i)
                if m is not None:
                    m.active = max(0, m.active - 1)
                    m.last = end
            if sse_key is not None:
                self._bindings.pop(sse_key, None)
        for i in header_ids:
            if self._bindings.get(i) == token_id and (
                    status == 404 or (method == "DELETE" and 200 <= status < 300)):
                self._drop(i)

    @staticmethod
    async def _reject(send, ctype: bytes, body: bytes) -> None:
        await send({"type": "http.response.start", "status": 404, "headers": [
            (b"content-length", str(len(body)).encode()),
            (b"content-type", ctype),
        ]})
        await send({"type": "http.response.body", "body": body})
