#!/bin/bash
# LexLink MCP Server - Cloud Run Smoke Test
#
# Verifies the MCP server is working correctly with proper session handling.
# Usage: ./smoke_test.sh [SERVICE_URL]
#
# If SERVICE_URL is not provided, it will be fetched from gcloud.

set -euo pipefail

# Get SERVICE_URL from argument or gcloud
if [ -n "${1:-}" ]; then
  SERVICE_URL="$1"
else
  echo "Fetching SERVICE_URL from gcloud..."
  SERVICE_URL=$(gcloud run services describe lexlink \
    --region=asia-northeast3 \
    --format='value(status.url)')
fi

echo "SERVICE_URL=$SERVICE_URL"
echo ""

ACCEPT_HEADER="Accept: application/json, text/event-stream"

# Step 1: Initialize session
echo ">>> Step 1: Initialize session"
INIT=$(curl -siS -X POST "$SERVICE_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "$ACCEPT_HEADER" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke-test","version":"0.1"}}}')

SESSION=$(printf "%s" "$INIT" | awk -F': ' 'tolower($1)=="mcp-session-id"{gsub("\r","",$2); print $2}')

if [ -z "$SESSION" ]; then
  echo "ERROR: Failed to get mcp-session-id"
  echo "Response:"
  echo "$INIT"
  exit 1
fi

echo "SESSION=$SESSION"
echo ""

# Step 2: Send initialized notification
echo ">>> Step 2: Send initialized notification"
curl -sS -X POST "$SERVICE_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "$ACCEPT_HEADER" \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null
echo "OK"
echo ""

# Step 3: List tools
echo ">>> Step 3: List tools"
RESULT=$(curl -sS -X POST "$SERVICE_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "$ACCEPT_HEADER" \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"cursor":null}}')

echo "$RESULT"
echo ""

# Check for success
if echo "$RESULT" | grep -q '"tools"'; then
  echo "=========================================="
  echo "SUCCESS: MCP server is working correctly!"
  echo "=========================================="
else
  echo "=========================================="
  echo "WARNING: Unexpected response format"
  echo "=========================================="
  exit 1
fi
