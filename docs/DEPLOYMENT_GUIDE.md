# LexLink Deployment Guide for Kakao PlayMCP

This guide explains how to deploy LexLink as an HTTP server for Kakao PlayMCP.

> **Critical Requirements for PlayMCP:**
> 1. **Domain name required** - Raw IP addresses are rejected
> 2. **Streamable HTTP transport** - Set `TRANSPORT=http` (not SSE)
> 3. **Port 80/443 only** - Use Nginx as reverse proxy
> 4. **Server OC must have server IP registered** at open.law.go.kr

---

## Quick Start (Local Testing)

```bash
# Run with Streamable HTTP transport (required for PlayMCP)
TRANSPORT=http uv run serve

# With your registered OC
OC=your_oc TRANSPORT=http uv run serve

# Server will start at: http://localhost:8000/mcp
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRANSPORT` | **Yes*** | sse | Set to `http` for PlayMCP |
| `OC` | **Yes** | - | Server's OC for law.go.kr API (must have server IP registered) |
| `PORT` | No | 8000 | Server port |
| `HOST` | No | 0.0.0.0 | Server host |
| `SLIM_RESPONSE` | No | - | Set to `true` to remove redundant raw XML from responses when parsed data exists (for PlayMCP size limits) |

*PlayMCP requires Streamable HTTP transport (`TRANSPORT=http`), not SSE.

---

## Important: Server OC & IP Registration

law.go.kr validates each API call by checking the OC + the requesting IP as a registered pair. Since the server makes all API calls from its own IP, **the server's `OC` environment variable must be an OC that has the server's public IP registered**.

1. Log in to [open.law.go.kr](https://open.law.go.kr)
2. Go to IP/domain registration settings for the OC you will use
3. Add your server's public IP (e.g., `34.47.86.246`)
4. Set `OC=that_oc` in the server's environment (systemd service file)

Without this, the API returns "사용자 정보 검증에 실패하였습니다" (user verification failed). Per-user OC values will **not** work because the server's IP is not registered under each user's OC.

**Note:** LexLink includes an anti-bot bypass (`client.py`) that automatically handles law.go.kr's JavaScript redirect protection. No additional configuration is needed for this.

---

## AWS EC2 Deployment

### Step 1: Launch EC2 Instance

1. Go to AWS Console → EC2 → Launch Instance
2. Choose your AMI:
   - **Ubuntu 22.04 LTS** (user: `ubuntu`)
   - **Amazon Linux 2023** (user: `ec2-user`)
3. Instance type: **t3.micro** (free tier) or higher
4. Create or select a key pair for SSH access
5. Security Group settings:
   - Allow SSH (port 22) from your IP
   - Allow HTTP (port 80) from anywhere (0.0.0.0/0)
   - Allow HTTPS (port 443) from anywhere (0.0.0.0/0) - optional

### Step 2: Allocate Elastic IP (Fixed IP)

1. Go to EC2 → Elastic IPs → Allocate Elastic IP address
2. Associate it with your EC2 instance
3. Note down this IP - you'll convert it to a domain using sslip.io

**Domain conversion with sslip.io:**
- IP: `3.232.164.31`
- Domain: `3-232-164-31.sslip.io` (replace dots with dashes)

### Step 3: Connect to EC2

```bash
# For Ubuntu
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP

# For Amazon Linux
ssh -i your-key.pem ec2-user@YOUR_ELASTIC_IP
```

### Step 4: Install Dependencies

**For Ubuntu:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv git nginx
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

**For Amazon Linux:**
```bash
sudo yum update -y
sudo yum install -y python3.12 git nginx
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### Step 5: Clone and Setup Project

```bash
cd ~
git clone https://github.com/rabqatab/lexlink-ko-mcp.git
cd lexlink-ko-mcp
uv sync
```

### Step 6: Test Run

```bash
# Test if server starts correctly (use TRANSPORT=http!)
OC=your_oc TRANSPORT=http uv run serve

# You should see:
# Starting LexLink MCP server (HTTP) on 0.0.0.0:8000
# Endpoint: http://0.0.0.0:8000/mcp
# Press Ctrl+C to stop
```

### Step 7: Configure Nginx (Required for PlayMCP)

Kakao PlayMCP requires port 80/443 (no custom ports allowed).

**For Ubuntu:** Create config in `/etc/nginx/sites-available/`
```bash
sudo nano /etc/nginx/sites-available/lexlink
```

**For Amazon Linux:** Create config in `/etc/nginx/conf.d/`
```bash
sudo nano /etc/nginx/conf.d/lexlink.conf
```

Paste this content:

```nginx
server {
    listen 80;
    server_name _;  # Accept any hostname/IP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Required for HTTP streaming
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;  # 24 hours for long connections

        # Pass through headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Pass through custom headers
        proxy_set_header OC $http_oc;
    }
}
```

**For Ubuntu only:** Enable site and remove default
```bash
sudo ln -s /etc/nginx/sites-available/lexlink /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

**For Amazon Linux:** Comment out default server in main config
```bash
sudo nano /etc/nginx/nginx.conf
# Comment out or delete the existing server { } block
```

**Test and restart nginx:**
```bash
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

### Step 8: Create Systemd Service (Auto-start)

```bash
sudo nano /etc/systemd/system/lexlink.service
```

**For Ubuntu:** (User=ubuntu, paths use /home/ubuntu/)
```ini
[Unit]
Description=LexLink MCP Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/lexlink-ko-mcp
Environment="OC=your_registered_oc"
Environment="PORT=8000"
Environment="TRANSPORT=http"
Environment="SLIM_RESPONSE=true"
ExecStart=/home/ubuntu/.local/bin/uv run serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**For Amazon Linux:** (User=ec2-user, paths use /home/ec2-user/)
```ini
[Unit]
Description=LexLink MCP Server
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/lexlink-ko-mcp
Environment="OC=your_registered_oc"
Environment="PORT=8000"
Environment="TRANSPORT=http"
Environment="SLIM_RESPONSE=true"
ExecStart=/home/ec2-user/.local/bin/uv run serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> **Note:** As of v2.0.0, JSON is the **default response format** (previously XML). Tools return JSON by default; use `type="XML"` to request XML format.
>
> **Note:** For case law tools (`prec_service`, `detc_service`, etc.) that return large responses, use `sections="summary"` parameter to retrieve only the summary section and stay within PlayMCP's 24KB size limit.
>
> **Note:** `SLIM_RESPONSE=true` prevents "Tool call returned too large content part" errors on PlayMCP by removing redundant raw XML when parsed `ranked_data` exists. All fields in `ranked_data` are preserved — no filtering or truncation.
>
> **How it works:**
> - Search tools (`_search`): `raw_content` removed, `ranked_data` preserved with all fields → ~5-15KB
> - Service tools (`_service`): No `ranked_data` exists → `raw_content` kept as-is (full text)
> - `aiSearch`: Default display reduced to 7 (조문내용 ~600 chars/item × 7 ≈ 15KB)
>
> **Response fields preserved per search tool (v1.5.2 verified):**
>
> | Tool | Data Key | Fields |
> |------|----------|--------|
> | `eflaw_search`, `law_search` | `law` | id, 법령일련번호, 현행연혁코드, 법령명한글, 법령약칭명, 법령ID, 공포일자, 공포번호, 제개정구분명, 소관부처코드, 소관부처명, 법령구분명, 시행일자, 법령상세링크 |
> | `elaw_search` | `law` | id, 법령일련번호, 현행연혁코드, 법령명한글, 법령명영문, 법령ID, 공포일자, 공포번호, 제개정구분명, 소관부처명, 법령구분명, 시행일자, 법령상세링크 |
> | `admrul_search` | `admrul` | id, 행정규칙일련번호, 행정규칙명, 행정규칙종류, 발령일자, 발령번호, 소관부처명, 현행연혁구분, 제개정구분명, 행정규칙ID, 행정규칙상세링크, 시행일자 |
> | `prec_search` | `prec` | id, 판례일련번호, 사건명, 사건번호, 선고일자, 법원명, 법원종류코드, 사건종류명, 사건종류코드, 판결유형, 선고, 데이터출처명, 판례상세링크 |
> | `detc_search` | `Detc` | id, 헌재결정례일련번호, 종국일자, 사건번호, 사건명, 헌재결정례상세링크 |
> | `expc_search` | `expc` | id, 법령해석례일련번호, 안건명, 안건번호, 질의기관명, 회신기관명, 회신일자, 법령해석례상세링크 |
> | `decc_search` | `decc` | id, 행정심판재결례일련번호, 사건명, 사건번호, 처분일자, 의결일자, 처분청, 재결청, 재결구분명, 행정심판례상세링크 |
> | `aiSearch` | `법령조문` | id, 법령일련번호, 법령ID, 법령명, 시행일자, 공포일자, 소관부처명, 법령종류명, 조문일련번호, 조문번호, 조문가지번호, 조문제목, **조문내용** |
> | `aiRltLs_search` | `법령조문` | id, 법령ID, 법령명, 시행일자, 공포일자, 조문번호, 조문가지번호, 조문제목 |

> **Important:** Make sure paths match your actual directory name (case-sensitive!)
> Check with: `ls ~/ | grep -i lexlink`

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable lexlink
sudo systemctl start lexlink
sudo systemctl status lexlink
```

### Step 9: Verify Setup

```bash
# Test locally (should return MCP response)
curl -X POST http://localhost/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

# Test from outside using sslip.io domain
curl -X POST http://YOUR-IP-WITH-DASHES.sslip.io/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

---

## Kakao PlayMCP Registration

Fill in the registration form:

| Field | Value |
|-------|-------|
| **대표 이미지** | Upload `LexLink_logo.png` from assets folder |
| **MCP 이름** | LexLink - 한국 법령정보 |
| **MCP 식별자** | lexlink |
| **MCP 설명** | 대한민국 법률, 판례, 행정규칙 검색 및 조회를 위한 MCP 서버. law.go.kr 국가법령정보 API 연동. 54개 도구 지원. |
| **대화 예시 1** | 민법 제20조 내용 알려줘 |
| **대화 예시 2** | 건축법과 관련된 대법원 판례 검색해줘 |
| **대화 예시 3** | 자동차관리법 시행령 검색 |
| **인증 방식** | 인증 없음 |
| **MCP Endpoint** | `http://YOUR-IP-WITH-DASHES.sslip.io/mcp` |

> **Note:** The server uses its own OC (set via environment variable) for all API calls.
> Users do not need to provide their own OC — law.go.kr validates OC + server IP as a pair.

---

## Updating the Server

When you update the LexLink project, re-deploy to EC2:

```bash
# SSH into EC2
ssh -i your-key.pem ec2-user@YOUR_IP  # or ubuntu@ for Ubuntu

# Pull latest code and restart
cd ~/lexlink-ko-mcp
git pull
uv sync  # if dependencies changed
sudo systemctl restart lexlink

# Verify it's running
sudo systemctl status lexlink
```

**One-liner from local machine:**
```bash
ssh AWS_lexlink "cd ~/lexlink-ko-mcp && git pull && uv sync && sudo systemctl restart lexlink"
```

**If ngrok is running**, it will automatically reconnect to the restarted service.

---

## Useful Commands

```bash
# Start/stop/restart LexLink
sudo systemctl start lexlink
sudo systemctl stop lexlink
sudo systemctl restart lexlink

# Start/stop/restart Nginx
sudo systemctl start nginx
sudo systemctl stop nginx
sudo systemctl restart nginx

# Check status
sudo systemctl status lexlink
sudo systemctl status nginx

# View LexLink logs (live)
sudo journalctl -u lexlink -f

# View Nginx access logs
sudo tail -f /var/log/nginx/access.log

# View Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

---

## Troubleshooting

### PlayMCP says "Endpoint URL의 도메인이 유효하지 않습니다"

PlayMCP rejects raw IP addresses. Use sslip.io:
- Wrong: `http://3.232.164.31/mcp`
- Correct: `http://3-232-164-31.sslip.io/mcp`

### PlayMCP says "MCP Server 연결 확인에 실패했습니다"

1. **Check transport type:** Must use `TRANSPORT=http` (not SSE)
   ```bash
   grep TRANSPORT /etc/systemd/system/lexlink.service
   # Should show: Environment="TRANSPORT=http"
   ```

2. **Check endpoint:** Must be `/mcp` (not `/sse`)

3. **Test the endpoint manually:**
   ```bash
   curl -X POST http://localhost:8000/mcp \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
   ```

### Service fails with status=217/USER

Wrong username in service file. Check your OS:
```bash
whoami  # Shows your username
```
Update the service file to use the correct username and paths.

### Service fails with status=203/EXEC

Wrong path to uv or project directory:
```bash
which uv                    # Find uv path
ls ~/lexlink-ko-mcp         # Check project exists (case-sensitive!)
```

### Port 8000 already in use (status=1/FAILURE)

Kill the stale process:
```bash
sudo lsof -i :8000          # Find PID
sudo kill <PID>             # Kill it
sudo systemctl restart lexlink
```

### Server won't start

```bash
# Check if port is already in use
sudo lsof -i :8000
sudo lsof -i :80

# Check service logs
sudo journalctl -u lexlink -n 50
sudo journalctl -u nginx -n 50
```

### Nginx 502 Bad Gateway

The LexLink service is not running:
```bash
sudo systemctl status lexlink
sudo systemctl restart lexlink
sudo journalctl -u lexlink -n 50
```

### Nginx conflicting server name warning

Another config is using `server_name _`. Remove default configs:
```bash
# Ubuntu
sudo rm -f /etc/nginx/sites-enabled/default

# Amazon Linux - edit nginx.conf and comment out server block
sudo nano /etc/nginx/nginx.conf
```

---

## HTTPS Setup (Optional)

HTTPS is not required when using "인증 없음" auth, but recommended for production.

### Option 1: ngrok (Free, Quickest)

Best for testing and small-scale use.

**Install ngrok:**
```bash
# Download and install
curl -s https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz | sudo tar xzf - -C /usr/local/bin

# Create free account at https://ngrok.com and get auth token
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

**Run ngrok:**
```bash
# Start ngrok (tunnels to port 8000)
ngrok http 8000

# Or run in background
nohup ngrok http 8000 > /tmp/ngrok.log 2>&1 &

# Get the HTTPS URL
curl -s http://localhost:4040/api/tunnels | grep -o 'https://[^"]*'
```

**PlayMCP Endpoint:** `https://YOUR-RANDOM-SUBDOMAIN.ngrok-free.dev/mcp`

> **Note:** Free ngrok URLs change each restart. For persistent URLs, upgrade to ngrok paid plan or use Let's Encrypt.

### Option 2: Let's Encrypt (Free, Production)

Best for production with a custom domain.

```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx  # Ubuntu
sudo yum install -y certbot python3-certbot-nginx  # Amazon Linux

# Get SSL certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com
```

**PlayMCP Endpoint:** `https://your-domain.com/mcp`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Internet                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   AWS Security Group                         │
│                   (Allow port 80/443)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      EC2 Instance                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Nginx (port 80)                         │    │
│  │              - Reverse proxy                         │    │
│  │              - Pass OC header                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         LexLink MCP Server (port 8000)               │    │
│  │         - uvicorn + FastMCP                          │    │
│  │         - Streamable HTTP transport (/mcp)           │    │
│  │         - Uses server's OC (env var)                 │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              law.go.kr API                           │    │
│  │              (using server's OC)                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```
