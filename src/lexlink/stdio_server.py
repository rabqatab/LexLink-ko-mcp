"""Stdio transport entry point for LexLink MCP server."""

import anyio

from .server import create_server

_CLOSED_STREAM_ERRORS = (anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream)


def is_closed_stream_error(exc: BaseException) -> bool:
    """True when ``exc`` (or every leaf of an exception group) is a write to a closed stream.

    Tool functions run in worker threads, so a tool can still be running when the client closes
    stdin. Its response is then written to a stream the SDK has already closed and the SDK
    raises ``ClosedResourceError`` out of ``run()`` (inside an ExceptionGroup): a normal
    disconnect, not a failure. Anything else is not matched and still propagates.
    """
    if isinstance(exc, _CLOSED_STREAM_ERRORS):
        return True
    leaves = getattr(exc, "exceptions", None)  # BaseExceptionGroup, without importing it (Python 3.10)
    return bool(leaves) and all(is_closed_stream_error(e) for e in leaves)


def main():
    """Run LexLink MCP server over stdio transport; a client disconnect is a clean exit."""
    try:
        create_server().run()
    except BaseException as exc:  # noqa: BLE001 - re-raised unless it is only a closed stream
        if not is_closed_stream_error(exc):
            raise


if __name__ == "__main__":
    main()
