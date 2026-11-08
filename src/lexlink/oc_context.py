"""
Per-request OC (HTTP mode, opt-in).

With ``LEXLINK_ACCEPT_OC_HEADER=true`` a ``tools/call`` whose HTTP request carries a valid
``X-LexLink-OC`` header uses that OC for every law.go.kr request made during the call; otherwise
the server env ``OC`` is used. The tool argument ``oc`` stays ignored in HTTP mode.

The value travels in a contextvar set by the per-call wrapper in ``_helpers`` (the MCP session runs
handlers in its own tasks, so middleware contextvars do not reach the tools; sync tools run in
anyio worker threads and ``run_coroutine_sync`` threads, both of which copy the context). The value
is never put in cache keys, log lines, results or error text: ``client.redact_oc`` masks the
env OC and the current request OC everywhere.
"""

import os
import re
from contextvars import ContextVar
from typing import Any, Mapping, Optional

OC_HEADER = "x-lexlink-oc"
_OC_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")

_request_oc: ContextVar[Optional[str]] = ContextVar("lexlink_request_oc", default=None)
_header_invalid: ContextVar[bool] = ContextVar("lexlink_oc_header_invalid", default=False)


def accept_oc_header() -> bool:
    return os.getenv("LEXLINK_ACCEPT_OC_HEADER", "").strip().lower() == "true"


def parse_oc_header(headers: Optional[Mapping[str, Any]]) -> tuple[Optional[str], bool]:
    """(valid OC or None, header_present_but_invalid). Never raises; honours the env flag.

    ``headers`` is a Starlette ``Headers`` (``getlist``) or a dict whose value may be a list.
    More than one ``X-LexLink-OC`` header is invalid (first-wins vs last-wins would differ
    between the tool path and the logger).
    """
    if headers is None or not accept_oc_header():
        return None, False
    try:
        if hasattr(headers, "getlist"):
            values = list(headers.getlist(OC_HEADER))
        else:
            raw = headers.get(OC_HEADER)
            values = [] if raw is None else (list(raw) if isinstance(raw, (list, tuple)) else [raw])
    except Exception:
        return None, False
    if not values:
        return None, False
    if len(values) > 1:
        return None, True
    value = values[0].strip()
    if _OC_RE.fullmatch(value):
        return value, False
    return None, True


def begin_request_oc(headers: Optional[Mapping[str, Any]]) -> Any:
    """Install the request OC for the current context; returns a token for ``end_request_oc``."""
    oc, invalid = parse_oc_header(headers)
    return (_request_oc.set(oc), _header_invalid.set(invalid))


def end_request_oc(token: Any) -> None:
    _request_oc.reset(token[0])
    _header_invalid.reset(token[1])


def get_request_oc() -> Optional[str]:
    return _request_oc.get()


def request_oc_invalid() -> bool:
    return _header_invalid.get()


def oc_source() -> str:
    """``"header"`` when this call uses a per-request OC, else ``"server"`` (never the value)."""
    return "header" if _request_oc.get() else "server"


def secret_ocs() -> list[str]:
    """Credentials to mask in the current context: server env OC and the request OC."""
    out = []
    for v in (os.environ.get("OC"), _request_oc.get()):
        v = (v or "").strip()
        if v and v not in out:
            out.append(v)
    return out
