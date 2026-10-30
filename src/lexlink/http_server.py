"""
HTTP Server Entry Point for Kakao PlayMCP and similar platforms.

This module provides HTTP/SSE transport for the LexLink MCP server,
enabling deployment on platforms that require an HTTP endpoint.

Transport Options:
    - Streamable HTTP (/mcp): Recommended for PlayMCP and modern clients
    - SSE (/sse): Legacy transport, may not work with some platforms

Authentication:
    Clients authenticate with ``Authorization: Bearer <token>``; tokens come
    from LEXLINK_AUTH_TOKENS="name:token,...". The server fails closed at
    startup without tokens unless LEXLINK_ALLOW_NO_AUTH=true (PlayMCP no-auth
    registration only). The tool `oc` argument is ignored in HTTP mode.

    The server uses its own OC from the environment variable (OC=...).
    law.go.kr validates OC + requesting IP as a pair, so the server's OC
    must have the server's public IP registered at open.law.go.kr.

Hardening (pure ASGI, order Auth > Logging > RateLimit > SessionBinding > app):
    - Host/Origin validation via LEXLINK_ALLOWED_HOSTS / LEXLINK_ALLOWED_ORIGINS
    - Per-token concurrency and per-minute limits (single process only)
    - MCP sessions bound to the creating token (LEXLINK_MAX_SESSIONS)
    - Privacy-preserving JSONL logging with retention (see raw_logger.py)
    Run a single uvicorn worker. See docs/OPERATIONS.md for all variables.

Usage:
    # Run with Streamable HTTP transport (recommended for PlayMCP)
    OC=your_oc LEXLINK_AUTH_TOKENS=name:token TRANSPORT=http uv run serve

    # Or as an ASGI factory (single worker)
    uvicorn --factory --no-proxy-headers lexlink.http_server:create_app

    # Run with SSE transport (legacy)
    OC=your_oc uv run serve

Endpoints:
    - HTTP (Streamable): http://your-host:8000/mcp  <- Use this for PlayMCP
    - SSE (Legacy): http://your-host:8000/sse

PlayMCP Registration:
    - 인증 방식: 인증 없음 (requires LEXLINK_ALLOW_NO_AUTH=true)
    - MCP Endpoint: http://your-domain/mcp (domain required, not raw IP)
    - Use sslip.io for IP-to-domain: http://1-2-3-4.sslip.io/mcp

Note:
    Kakao PlayMCP requires:
    1. Domain name (not raw IP address)
    2. Streamable HTTP transport (TRANSPORT=http)
    3. Port 80/443 (use Nginx as reverse proxy)
"""

import logging
import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Mount

from .http_security import (
    BearerAuthMiddleware,
    RateLimitMiddleware,
    SessionBindingMiddleware,
    build_transport_security,
    load_auth_tokens,
)
from .params import set_ignore_oc_override
from .raw_logger import LoggingMiddleware, flush_all
from .server import create_server

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app(transport: str = "http"):
    """
    Build the ASGI app: Auth > Logging > RateLimit > SessionBinding > FastMCP.

    Owns the single create_server() call and the session manager lifespan.
    Raises RuntimeError at startup if authentication is not configured
    (see http_security.load_auth_tokens). Also usable as a uvicorn factory:
    ``uvicorn --factory lexlink.http_server:create_app`` (single worker only:
    rate limits and log writer are in-process).

    Note: the factory serves plain HTTP only (no TLS); put a reverse proxy in
    front. The ``TRANSPORT``/``HOST``/``PORT`` env vars are ignored by the
    factory (it always serves Streamable HTTP; use uvicorn flags for the
    rest). Run uvicorn with ``--no-proxy-headers`` so that
    LEXLINK_TRUSTED_PROXIES is the only X-Forwarded-For authority.

    Side effect: the HTTP-mode "ignore the tool-argument oc" switch
    (``params.set_ignore_oc_override(True)``) is per-process, not per-app:
    after create_app() every tool call in this process uses the server's OC,
    including other servers or stdio sessions embedded in the same process.

    Args:
        transport: "http" (Streamable HTTP, /mcp) or "sse" (legacy, /sse)
    """
    tokens = load_auth_tokens()  # fail closed before anything else
    set_ignore_oc_override(True)  # HTTP callers must not choose the OC

    if transport == "sse":
        logger.warning(
            "TRANSPORT=sse: results travel on the GET /sse stream, so per-request "
            "log status/error_code and the concurrency limit cannot observe tool "
            "results (POST /messages returns 202 immediately). Prefer TRANSPORT=http. "
            "See docs/OPERATIONS.md."
        )
    fastmcp = create_server(transport_security=build_transport_security())
    tool_schemas = {
        t.name: set((t.parameters or {}).get("properties", {}))
        for t in fastmcp._tool_manager.list_tools()
    }
    if transport == "sse":
        inner = fastmcp.sse_app()
    else:
        inner = fastmcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        try:
            if transport == "sse":
                yield
            else:
                async with fastmcp.session_manager.run():
                    yield
        finally:
            flush_all()

    starlette_app = Starlette(routes=[Mount("/", app=inner)], lifespan=lifespan)
    app = SessionBindingMiddleware(starlette_app)
    app = RateLimitMiddleware(app)
    app = LoggingMiddleware(app, tool_schemas=tool_schemas)
    return BearerAuthMiddleware(app, tokens)


def run_sse_server(host: str = "0.0.0.0", port: int = 8000):
    """
    Run the MCP server with SSE transport.

    This creates endpoints at:
    - /sse - SSE endpoint for MCP protocol

    Args:
        host: Host to bind to (default: 0.0.0.0 for all interfaces)
        port: Port to listen on (default: 8000)
    """
    import uvicorn

    logger.info(f"Starting LexLink MCP server (SSE) on {host}:{port}")
    logger.info(f"Endpoint: http://{host}:{port}/sse")

    uvicorn.run(create_app("sse"), host=host, port=port, proxy_headers=False)


def run_http_server(host: str = "0.0.0.0", port: int = 8000):
    """
    Run the MCP server with Streamable HTTP transport.

    This creates endpoints at:
    - /mcp - Streamable HTTP endpoint for MCP protocol

    Args:
        host: Host to bind to (default: 0.0.0.0 for all interfaces)
        port: Port to listen on (default: 8000)
    """
    import uvicorn

    logger.info(f"Starting LexLink MCP server (HTTP) on {host}:{port}")
    logger.info(f"Endpoint: http://{host}:{port}/mcp")

    uvicorn.run(create_app("http"), host=host, port=port, proxy_headers=False)


def main():
    """
    Main entry point for the HTTP/SSE server.

    Environment variables:
        PORT: Port to listen on (default: 8000)
        HOST: Host to bind to (default: 0.0.0.0)
        TRANSPORT: Transport type - "sse" or "http" (default: sse)
        OC: Server's OC for law.go.kr API (must have server IP registered)
        LEXLINK_AUTH_TOKENS / LEXLINK_ALLOW_NO_AUTH: required, see docs/OPERATIONS.md
    """
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    transport = os.getenv("TRANSPORT", "sse")  # "sse" or "http"

    if transport == "http":
        run_http_server(host=host, port=port)
    else:
        run_sse_server(host=host, port=port)


if __name__ == "__main__":
    main()
