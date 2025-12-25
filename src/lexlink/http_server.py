"""
HTTP Server Entry Point for Kakao PlayMCP and similar platforms.

This module provides HTTP/SSE transport for the LexLink MCP server,
enabling deployment on platforms that require an HTTP endpoint.

Transport Options:
    - Streamable HTTP (/mcp): Recommended for PlayMCP and modern clients
    - SSE (/sse): Legacy transport, may not work with some platforms

Authentication:
    PlayMCP passes user's OC via HTTP header. This server extracts the
    "OC" header and uses it for law.go.kr API calls.

Usage:
    # Run with Streamable HTTP transport (recommended for PlayMCP)
    TRANSPORT=http uv run serve

    # Run with SSE transport (legacy)
    uv run serve

    # With fallback OC (used if no header provided)
    OC=your_oc TRANSPORT=http uv run serve

Endpoints:
    - HTTP (Streamable): http://your-host:8000/mcp  <- Use this for PlayMCP
    - SSE (Legacy): http://your-host:8000/sse

PlayMCP Registration:
    - 인증 방식: Key/Token 인증
    - Header 이름: OC
    - MCP Endpoint: http://your-domain/mcp (domain required, not raw IP)
    - Use sslip.io for IP-to-domain: http://1-2-3-4.sslip.io/mcp

Note:
    Kakao PlayMCP requires:
    1. Domain name (not raw IP address)
    2. Streamable HTTP transport (TRANSPORT=http)
    3. Port 80/443 (use Nginx as reverse proxy)
"""

import os
import json
import logging
import contextvars
import time
from typing import Optional

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Mount

from mcp.server.fastmcp import FastMCP

from .config import LexLinkConfig
from .server import create_server
from .raw_logger import log_raw, generate_request_id

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Context variable to store OC from HTTP header (thread-safe for concurrent requests)
_oc_from_header: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'oc_from_header', default=None
)


def get_oc_from_header() -> Optional[str]:
    """Get OC value extracted from HTTP header (for current request context)."""
    return _oc_from_header.get()


class OCHeaderMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract OC from HTTP headers for PlayMCP authentication.

    PlayMCP sends the user's OC via custom HTTP header when connecting.
    This middleware extracts it and makes it available to the MCP tools.
    """

    async def dispatch(self, request: Request, call_next):
        # Extract OC from header (PlayMCP Key/Token auth)
        oc_value = request.headers.get("OC") or request.headers.get("oc")

        if oc_value:
            logger.debug(f"Received OC from header: {oc_value[:4]}***")
            # Store in context variable (thread-safe)
            _oc_from_header.set(oc_value)
            # Also set environment variable as fallback for tools
            os.environ["OC"] = oc_value

        response = await call_next(request)
        return response


class RawLoggingMiddleware(BaseHTTPMiddleware):
    """
    Crude raw logger for capturing all MCP traffic.

    Logs request body, response body, headers, timing - everything.
    For analysis to determine precise log schema later.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = generate_request_id()
        start_time = time.time()

        # Capture request
        try:
            body_bytes = await request.body()
            try:
                body_json = json.loads(body_bytes) if body_bytes else None
            except json.JSONDecodeError:
                body_json = body_bytes.decode("utf-8", errors="replace") if body_bytes else None
        except Exception as e:
            body_json = f"[ERROR reading body: {e}]"

        # Log request
        log_raw(
            request_id=request_id,
            phase="request",
            data=body_json,
            extra={
                "method": request.method,
                "path": str(request.url.path),
                "query": str(request.url.query),
                "headers": dict(request.headers),
                "client": request.client.host if request.client else None,
            }
        )

        # Get response
        response = await call_next(request)
        elapsed_ms = (time.time() - start_time) * 1000

        # Capture response body (tricky for streaming)
        if isinstance(response, StreamingResponse):
            # For streaming responses, collect all chunks
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)

            response_body = b"".join(chunks)
            try:
                response_json = json.loads(response_body) if response_body else None
            except json.JSONDecodeError:
                response_json = response_body.decode("utf-8", errors="replace") if response_body else None

            # Log response
            log_raw(
                request_id=request_id,
                phase="response",
                data=response_json,
                extra={
                    "status_code": response.status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "headers": dict(response.headers),
                }
            )

            # Return new response with same body
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        else:
            # Non-streaming response
            log_raw(
                request_id=request_id,
                phase="response",
                data="[non-streaming response]",
                extra={
                    "status_code": response.status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                }
            )
            return response


def get_config_from_env() -> Optional[LexLinkConfig]:
    """Create config from environment variables."""
    oc = os.getenv("OC")
    if oc:
        return LexLinkConfig(
            oc=oc,
            http_timeout_s=int(os.getenv("LEXLINK_TIMEOUT", "60"))
        )
    return None


def get_fastmcp_server() -> FastMCP:
    """
    Get the underlying FastMCP server instance.

    The create_server() returns a SmitheryFastMCP wrapper, but we need
    the underlying FastMCP for HTTP transport methods.
    """
    config = get_config_from_env()
    smithery_server = create_server(config)

    # Access the underlying FastMCP from SmitheryFastMCP wrapper
    if hasattr(smithery_server, '_fastmcp'):
        return smithery_server._fastmcp
    else:
        # Fallback: if it's already a FastMCP
        return smithery_server


# Create server instance
_server: FastMCP = get_fastmcp_server()

# Get the raw SSE app from FastMCP
_sse_app = _server.sse_app()

# Wrap with our middleware for OC header extraction and raw logging
app = Starlette(
    routes=[Mount("/", app=_sse_app)],
    middleware=[
        Middleware(OCHeaderMiddleware),
        Middleware(RawLoggingMiddleware),
    ]
)


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
    logger.info("PlayMCP Auth: Send OC via 'OC' HTTP header")

    uvicorn.run(app, host=host, port=port)


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
    from contextlib import asynccontextmanager

    logger.info(f"Starting LexLink MCP server (HTTP) on {host}:{port}")
    logger.info(f"Endpoint: http://{host}:{port}/mcp")
    logger.info("PlayMCP Auth: Send OC via 'OC' HTTP header")

    # Create a fresh server with stateless_http=True for proper HTTP transport
    config = get_config_from_env()
    from .server import create_server
    http_server = create_server(config)

    # Access the underlying FastMCP
    if hasattr(http_server, '_fastmcp'):
        fastmcp = http_server._fastmcp
    else:
        fastmcp = http_server

    # Get the streamable HTTP app with proper configuration
    _http_app = fastmcp.streamable_http_app()

    # Create lifespan that properly initializes the session manager
    @asynccontextmanager
    async def lifespan(app):
        async with fastmcp.session_manager.run():
            yield

    http_app = Starlette(
        routes=[Mount("/", app=_http_app)],
        middleware=[
            Middleware(OCHeaderMiddleware),
            Middleware(RawLoggingMiddleware),
        ],
        lifespan=lifespan
    )
    uvicorn.run(http_app, host=host, port=port)


def main():
    """
    Main entry point for the HTTP/SSE server.

    Environment variables:
        PORT: Port to listen on (default: 8000)
        HOST: Host to bind to (default: 0.0.0.0)
        TRANSPORT: Transport type - "sse" or "http" (default: sse)
        OC: Fallback OC if not provided via header
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
