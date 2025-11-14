"""
MCP Protocol Client for Testing.

This client simulates how Smithery calls the LexLink MCP server,
making JSON-RPC requests over HTTP.
"""

import httpx
import json
import time
from typing import Optional, Dict, Any, List
from datetime import datetime


class MCPClient:
    """Client for MCP JSON-RPC protocol over HTTP."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8081",
        session_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize MCP client.

        Args:
            base_url: Base URL for MCP server
            session_config: Session configuration (e.g., {"oc": "value"})
        """
        self.base_url = base_url
        self.session_config = session_config or {}
        self.session_id: Optional[str] = None
        self.request_counter = 0

        # Build URL with session config as query params
        query_params = "&".join([f"{k}={v}" for k, v in self.session_config.items()])
        self.mcp_url = f"{base_url}/mcp"
        if query_params:
            self.mcp_url += f"?{query_params}"

        self.client = httpx.Client(timeout=30.0)
        self.call_log: List[Dict[str, Any]] = []

    def _next_request_id(self) -> int:
        """Generate next request ID."""
        self.request_counter += 1
        return self.request_counter

    def _parse_sse_response(self, text: str) -> Dict[str, Any]:
        """
        Parse Server-Sent Events (SSE) response.

        SSE format:
            event: message
            data: {"jsonrpc":"2.0",...}

        Args:
            text: Raw SSE response text

        Returns:
            Parsed JSON-RPC response
        """
        lines = text.strip().split('\n')
        for line in lines:
            if line.startswith('data: '):
                json_str = line[6:]  # Remove 'data: ' prefix
                return json.loads(json_str)
        # If no data line found, try parsing as plain JSON
        return json.loads(text)

    def _log_call(
        self,
        method: str,
        params: Dict[str, Any],
        response: Dict[str, Any],
        elapsed_ms: int
    ):
        """Log MCP call for debugging."""
        self.call_log.append({
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "params": params,
            "response": response,
            "elapsed_ms": elapsed_ms,
            "session_id": self.session_id,
        })

    def initialize(self) -> Dict[str, Any]:
        """
        Initialize MCP session (JSON-RPC initialize method).

        Returns:
            Server capabilities and session info
        """
        request = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {
                    "name": "lexlink-test-client",
                    "version": "1.0.0"
                }
            }
        }

        start_time = time.time()
        response = self.client.post(
            self.mcp_url,
            json=request,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        response.raise_for_status()

        # Parse SSE response (Server-Sent Events format)
        result = self._parse_sse_response(response.text)

        # Extract session ID from headers
        self.session_id = response.headers.get("mcp-session-id")

        self._log_call("initialize", request["params"], result, elapsed_ms)

        return result

    def list_tools(self) -> Dict[str, Any]:
        """
        List available MCP tools.

        Returns:
            List of tools with their schemas
        """
        request = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/list",
            "params": {}
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        start_time = time.time()
        response = self.client.post(
            self.mcp_url,
            json=request,
            headers=headers
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        response.raise_for_status()
        result = self._parse_sse_response(response.text)

        self._log_call("tools/list", request["params"], result, elapsed_ms)

        return result

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool to call (e.g., "eflaw_search")
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        request = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        start_time = time.time()
        response = self.client.post(
            self.mcp_url,
            json=request,
            headers=headers
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        response.raise_for_status()
        result = self._parse_sse_response(response.text)

        self._log_call(
            f"tools/call:{tool_name}",
            {"tool": tool_name, "arguments": arguments},
            result,
            elapsed_ms
        )

        return result

    def get_call_log(self) -> List[Dict[str, Any]]:
        """
        Get full call log for this session.

        Returns:
            List of all MCP calls made
        """
        return self.call_log

    def close(self):
        """Close HTTP client."""
        self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
