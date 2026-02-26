# GCP Deployment Quick Start

**Deploy LexLink to Cloud Run in 5 minutes—no Dockerfile needed.**

> For PlayMCP/AWS, see [`assets/DEPLOYMENT_GUIDE.md`](../../assets/DEPLOYMENT_GUIDE.md)

---

## Prerequisites

```bash
gcloud auth login

# Find your PROJECT_ID (lowercase/hyphens only, NOT display name)
gcloud projects list

gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com
```

---

## Deploy (Source-Based)

### 1. Add entry point to `pyproject.toml`

```toml
[project.scripts]
serve = "lexlink.http_server:main"
```

> **Warning**: Don't duplicate `[project.scripts]`. Merge if it exists.

### 2. Create `Procfile` in project root

```
web: python -m lexlink.http_server
```

### 3. Store secret & deploy

```bash
# Store OC secret
echo -n "your_oc_value" | gcloud secrets create lexlink-oc --data-file=-

# Deploy (no PORT env - Cloud Run sets it automatically)
gcloud run deploy lexlink \
  --source=. \
  --region=asia-northeast3 \
  --memory=1Gi \
  --timeout=300 \
  --set-env-vars="TRANSPORT=http,SLIM_RESPONSE=false" \
  --set-secrets="OC=lexlink-oc:latest" \
  --allow-unauthenticated
```

### 4. Verify (MCP Session Handshake Required)

```bash
# Get URL
SERVICE_URL=$(gcloud run services describe lexlink \
  --region=asia-northeast3 --format='value(status.url)')
echo "SERVICE_URL=$SERVICE_URL"

# Run smoke test
./docs/internal_GCP_deployment/smoke_test.sh
```

Or manually:

```bash
ACCEPT="Accept: application/json, text/event-stream"

# 1) Initialize
INIT=$(curl -siS -X POST "$SERVICE_URL/mcp" \
  -H "Content-Type: application/json" -H "$ACCEPT" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0.1"}}}')
SESSION=$(printf "%s" "$INIT" | awk -F': ' 'tolower($1)=="mcp-session-id"{gsub("\r","",$2); print $2}')

# 2) Notify initialized
curl -sS -X POST "$SERVICE_URL/mcp" -H "Content-Type: application/json" \
  -H "$ACCEPT" -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3) List tools
curl -sS -X POST "$SERVICE_URL/mcp" -H "Content-Type: application/json" \
  -H "$ACCEPT" -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"cursor":null}}'
```

---

## Common Errors

| Error | Fix |
|-------|-----|
| `reserved env names: PORT` | Remove PORT from `--set-env-vars` |
| `406 Not Acceptable` | Add `Accept: application/json, text/event-stream` |
| `Missing session ID` | Call `initialize` first, use `mcp-session-id` header |
| `/health` 404 | Expected—no health endpoint, use `/mcp` |
| Duplicate TOML table | Merge `[project.scripts]` into one block |

---

## Internal-Only (VPC)

```bash
gcloud run deploy lexlink \
  --source=. \
  --region=asia-northeast3 \
  --ingress=internal \
  --no-allow-unauthenticated \
  ...
```

---

## Files

```
docs/internal_GCP_deployment/
├── README.md                    # Full guide
├── QUICKSTART.md                # This file
├── smoke_test.sh                # Verification script
├── lexlink_mcp_errors_summary.md # Debugging reference
├── Dockerfile                   # Appendix option
└── cloudbuild.yaml              # CI/CD option
```

See [README.md](./README.md) for detailed instructions.
