# LexLink Deployment Guide for Kakao PlayMCP

This guide explains how to deploy LexLink as an HTTP server for Kakao PlayMCP.

> **Critical Requirements for PlayMCP:**
> 1. **Domain name required** - Raw IP addresses are rejected (use sslip.io as workaround)
> 2. **Streamable HTTP transport** - Set `TRANSPORT=http` (not SSE)
> 3. **Port 80/443 only** - Use Nginx as reverse proxy

---

## Quick Start (Local Testing)

```bash
# Run with Streamable HTTP transport (required for PlayMCP)
TRANSPORT=http uv run serve

# With fallback OC for testing
OC=your_oc TRANSPORT=http uv run serve

# Server will start at: http://localhost:8000/mcp
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRANSPORT` | **Yes*** | sse | Set to `http` for PlayMCP |
| `OC` | No | - | Fallback OC (used if not provided via HTTP header) |
| `PORT` | No | 8000 | Server port |
| `HOST` | No | 0.0.0.0 | Server host |

*PlayMCP requires Streamable HTTP transport (`TRANSPORT=http`), not SSE.

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

        # Pass OC header for authentication
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
Environment="OC=fallback_oc"
Environment="PORT=8000"
Environment="TRANSPORT=http"
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
Environment="OC=fallback_oc"
Environment="PORT=8000"
Environment="TRANSPORT=http"
ExecStart=/home/ec2-user/.local/bin/uv run serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

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
| **MCP 설명** | 대한민국 법률, 판례, 행정규칙 검색 및 조회를 위한 MCP 서버. law.go.kr 국가법령정보 API 연동. 24개 도구 지원. |
| **대화 예시 1** | 민법 제20조 내용 알려줘 |
| **대화 예시 2** | 건축법과 관련된 대법원 판례 검색해줘 |
| **대화 예시 3** | 자동차관리법 시행령 검색 |
| **인증 방식** | Key/Token 인증 |
| **MCP Endpoint** | `http://YOUR-IP-WITH-DASHES.sslip.io/mcp` |

> **Endpoint Examples:**
> - IP: `3.232.164.31`
> - Endpoint: `http://3-232-164-31.sslip.io/mcp`

### Key/Token Authentication Setup

When you select **Key/Token 인증**, configure:

| Setting | Value |
|---------|-------|
| **Header 이름** | `OC` |
| **설명** | 법제처 국가법령정보 API OC 식별자 (open.law.go.kr에서 발급) |

**How it works:**
1. Each user registers at [open.law.go.kr](https://open.law.go.kr) to get their own OC
2. User enters their OC in PlayMCP settings
3. PlayMCP sends the OC via HTTP header when connecting to your server
4. Your server uses the user's OC for API calls (each user uses their own quota)

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

## Optional: HTTPS with SSL Certificate

For production with a custom domain:

```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx  # Ubuntu
sudo yum install -y certbot python3-certbot-nginx  # Amazon Linux

# Get SSL certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com
```

Then use `https://your-domain.com/mcp` for Kakao PlayMCP.

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
│  │         - OCHeaderMiddleware                         │    │
│  │         - Streamable HTTP transport (/mcp)           │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              law.go.kr API                           │    │
│  │              (using user's OC)                       │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```
