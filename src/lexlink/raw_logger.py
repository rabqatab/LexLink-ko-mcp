"""
HTTP-mode traffic logger (pure ASGI, privacy-preserving by default).

LoggingMiddleware forwards every ASGI message immediately and unchanged while
keeping capped copies of the request/response bytes. One JSONL entry per MCP
call is queued to a single background daemon thread, so the event loop never
blocks on disk I/O and streams are never buffered.

Default entry fields: timestamp, token_id, method, tool_name, declared argument
key names (no values; unknown ones only as a count), status, error_code, http_status, response_bytes,
duration_ms, client_ip. With LEXLINK_LOG_BODIES=true, argument values (minus
oc/token/authorization keys) and the result body are logged too, with the OC
credential redacted.

Environment variables:
    LEXLINK_LOG_DIR             log directory (default: <repo>/logs/playmcp)
    LEXLINK_LOG_RETENTION_DAYS  delete YYYY-MM-DD.jsonl older than N days (default 30; 0 = keep)
    LEXLINK_LOG_BODIES          "true" to log argument values and result bodies
    LEXLINK_LOG_CAPTURE_MAX_BYTES  per-direction capture cap (default 1048576)
    LEXLINK_TRUSTED_PROXIES     exact peer IPs allowed to set X-Forwarded-For
"""

import atexit
import json
import logging
import os
import queue
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .client import redact_oc
from .http_security import NO_AUTH_TOKEN_ID, resolve_client_ip

logger = logging.getLogger(__name__)

# Default log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs" / "playmcp"

_DATED_FILE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.jsonl$")
_SENSITIVE_KEYS = {"oc", "apikey", "api_key", "password", "secret"}
_SENSITIVE_SUBSTRINGS = ("token", "authorization")
UNKNOWN = "<unknown>"
# Fixed set of MCP methods that may appear in default-mode logs. Anything else
# (client-controlled free text) is logged as "<unknown>".
KNOWN_METHODS = frozenset({
    "initialize", "ping", "tools/list", "tools/call", "prompts/list",
    "prompts/get", "resources/list", "resources/templates/list",
    "resources/read", "resources/subscribe", "resources/unsubscribe",
    "completion/complete", "logging/setLevel", "notifications/initialized",
    "notifications/cancelled", "notifications/progress",
    "notifications/roots/list_changed",
})
_DROP_WARN_INTERVAL = 60.0
_RESPONSE_KEY_RE = re.compile(r'error_code\\*"\s*:\s*\\*"([A-Za-z0-9_]+)')


def get_log_dir() -> Path:
    raw = os.getenv("LEXLINK_LOG_DIR", "").strip()
    return Path(raw) if raw else LOG_DIR


# ---------------------------------------------------------------------------
# Background writer
# ---------------------------------------------------------------------------

class LogWriter:
    """Single daemon thread appending JSONL lines; applies retention."""

    def __init__(self, log_dir: Path, retention_days: int = 30, maxsize: int = 10000):
        self.log_dir = Path(log_dir)
        self.retention_days = retention_days
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._current_day: Optional[date] = None
        self.dropped = 0
        self._dropped_reported = 0
        self._last_drop_warn = float("-inf")
        self._thread = threading.Thread(
            target=self._run, name="lexlink-log-writer", daemon=True
        )
        self._thread.start()

    def write(self, entry: dict) -> None:
        """Queue an entry; never blocks (drops if the queue is full)."""
        try:
            self._queue.put_nowait(entry)
        except queue.Full:
            self.dropped += 1
            self._maybe_warn_drops()

    def _maybe_warn_drops(self) -> None:
        """Warn about dropped entries at most once per minute."""
        now = time.monotonic()
        if now - self._last_drop_warn < _DROP_WARN_INTERVAL:
            return
        self._last_drop_warn = now
        logger.warning(
            "log queue full: %d entries dropped so far (%d since last warning)",
            self.dropped, self.dropped - self._dropped_reported,
        )
        self._dropped_reported = self.dropped

    def flush(self) -> None:
        """Block until everything queued so far is written."""
        self._queue.join()

    def _run(self) -> None:
        try:  # retention runs at writer start, not only at the first write
            self._current_day = datetime.now().date()
            self.apply_retention(self._current_day)
        except Exception as e:
            logger.warning("log retention failed: %s", type(e).__name__)
        while True:
            entry = self._queue.get()
            try:
                self._write_entry(entry)
            except Exception as e:  # never crash the writer
                logger.warning("log write failed: %s", type(e).__name__)
            finally:
                self._queue.task_done()

    def _write_entry(self, entry: dict) -> None:
        today = datetime.now().date()
        self.log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if today != self._current_day:
            self._current_day = today
            self.apply_retention(today)
        path = self.log_dir / f"{today.isoformat()}.jsonl"
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def apply_retention(self, today: Optional[date] = None) -> None:
        """Delete only YYYY-MM-DD.jsonl files older than retention_days."""
        if self.retention_days <= 0:
            return
        today = today or datetime.now().date()
        cutoff = today - timedelta(days=self.retention_days)
        try:
            names = os.listdir(self.log_dir)
        except OSError:
            return
        for name in names:
            m = _DATED_FILE_RE.match(name)
            if not m:
                continue
            try:
                day = date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                continue
            if day < cutoff:
                try:
                    (self.log_dir / name).unlink()
                except OSError:
                    pass


_writers: dict[str, LogWriter] = {}
_writers_lock = threading.Lock()


def get_writer(log_dir: Optional[Path] = None, retention_days: Optional[int] = None) -> LogWriter:
    """Shared writer per log directory."""
    log_dir = Path(log_dir) if log_dir else get_log_dir()
    if retention_days is None:
        try:
            retention_days = int(os.getenv("LEXLINK_LOG_RETENTION_DAYS", "30"))
        except ValueError:
            retention_days = 30
    key = str(log_dir)
    with _writers_lock:
        w = _writers.get(key)
        if w is None:
            w = _writers[key] = LogWriter(log_dir, retention_days)
        return w


def flush_all() -> None:
    """Flush every writer (shutdown / tests)."""
    with _writers_lock:
        writers = list(_writers.values())
    for w in writers:
        w.flush()


atexit.register(flush_all)


# ---------------------------------------------------------------------------
# Parsing and entry building
# ---------------------------------------------------------------------------

def _is_sensitive_key(key: Any) -> bool:
    k = str(key).strip().lower()
    return k in _SENSITIVE_KEYS or any(sub in k for sub in _SENSITIVE_SUBSTRINGS)


def _redact_values(obj: Any) -> Any:
    """Redact OC in strings and drop oc/token/authorization-like keys, recursively."""
    if isinstance(obj, str):
        stripped = obj.lstrip()
        if stripped[:1] in ("{", "["):  # JSON embedded in a string (MCP text content)
            try:
                parsed = json.loads(obj)
            except ValueError:
                parsed = None
            if isinstance(parsed, (dict, list)):
                return json.dumps(_redact_values(parsed), ensure_ascii=False)
        return redact_oc(obj)
    if isinstance(obj, dict):
        return {
            k: _redact_values(v) for k, v in obj.items() if not _is_sensitive_key(k)
        }
    if isinstance(obj, list):
        return [_redact_values(v) for v in obj]
    return obj


def _parse_request(body: bytes) -> Optional[dict]:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(data, list):
        data = next((d for d in data if isinstance(d, dict)), None)
    return data if isinstance(data, dict) else None


def _parse_response_messages(body: bytes, content_type: str) -> list[dict]:
    """JSON-RPC messages from a plain JSON or SSE response capture."""
    text = body.decode("utf-8", errors="replace")
    msgs: list[Any] = []
    if "text/event-stream" in content_type or text.lstrip().startswith(("event:", "data:", "id:")):
        for block in re.split(r"\r?\n\r?\n", text):
            data_lines = [
                ln[5:].lstrip() for ln in block.splitlines() if ln.startswith("data:")
            ]
            if not data_lines:
                continue
            try:
                msgs.append(json.loads("\n".join(data_lines)))
            except ValueError:
                pass
    else:
        try:
            msgs.append(json.loads(text))
        except ValueError:
            pass
    flat: list[dict] = []
    for m in msgs:
        flat.extend(m if isinstance(m, list) else [m])
    return [m for m in flat if isinstance(m, dict)]


def _tool_payload(result: dict) -> Optional[dict]:
    """The LexLink tool response dict inside an MCP tools/call result."""
    sc = result.get("structuredContent")
    if isinstance(sc, dict):
        return sc.get("result") if isinstance(sc.get("result"), dict) else sc
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            try:
                parsed = json.loads(item.get("text", ""))
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def build_entry(
    *,
    req_body: bytes,
    resp_body: bytes,
    content_type: str,
    http_method: str,
    http_status: int,
    response_bytes: int,
    duration_ms: float,
    token_id: str,
    client_ip: Optional[str],
    truncated_capture: bool,
    log_bodies: bool,
    tool_schemas: Optional[dict] = None,
) -> Optional[dict]:
    """Build one log entry, or None if this request should not be logged.

    ``tool_schemas`` maps registered tool name -> iterable of declared argument
    names. Client-controlled strings (method, tool name, argument keys) are only
    logged in default mode when they match these known values.
    """
    tool_schemas = tool_schemas or {}
    rpc_id = None
    method = None
    tool_name = None
    arguments: Any = None
    if http_method == "POST":
        req = _parse_request(req_body)
        if req is not None:
            method = req.get("method")
            rpc_id = req.get("id")
            params = req.get("params")
            if method == "tools/call" and isinstance(params, dict):
                tool_name = params.get("name")
                arguments = params.get("arguments")
        else:
            m = re.search(rb'"method"\s*:\s*"([^"]+)"', req_body)
            method = m.group(1).decode("utf-8", "replace") if m else None
        if not isinstance(method, str) or not method:
            return None
        if method not in KNOWN_METHODS:
            method = UNKNOWN
    elif http_method == "GET":
        method = "GET"
    else:
        return None

    error = None
    result = None
    for msg in _parse_response_messages(resp_body, content_type):
        if "result" not in msg and "error" not in msg:
            continue
        if rpc_id is not None and msg.get("id") != rpc_id and msg.get("id") is not None:
            continue
        result, error = msg.get("result"), msg.get("error")
        break

    is_error = http_status >= 400 or bool(error)
    error_code: Optional[str] = None
    payload = None
    if isinstance(error, dict) and error.get("code") is not None:
        error_code = str(error["code"])
    if isinstance(result, dict):
        if result.get("isError"):
            is_error = True
        payload = _tool_payload(result)
        if payload is not None:
            if payload.get("status") == "error":
                is_error = True
            if payload.get("error_code"):
                error_code = str(payload["error_code"])
    if error_code is None and resp_body and method == "tools/call":
        m = _RESPONSE_KEY_RE.search(resp_body.decode("utf-8", errors="replace"))
        if m:
            error_code, is_error = m.group(1), True

    arg_keys: Optional[list] = None
    unknown_arg_keys: Optional[int] = None
    if method == "tools/call":
        known_tool = isinstance(tool_name, str) and tool_name in tool_schemas
        declared = set(tool_schemas[tool_name]) if known_tool else set()
        if not known_tool:
            tool_name = UNKNOWN
        if isinstance(arguments, dict):
            arg_keys = sorted(k for k in arguments if isinstance(k, str) and k in declared)
            unknown_arg_keys = len(arguments) - len(arg_keys) or None
    else:
        tool_name = None

    entry: dict = {
        "timestamp": datetime.now().isoformat(),
        "token_id": token_id,
        "method": method,
        "tool_name": tool_name,
        "arguments_keys": arg_keys,
        "unknown_arg_keys": unknown_arg_keys,
        "status": "error" if is_error else "ok",
        "error_code": error_code,
        "http_status": http_status,
        "response_bytes": response_bytes,
        "duration_ms": round(duration_ms, 2),
        "client_ip": client_ip,
        "truncated_capture": True if truncated_capture else None,
    }
    if log_bodies:
        if isinstance(arguments, dict):
            entry["arguments"] = _redact_values(arguments)
        if result is not None:
            entry["result"] = _redact_values(result)
        elif error is not None:
            entry["result"] = _redact_values(error)
    return {k: v for k, v in entry.items() if v is not None}


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------

class LoggingMiddleware:
    """Pure ASGI logger: forwards messages untouched, keeps capped copies."""

    def __init__(
        self,
        app,
        writer: Optional[LogWriter] = None,
        log_bodies: Optional[bool] = None,
        capture_max_bytes: Optional[int] = None,
        trusted_proxies: Optional[frozenset] = None,
        tool_schemas: Optional[dict] = None,
    ):
        self.app = app
        self.tool_schemas = tool_schemas or {}
        self.writer = writer if writer is not None else get_writer()
        self.log_bodies = (
            os.getenv("LEXLINK_LOG_BODIES", "").strip().lower() == "true"
            if log_bodies is None else log_bodies
        )
        if capture_max_bytes is None:
            try:
                capture_max_bytes = int(os.getenv("LEXLINK_LOG_CAPTURE_MAX_BYTES", "1048576"))
            except ValueError:
                capture_max_bytes = 1048576
        self.capture_max = capture_max_bytes
        if trusted_proxies is None:
            trusted_proxies = frozenset(
                p.strip() for p in os.getenv("LEXLINK_TRUSTED_PROXIES", "").split(",") if p.strip()
            )
        self.trusted_proxies = trusted_proxies

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        http_method = scope.get("method", "")
        req_buf = bytearray()
        resp_buf = bytearray()
        info = {"status": 500, "ctype": "", "total": 0, "truncated": False}

        async def wrapped_receive():
            message = await receive()
            if message["type"] == "http.request" and http_method == "POST":
                self._capture(req_buf, message.get("body", b""), info)
            return message

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                info["status"] = message["status"]
                for k, v in message.get("headers", []):
                    if k.lower() == b"content-type":
                        info["ctype"] = v.decode("latin-1").lower()
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                info["total"] += len(body)
                self._capture(resp_buf, body, info)
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        finally:
            try:
                entry = build_entry(
                    req_body=bytes(req_buf),
                    resp_body=bytes(resp_buf),
                    content_type=info["ctype"],
                    http_method=http_method,
                    http_status=info["status"],
                    response_bytes=info["total"],
                    duration_ms=(time.perf_counter() - start) * 1000,
                    token_id=scope.get("state", {}).get("token_id", NO_AUTH_TOKEN_ID),
                    client_ip=resolve_client_ip(scope, self.trusted_proxies),
                    truncated_capture=info["truncated"],
                    log_bodies=self.log_bodies,
                    tool_schemas=self.tool_schemas,
                )
                if entry is not None:
                    self.writer.write(entry)
            except Exception as e:  # logging must never break a request
                logger.warning("log build failed: %s", type(e).__name__)

    def _capture(self, buf: bytearray, chunk: bytes, info: dict) -> None:
        room = self.capture_max - len(buf)
        if len(chunk) > room:
            info["truncated"] = True
        if room > 0:
            buf.extend(chunk[:room])
