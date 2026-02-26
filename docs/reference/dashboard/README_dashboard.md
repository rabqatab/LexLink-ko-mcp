# Smithery Logs Dashboard

A Streamlit-based dashboard for viewing and analyzing Smithery MCP server logs.

## Features

- **Overview**: Key metrics, time series charts, distribution visualizations
- **Logs Explorer**: Filterable log table with expandable details, CSV/JSON export
- **Tool Analytics**: Per-tool performance metrics and comparisons

## Status Icons

| Icon | Meaning | Description |
|------|---------|-------------|
| 🟢 | Success | Request completed with valid content |
| 🟡 | Empty/Error Result | Success status but no meaningful content (check request params or API issue) |
| 🔴 | Error | Request failed |

**Yellow circle (🟡) patterns:**
- `totalCnt=0` - Search returned no results
- `status: "error"` in result - Upstream API error (e.g., 500, missing params)
- Empty content array

## Logs Explorer - Filter Guide

The Logs Explorer supports filtering by every field in the log entries.

### Basic Filters (Always Visible)

| Filter | Description |
|--------|-------------|
| **Date Range** | Filter logs by request timestamp |
| **Method** | Filter by RPC method (tools/call, initialize, tools/list, etc.) |
| **Status** | Filter by Success or Error |
| **Tool** | Filter by tool name (for tools/call method) |
| **Client** | Filter by client name |
| **Duration Range** | Slider to filter by response time (ms) |

### Advanced Filters (Collapsible Section)

| Filter | Description |
|--------|-------------|
| **RPC ID Search** | Search by RPC ID (exact or partial match) |
| **Protocol Version** | Filter by MCP protocol version |
| **OC (API Key)** | Filter by OC value from params.arguments (user identifier) |
| **Client Info Name** | Filter by client info name from params |
| **Duration Bucket** | Quick filter: Fast (<500ms), Normal, Slow, Very Slow |
| **Hour of Day** | Filter by hour (0-23) |
| **Day of Week** | Filter by day (Monday-Sunday) |
| **Has Response** | Filter logs with/without response |
| **Has Result** | Filter logs with/without result |
| **Has Error** | Filter logs with/without error field |
| **Result isError** | Filter by result.isError flag |
| **Empty Result** | Filter logs with empty/error results (yellow circle) |

### Search

| Scope | Description |
|-------|-------------|
| **All Fields** | Search in params, result, error, and RPC ID |
| **Params Only** | Search only in request parameters |
| **Result Only** | Search only in response result |
| **Error Only** | Search only in error field |
| **Arguments Only** | Search only in params.arguments (tool-specific args) |

### Export

- **CSV**: Export filtered logs to CSV (basic fields)
- **JSON**: Export filtered logs to JSON (all fields)

## Setup

1. Install uv (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Install dependencies:
   ```bash
   cd dashboard
   uv sync
   ```

3. Ensure crawler logs are available at `../crawler/data/logs/`

4. Run the dashboard:
   ```bash
   uv run streamlit run app.py
   ```

5. Open http://localhost:8501 in your browser

## Project Structure

```
dashboard/
├── app.py              # Main Streamlit app
├── data_loader.py      # Data loading with deduplication
├── pages/
│   ├── __init__.py
│   ├── overview.py     # Overview dashboard
│   ├── explorer.py     # Log explorer with filters
│   └── tools.py        # Tool analytics
├── pyproject.toml      # uv project config
├── uv.lock             # Dependency lock
├── requirements.txt    # Legacy pip support
└── README.md
```

## Data Source

The dashboard reads JSON log files from `../crawler/data/logs/`. Logs are deduplicated by `rpc_id` when loading multiple files.
