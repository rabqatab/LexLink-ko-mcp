"""
Per-tool-call count of HTTP requests sent to law.go.kr (for the HTTP request log).

A contextvar set in the tool-call wrapper (``_helpers.install_threaded_tool_calls``) reaches
``client.py`` from the worker threads sync tools run in (``anyio.to_thread.run_sync`` copies
the context) and from ``run_coroutine_sync`` (copies it explicitly); the counter object is
shared by reference. A thread started without copying the context would not be counted. The logging middleware
runs in a different task (the ASGI request), so the finished count is handed over through a
small bounded registry keyed by (MCP session id, JSON-RPC request id), taken by
``LoggingMiddleware`` once the response is complete. A tool answered from cache sends
nothing and records 0.
"""

import threading
from collections import OrderedDict
from contextvars import ContextVar
from typing import Any, Optional

_counter: ContextVar[Optional[list]] = ContextVar("lexlink_upstream_counter", default=None)

_MAX_PENDING = 4096
_pending: "OrderedDict[tuple, int]" = OrderedDict()
_lock = threading.Lock()


def start_counter() -> Any:
    """Install a fresh counter in the current context; returns the reset token."""
    return _counter.set([0])


def end_counter(token: Any) -> int:
    """Remove the counter installed by ``start_counter`` and return its count."""
    counter = _counter.get()
    _counter.reset(token)
    return counter[0] if counter else 0


def count_upstream_call() -> None:
    """Count one HTTP request to law.go.kr (no-op outside a counted tool call)."""
    counter = _counter.get()
    if counter is not None:
        counter[0] += 1  # one tool call is sequential, so no lock is needed


def record(session_id: Optional[str], request_id: Any, count: int) -> None:
    """Store a finished call's count. A key already pending (duplicate in-flight id) is
    ambiguous, so both counts are dropped rather than attributed to the wrong call."""
    if not session_id or request_id is None:
        return
    key = (session_id, request_id)
    with _lock:
        if key in _pending:
            del _pending[key]
            return
        _pending[key] = count
        while len(_pending) > _MAX_PENDING:
            _pending.popitem(last=False)


def discard(session_id: Optional[str], request_id: Any) -> None:
    """Forget a stale count (e.g. a cancelled call) when a new call with the same id starts."""
    take(session_id, request_id)


def take(session_id: Optional[str], request_id: Any) -> Optional[int]:
    if not session_id or request_id is None:
        return None
    with _lock:
        return _pending.pop((session_id, request_id), None)
