# LexLink MCP Server - GCP Deployment Guide

> **Note**: This guide is **separate from** the existing PlayMCP/AWS deployment at [`DEPLOYMENT_GUIDE.md`](../DEPLOYMENT_GUIDE.md).
>
> | Guide | Target | Transport | Use Case |
> |-------|--------|-----------|----------|
> | `docs/DEPLOYMENT_GUIDE.md` | AWS EC2 + Kakao PlayMCP | SSE/Streaming | Public PlayMCP marketplace |
> | **This guide** | GCP Cloud Run | HTTP (non-streaming) | In-company enterprise use |

## Why GCP Instead of PlayMCP?

PlayMCP has constraints unsuitable for enterprise:
- **Input context length limit**: Truncates large MCP responses
- **Streaming requirement**: `stream: true` conflicts with some clients

**GCP Cloud Run** provides:
- Full response sizes (law text can be 100KB+)
- Non-streaming HTTP transport
- VPC Service Controls for internal-only access
- No Dockerfile needed (source-based deploy)

---

## Recommended: Source-Based Deployment

Cloud Run can deploy directly from your Python source—**no Dockerfile required**. This preserves the Smithery-native project structure.

### Prerequisites

```bash
# Install gcloud CLI: https://cloud.google.com/sdk/docs/install

gcloud auth login

# IMPORTANT: Use the correct PROJECT_ID (lowercase, numbers, hyphens only)
# Find your project ID:
gcloud projects list

gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com
```

> **Note**: Project ID must be lowercase with hyphens (e.g., `my-mcp-server`), not display name.

### Step 1: Verify Entry Point in pyproject.toml

Ensure `pyproject.toml` has the `serve` script (already present by default):

```toml
[project.scripts]
serve = "lexlink.http_server:main"
```

> **Warning**: Do NOT declare `[project.scripts]` twice in pyproject.toml. Duplicate TOML tables cause Cloud Build to fail.

### Step 2: Create Procfile (Optional but Recommended)

Create `Procfile` in project root:

```
web: python -m lexlink.http_server
```

This tells Cloud Run how to start the server.

### Step 3: Store OC Secret

```bash
# Create secret for law.go.kr API identifier
echo -n "your_oc_value" | gcloud secrets create lexlink-oc --data-file=-

# Grant Cloud Run access
gcloud secrets add-iam-policy-binding lexlink-oc \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 4: Deploy from Source

```bash
gcloud run deploy lexlink \
  --source=. \
  --region=asia-northeast3 \
  --memory=1Gi \
  --timeout=300 \
  --set-env-vars="TRANSPORT=http,SLIM_RESPONSE=false" \
  --set-secrets="OC=lexlink-oc:latest" \
  --allow-unauthenticated
```

Cloud Run automatically:
1. Detects `pyproject.toml`
2. Installs dependencies via buildpacks
3. Runs the server using `Procfile` or detected entry point

### Step 5: Verify Deployment

The MCP server uses **Streamable HTTP** which requires proper session handling.

```bash
# Get service URL (run this first!)
SERVICE_URL=$(gcloud run services describe lexlink \
  --region=asia-northeast3 \
  --format='value(status.url)')
echo "SERVICE_URL=$SERVICE_URL"
```

**MCP Session Handshake** (required for all requests):

```bash
# Required headers for MCP Streamable HTTP
ACCEPT_HEADER="Accept: application/json, text/event-stream"

# 1) Initialize session (get mcp-session-id from response header)
INIT=$(curl -siS -X POST "$SERVICE_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "$ACCEPT_HEADER" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0.1"}}}')

SESSION=$(printf "%s" "$INIT" | awk -F': ' 'tolower($1)=="mcp-session-id"{gsub("\r","",$2); print $2}')
echo "SESSION=$SESSION"

# 2) Send initialized notification
curl -sS -X POST "$SERVICE_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "$ACCEPT_HEADER" \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3) Test tools/list
curl -sS -X POST "$SERVICE_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "$ACCEPT_HEADER" \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"cursor":null}}'
```

**Expected Response** (SSE format):
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"eflaw_search",...}]}}
```

> **Tip**: See [`smoke_test.sh`](./smoke_test.sh) for a complete one-liner script.

---

## Internal-Only Access (VPC)

For in-company usage without public internet exposure:

```bash
gcloud run deploy lexlink \
  --source=. \
  --region=asia-northeast3 \
  --ingress=internal \
  --no-allow-unauthenticated \
  --set-env-vars="TRANSPORT=http,SLIM_RESPONSE=false" \
  --set-secrets="OC=lexlink-oc:latest"
```

### Client Authentication

Internal services must include identity token:

```python
import google.auth
from google.auth.transport.requests import Request
import requests

credentials, project = google.auth.default()
credentials.refresh(Request())

headers = {"Authorization": f"Bearer {credentials.token}"}
response = requests.post(f"{SERVICE_URL}/mcp", headers=headers, json=payload)
```

Grant invoker role to client service accounts:

```bash
gcloud run services add-iam-policy-binding lexlink \
  --region=asia-northeast3 \
  --member="serviceAccount:client-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

---

## Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `TRANSPORT` | `http` | Non-streaming HTTP (not `sse`) |
| `SLIM_RESPONSE` | `false` | Full responses for enterprise clients |
| `OC` | (secret) | law.go.kr API identifier |
| `HTTP_TIMEOUT_S` | `60` | Upstream timeout (law.go.kr can be slow) |

> **Note**: `PORT` is automatically set by Cloud Run (default 8080). Do not set it manually.

---

## Monitoring

### View Logs

```bash
# Recent logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=lexlink" \
  --limit=50

# Stream logs
gcloud beta run services logs tail lexlink --region=asia-northeast3
```

### Update Deployment

```bash
# Redeploy after code changes
gcloud run deploy lexlink --source=. --region=asia-northeast3
```

---

## Cost Estimation

| Usage | Estimated Monthly |
|-------|-------------------|
| Light (1K req/day) | $5-10 |
| Medium (10K req/day) | $20-50 |
| Heavy (100K req/day) | $100-200 |

*Free tier: 2M requests/month, 360K GB-seconds*

---

## Troubleshooting

### Deployment Errors

**Invalid project ID**
```
ERROR: The project property must be set to a valid project ID
```
→ Use `gcloud projects list` to find the correct PROJECT_ID (lowercase/hyphens only).

**Reserved env PORT**
```
ERROR: reserved env names were provided: PORT
```
→ Remove `PORT=...` from `--set-env-vars`. Cloud Run sets PORT automatically.

**Cloud Build fails (TOML parse error)**
```
Build failed; check build logs
```
→ Check for duplicate `[project.scripts]` tables in pyproject.toml. Merge into one block.

### Verification Errors

**406 Not Acceptable**
```json
{"error":{"message":"Client must accept both application/json and text/event-stream"}}
```
→ Add header: `-H "Accept: application/json, text/event-stream"`

**Missing session ID**
```
Bad Request: Missing session ID
```
→ Must call `initialize` first and include `mcp-session-id` header from response.

**Invalid params on tools/list**
```
{"error":{"code":-32602,"message":"Invalid params"}}
```
→ Include `"params":{"cursor":null}` in the request body.

**/health returns 404**
→ This is expected. The server doesn't have a `/health` endpoint. Use `/mcp` for verification.

**SERVICE_URL is empty**
```
curl: (3) URL rejected: No host part in the URL
```
→ Run the `SERVICE_URL=$(gcloud run services describe ...)` command first, then verify with `echo $SERVICE_URL`.

### Runtime Errors

**Cold start timeout**: Set minimum instances
```bash
gcloud run services update lexlink --min-instances=1 --region=asia-northeast3
```

**law.go.kr timeout**: Increase Cloud Run timeout
```bash
gcloud run services update lexlink --timeout=300 --region=asia-northeast3
```

**Build fails on Python version**
```bash
# Ensure pyproject.toml specifies Python 3.10+
requires-python = ">=3.10"
```

### MCP Client Checklist

When connecting LLM clients (Claude, etc.), verify:
- [ ] Client sends `Accept: application/json, text/event-stream`
- [ ] Client handles MCP session handshake (`mcp-session-id`)
- [ ] Client follows lifecycle: `initialize` → `notifications/initialized` → tools
- [ ] Client parses SSE responses (`event: message\ndata: {...}`)

---

## Appendix

### Appendix A: Dockerfile-Based Deployment

If you need more control over the build process (custom dependencies, multi-stage builds), use the Dockerfile approach.

See [`Dockerfile`](./Dockerfile) in this directory.

```bash
# Build from project root
docker build -f docs/internal_GCP_deployment/Dockerfile -t lexlink .

# Push to Artifact Registry
gcloud artifacts repositories create lexlink-repo \
  --repository-format=docker \
  --location=asia-northeast3

gcloud auth configure-docker asia-northeast3-docker.pkg.dev

docker tag lexlink asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/lexlink-repo/lexlink:latest
docker push asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/lexlink-repo/lexlink:latest

# Deploy from image
gcloud run deploy lexlink \
  --image=asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/lexlink-repo/lexlink:latest \
  --region=asia-northeast3 \
  --memory=1Gi \
  --timeout=300 \
  --set-env-vars="TRANSPORT=http,SLIM_RESPONSE=false" \
  --set-secrets="OC=lexlink-oc:latest"
```

### Appendix B: Compute Engine (VM) Deployment

For persistent VMs with predictable traffic. Similar to AWS EC2 approach.

```bash
# Create VM
gcloud compute instances create lexlink-server \
  --zone=asia-northeast3-a \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud

# SSH and setup
gcloud compute ssh lexlink-server --zone=asia-northeast3-a

# Inside VM:
sudo apt update && sudo apt install -y python3.12 nginx
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/your-org/lexlink-ko-mcp.git
cd lexlink-ko-mcp && uv sync

# Create systemd service and nginx reverse proxy
# (See docs/DEPLOYMENT_GUIDE.md for detailed nginx/systemd config)
```

### Appendix C: Cloud Build CI/CD

For automated deployments on git push. See [`cloudbuild.yaml`](./cloudbuild.yaml).

```bash
# Manual trigger
gcloud builds submit --config=docs/internal_GCP_deployment/cloudbuild.yaml .

# Or set up trigger for automatic deployment on push
gcloud builds triggers create github \
  --repo-name=lexlink-ko-mcp \
  --branch-pattern="^main$" \
  --build-config=docs/internal_GCP_deployment/cloudbuild.yaml
```

### Appendix D: Files in This Directory

```
docs/internal_GCP_deployment/
├── README.md                       # This guide
├── QUICKSTART.md                   # One-page quick reference
├── smoke_test.sh                   # Verification script (run after deploy)
├── Dockerfile                      # Container build (Appendix A)
└── cloudbuild.yaml                 # CI/CD pipeline (Appendix C)
```

These files are kept here (not in project root) to preserve the Smithery-native project structure.
