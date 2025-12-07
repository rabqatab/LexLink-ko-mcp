# LexLink Deployment Guide for Kakao PlayMCP

This guide explains how to deploy LexLink as an HTTP server for Kakao PlayMCP.

---

## Quick Start (Local Testing)

```bash
# Run the HTTP server (OC can be provided via header or env var)
uv run serve

# Or with a fallback OC for testing
OC=your_oc uv run serve

# Server will start at: http://localhost:8000/sse
# PlayMCP clients send OC via HTTP header automatically
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OC` | No* | - | Fallback OC (used if not provided via HTTP header) |
| `PORT` | No | 8000 | Server port |
| `HOST` | No | 0.0.0.0 | Server host |
| `TRANSPORT` | No | sse | Transport type: `sse` or `http` |

*When using PlayMCP with Key/Token auth, users provide their own OC via HTTP header.

---

## AWS EC2 Deployment

### Step 1: Launch EC2 Instance

1. Go to AWS Console → EC2 → Launch Instance
2. Choose **Ubuntu 22.04 LTS**
3. Instance type: **t3.micro** (free tier) or higher
4. Create or select a key pair for SSH access
5. Security Group settings:
   - Allow SSH (port 22) from your IP
   - Allow Custom TCP (port 8000) from anywhere (0.0.0.0/0)

### Step 2: Allocate Elastic IP (Fixed IP)

1. Go to EC2 → Elastic IPs → Allocate Elastic IP address
2. Associate it with your EC2 instance
3. Note down this IP - you'll use it for Kakao PlayMCP

### Step 3: Connect to EC2

```bash
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP
```

### Step 4: Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.12
sudo apt install -y python3.12 python3.12-venv git

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### Step 5: Clone and Setup Project

```bash
# Clone repository
git clone https://github.com/rabqatab/lexlink-ko-mcp.git
cd lexlink-ko-mcp

# Install dependencies
uv sync
```

### Step 6: Test Run

```bash
# Test if server starts correctly
OC=ddongle0205 uv run serve

# You should see:
# INFO: Uvicorn running on http://0.0.0.0:8000
# Press Ctrl+C to stop
```

### Step 7: Create Systemd Service (Auto-start)

```bash
# Create service file
sudo nano /etc/systemd/system/lexlink.service
```

Paste this content:

```ini
[Unit]
Description=LexLink MCP Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/lexlink-ko-mcp
# OC is optional - PlayMCP users provide their own OC via HTTP header
# Set a fallback OC for testing or non-PlayMCP clients
Environment="OC=fallback_oc"
Environment="PORT=8000"
ExecStart=/home/ubuntu/.local/bin/uv run serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save and exit (Ctrl+X, Y, Enter).

```bash
# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable lexlink
sudo systemctl start lexlink

# Check status
sudo systemctl status lexlink

# View logs
sudo journalctl -u lexlink -f
```

---

## Kakao PlayMCP Registration

Fill in the registration form:

| Field | Value |
|-------|-------|
| **대표 이미지** | Upload `LexLink_logo.png` from assets folder |
| **MCP 이름** | LexLink - 한국 법령정보 |
| **MCP 식별자** | lexlink |
| **MCP 설명** | 대한민국 법률, 판례, 행정규칙 검색 및 조회를 위한 MCP 서버. law.go.kr 국가법령정보 API 연동. 24개 도구 지원 (법령 검색, 조문 조회, 판례 검색, 헌재결정례, 법령해석례 등). |
| **대화 예시 1** | 민법 제20조 내용 알려줘 |
| **대화 예시 2** | 건축법과 관련된 대법원 판례 검색해줘 |
| **대화 예시 3** | 자동차관리법 시행령 검색 |
| **인증 방식** | Key/Token 인증 |
| **MCP Endpoint** | `http://YOUR_ELASTIC_IP:8000/sse` |

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
# Start server
sudo systemctl start lexlink

# Stop server
sudo systemctl stop lexlink

# Restart server
sudo systemctl restart lexlink

# Check status
sudo systemctl status lexlink

# View logs (live)
sudo journalctl -u lexlink -f

# View recent logs
sudo journalctl -u lexlink --since "1 hour ago"
```

---

## Troubleshooting

### Server won't start

```bash
# Check if port is already in use
sudo lsof -i :8000

# Check service logs
sudo journalctl -u lexlink -n 50
```

### Connection refused from outside

1. Check AWS Security Group allows port 8000
2. Check if server is running: `sudo systemctl status lexlink`
3. Test locally first: `curl http://localhost:8000/sse`

### OC error

Make sure `OC` is set in the systemd service file (or users provide via HTTP header):
```bash
sudo nano /etc/systemd/system/lexlink.service
# Check Environment="OC=your_id"
sudo systemctl daemon-reload
sudo systemctl restart lexlink
```

---

## Optional: HTTPS with Nginx

For production, add HTTPS:

```bash
# Install nginx and certbot
sudo apt install -y nginx certbot python3-certbot-nginx

# Configure nginx
sudo nano /etc/nginx/sites-available/lexlink
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/lexlink /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

Then use `https://your-domain.com/sse` for Kakao PlayMCP.
