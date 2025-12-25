"""
Log processor for transforming raw PlayMCP logs to dashboard-compatible format.

Merges request/response pairs and extracts fields needed for dashboard filtering.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def process_raw_logs(input_path: Path, output_path: Optional[Path] = None) -> list[dict]:
    """
    Process raw JSONL logs into dashboard-compatible format.

    Args:
        input_path: Path to raw JSONL log file
        output_path: Optional path to write processed logs

    Returns:
        List of processed log entries
    """
    # Read raw logs
    raw_logs = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                raw_logs.append(json.loads(line))

    # Group by request_id
    requests = {}
    responses = {}

    for log in raw_logs:
        req_id = log.get('request_id')
        if log.get('phase') == 'request':
            requests[req_id] = log
        elif log.get('phase') == 'response':
            responses[req_id] = log

    # Merge and transform
    processed = []
    for req_id, req in requests.items():
        resp = responses.get(req_id, {})
        entry = transform_to_dashboard_format(req_id, req, resp)
        if entry:
            processed.append(entry)

    # Sort by timestamp
    processed.sort(key=lambda x: x.get('timestamp', ''))

    # Write output if path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            for entry in processed:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')

    return processed


def transform_to_dashboard_format(req_id: str, req: dict, resp: dict) -> Optional[dict]:
    """
    Transform a request/response pair into dashboard-compatible format.

    Dashboard schema:
    - rpc_id: Unique RPC identifier (from jsonrpc id)
    - timestamp: Request timestamp
    - method: RPC method (initialize, tools/call, tools/list, etc.)
    - tool_name: Tool name (for tools/call)
    - client: Client name (PlayMCP, etc.)
    - client_version: Client version
    - protocol_version: MCP protocol version
    - oc: User API key (masked)
    - session_id: MCP session ID
    - client_ip: Client IP address
    - status: success/error
    - status_code: HTTP status code
    - duration_ms: Response time
    - params: Request parameters
    - result: Response result
    - error: Error details if any
    """
    req_data = req.get('data')
    if not req_data or not isinstance(req_data, dict):
        # Skip non-JSON requests (GET /, etc.)
        return None

    method = req_data.get('method')
    if not method:
        return None

    # Extract request headers
    headers = req.get('headers', {})

    # Extract response data
    resp_data = resp.get('data')
    result = None
    error = None
    is_error = False

    if resp_data and isinstance(resp_data, dict):
        # Parse SSE events
        sse_events = resp_data.get('_sse_events', [])
        if sse_events:
            event_data = sse_events[0].get('data', {})
            result = event_data.get('result')
            error = event_data.get('error')
            if error:
                is_error = True

    # Check for result.isError flag
    if result and isinstance(result, dict):
        if result.get('isError'):
            is_error = True

    # Determine status
    status_code = resp.get('status_code', 0)
    if status_code >= 400 or is_error or error:
        status = 'error'
    else:
        status = 'success'

    # Extract client info (from initialize params or headers)
    params = req_data.get('params', {})
    client_info = params.get('clientInfo', {})
    client = client_info.get('name') or headers.get('user-agent', '').split('/')[0]
    client_version = client_info.get('version')
    protocol_version = params.get('protocolVersion')

    # Extract tool info (for tools/call)
    tool_name = None
    arguments = None
    if method == 'tools/call':
        tool_name = params.get('name')
        arguments = params.get('arguments')

    # Build dashboard entry
    entry = {
        # Identifiers
        'rpc_id': str(req_data.get('id', req_id)),
        'request_id': req_id,  # Internal correlation ID
        'session_id': headers.get('mcp-session-id'),

        # Timing
        'timestamp': req.get('timestamp'),
        'duration_ms': resp.get('elapsed_ms', 0),

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
        'client_ip': headers.get('x-forwarded-for') or req.get('client'),
        'oc': headers.get('oc'),

        # Response info
        'status': status,
        'status_code': status_code,
        'result': result,
        'error': error,

        # Metadata
        'response_type': resp.get('response_type'),
    }

    # Clean up None values for cleaner output
    entry = {k: v for k, v in entry.items() if v is not None}

    return entry


def get_empty_result_status(result: Any) -> bool:
    """Check if result is empty/error (yellow circle in dashboard)."""
    if not result:
        return True

    if isinstance(result, dict):
        # Check for totalCnt=0
        if result.get('totalCnt') == 0:
            return True
        # Check for status: error
        if result.get('status') == 'error':
            return True
        # Check for empty content
        content = result.get('content')
        if isinstance(content, list) and len(content) == 0:
            return True
        if isinstance(content, list) and len(content) == 1:
            # Check if content[0] has text with error
            item = content[0]
            if isinstance(item, dict) and item.get('type') == 'text':
                text = item.get('text', '')
                if '"status": "error"' in text or '"totalCnt": 0' in text:
                    return True

    return False


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python log_processor.py <input.jsonl> [output.jsonl]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    processed = process_raw_logs(input_path, output_path)

    print(f"Processed {len(processed)} log entries")

    # Print summary
    methods = {}
    tools = {}
    for entry in processed:
        method = entry.get('method', 'unknown')
        methods[method] = methods.get(method, 0) + 1
        if entry.get('tool_name'):
            tool = entry['tool_name']
            tools[tool] = tools.get(tool, 0) + 1

    print(f"\nMethods: {methods}")
    print(f"Tools: {tools}")

    if not output_path:
        print("\n=== Sample entries ===")
        for entry in processed[:3]:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
