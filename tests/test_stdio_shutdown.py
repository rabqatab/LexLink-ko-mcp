"""Closing stdio while a threaded tool call is still running must exit cleanly."""

import http.server
import json
import os
import subprocess
import sys
import threading
import time

import anyio
import pytest

from lexlink.stdio_server import is_closed_stream_error

pytestmark = pytest.mark.unit


def test_is_closed_stream_error_matches_only_closed_streams():
    assert is_closed_stream_error(anyio.ClosedResourceError())
    assert is_closed_stream_error(anyio.BrokenResourceError())
    nested = ExceptionGroup("g", [ExceptionGroup("g2", [anyio.ClosedResourceError()])]) \
        if sys.version_info >= (3, 11) else None
    if nested is not None:
        assert is_closed_stream_error(nested)
        assert not is_closed_stream_error(ExceptionGroup("g", [anyio.ClosedResourceError(), ValueError("x")]))
    assert not is_closed_stream_error(ValueError("x"))
    assert not is_closed_stream_error(KeyboardInterrupt())


class _SlowHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(2.5)
        body = b'{"LawSearch":{"law":[],"totalCnt":"0"}}'
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass

    def log_message(self, *args):
        pass


def test_stdio_close_during_tool_call_exits_zero_without_traceback():
    upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    env = dict(os.environ, LEXLINK_BASE_URL=f"http://127.0.0.1:{upstream.server_address[1]}", OC="dummy-oc")
    proc = subprocess.Popen([sys.executable, "-m", "lexlink.stdio_server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    def send(message):
        proc.stdin.write((json.dumps(message) + "\n").encode())
        proc.stdin.flush()

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                         "clientInfo": {"name": "t", "version": "1"}}})
        assert json.loads(proc.stdout.readline())["id"] == 1
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "law_search", "arguments": {"query": "민법"}}})
        time.sleep(0.7)  # the tool is now blocked on the slow upstream, in a worker thread
        proc.stdin.close()
        returncode = proc.wait(timeout=30)
        stderr = proc.stderr.read().decode("utf-8", "replace")
    finally:
        if proc.poll() is None:
            proc.kill()
        upstream.shutdown()
    assert "Traceback" not in stderr and "ClosedResourceError" not in stderr, stderr[-1500:]
    assert returncode == 0
