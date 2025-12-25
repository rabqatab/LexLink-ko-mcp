"""
PlayMCP traffic logger with dashboard-compatible format.

Captures MCP request/response pairs and logs in a format compatible
with the Smithery dashboard for filtering and analysis.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs" / "playmcp"


def ensure_log_dir():
    """Create log directory if not exists."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_log_file() -> Path:
    """Get today's log file path."""
    ensure_log_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"{today}.jsonl"


def generate_request_id() -> str:
    """Generate unique request ID."""
    return str(uuid.uuid4())[:8]


def log_raw(
    request_id: str,
    phase: str,  # "request" or "response"
    data: Any,
    extra: Optional[dict] = None
):
    """
    Log raw data to JSONL file (legacy format).

    Args:
        request_id: Unique ID for correlating request/response
        phase: "request" or "response"
        data: Raw data (will be JSON serialized)
        extra: Additional metadata
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "request_id": request_id,
        "phase": phase,
        "data": data,
        **(extra or {})
    }

    try:
        log_file = get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        # Don't crash on logging errors
        print(f"[RAW_LOGGER] Error writing log: {e}")


def log_mcp_call(
    request_id: str,
    timestamp: str,
    duration_ms: float,
    req_data: Optional[dict],
    resp_data: Any,
    headers: dict,
    status_code: int,
    client_ip: Optional[str] = None,
    response_type: Optional[str] = None,
):
    """
    Log MCP call in dashboard-compatible format (merged request+response).

    This is the primary logging function for PlayMCP traffic.
    Format matches the Smithery dashboard schema.
    """
    if not req_data or not isinstance(req_data, dict):
        return  # Skip non-JSON requests

    method = req_data.get('method')
    if not method:
        return

    # Extract result from SSE events
    result = None
    error = None
    is_error = False

    if resp_data and isinstance(resp_data, dict):
        sse_events = resp_data.get('_sse_events', [])
        if sse_events:
            event_data = sse_events[0].get('data', {})
            result = event_data.get('result')
            error = event_data.get('error')
            if error:
                is_error = True

    # Check result.isError flag
    if result and isinstance(result, dict) and result.get('isError'):
        is_error = True

    # Determine status
    if status_code >= 400 or is_error or error:
        status = 'error'
    else:
        status = 'success'

    # Extract client info
    params = req_data.get('params', {})
    client_info = params.get('clientInfo', {})
    client = client_info.get('name') or headers.get('user-agent', '').split('/')[0]
    client_version = client_info.get('version')
    protocol_version = params.get('protocolVersion')

    # Extract tool info
    tool_name = None
    arguments = None
    if method == 'tools/call':
        tool_name = params.get('name')
        arguments = params.get('arguments')

    # Build dashboard entry
    entry = {
        # Identifiers
        'rpc_id': str(req_data.get('id', request_id)),
        'request_id': request_id,
        'session_id': headers.get('mcp-session-id'),

        # Timing
        'timestamp': timestamp,
        'duration_ms': round(duration_ms, 2),

        # Request info
        'method': method,
        'tool_name': tool_name,
        'params': {
            'arguments': arguments,
            'clientInfo': client_info if client_info else None,
            'protocolVersion': protocol_version,
        },

        # Client info
        'client': client,
        'client_version': client_version,
        'protocol_version': protocol_version,
        'client_ip': headers.get('x-forwarded-for') or client_ip,
        'oc': headers.get('oc') or headers.get('OC'),

        # Response info
        'status': status,
        'status_code': status_code,
        'result': result,
        'error': error,

        # Metadata
        'response_type': response_type,
    }

    # Clean up None values
    entry = {k: v for k, v in entry.items() if v is not None}

    # Also clean params
    if 'params' in entry:
        entry['params'] = {k: v for k, v in entry['params'].items() if v is not None}

    try:
        log_file = get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[MCP_LOGGER] Error writing log: {e}")
