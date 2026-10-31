# LexLink HTTP 서버 운영 가이드

HTTP/SSE 모드(`uv run serve`)를 외부에 노출할 때의 배포, 인증, 로깅, 제한, 프록시 설정을 설명합니다. stdio 모드는 이 문서의 영향을 받지 않습니다.

목차: 1 기본 원칙 / 2 환경변수 / 3 로그와 개인정보 / 4 TLS 프록시 / 5 systemd / 6 PlayMCP 등록 / 7 OC와 IP 등록 / 8 EC2 배포 절차 / 9 문제 해결

로컬 시험:

```bash
OC=<OC> LEXLINK_AUTH_TOKENS=local:<TOKEN> TRANSPORT=http uv run serve
# 엔드포인트: http://localhost:8000/mcp  (Host localhost:8000은 기본으로 허용)
```

## 1. 기본 원칙

- **단일 프로세스, 단일 워커로만 실행합니다.** 속도 제한(rate limit)과 로그 기록 스레드는 프로세스 메모리 안에서 동작하므로 `uvicorn --workers N`(N>1)이나 다중 인스턴스에서는 제한이 정확하지 않습니다.
- **`TRANSPORT=http`(Streamable HTTP, `/mcp`)를 권장합니다.** SSE(`/sse`)는 레거시입니다.
- 인증 없이는 시작되지 않습니다(fail closed). `LEXLINK_AUTH_TOKENS`가 없고 `LEXLINK_ALLOW_NO_AUTH=true`도 아니면 기동 시 `RuntimeError`가 발생합니다.
- HTTP 모드에서는 도구의 `oc` 인자를 **무시**하고 항상 서버 환경변수 `OC`를 사용합니다. (stdio 모드는 기존대로 `oc` 인자를 허용합니다.)
- 미들웨어 순서: 인증 > 로깅 > 속도 제한 > 앱.
- ASGI 팩토리로도 실행할 수 있습니다: `uvicorn --factory --no-proxy-headers lexlink.http_server:create_app --host 127.0.0.1 --port 8000` (워커 1개). 팩토리는 **항상 Streamable HTTP(`/mcp`)만, TLS 없는 평문 HTTP로** 서비스하며 `TRANSPORT`/`HOST`/`PORT`는 무시합니다(주소는 uvicorn 옵션 사용). `--no-proxy-headers`를 반드시 붙여 `LEXLINK_TRUSTED_PROXIES`가 `X-Forwarded-For`의 유일한 판단 기준이 되게 하세요(`uv run serve`는 코드에서 `proxy_headers=False`로 실행).
- HTTP 모드의 "`oc` 인자 무시" 스위치는 **프로세스 단위**입니다. `create_app()`을 호출하면 같은 프로세스의 모든 도구 호출이 서버 `OC`를 사용합니다.
- **SSE 전송(`TRANSPORT=sse`, 현재 기본값)의 한계**: 도구 결과가 `GET /sse` 스트림으로 전달되고 `POST /messages/`는 즉시 202를 반환합니다. 따라서 요청별 로그의 `status`/`error_code`는 항상 `ok`/없음으로 남고(스트림은 연결 종료 시 `method: GET`으로 한 번만 기록), 동시성 제한은 업스트림 부하를 제한하지 못합니다(분당 제한은 동작). 시작 시 경고를 출력합니다. 의미 있는 로그/제한이 필요하면 `TRANSPORT=http`를 사용하세요.

## 2. 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OC` | - | law.go.kr API용 서버 OC (서버 IP가 등록되어 있어야 함) |
| `LEXLINK_BASE_URL` | `http://www.law.go.kr` | 업스트림 기본 URL |
| `LEXLINK_TIMEOUT` | `60` | 업스트림 요청 타임아웃(초) |
| `SLIM_RESPONSE` | - | `1`/`true`/`yes`/`on`이면 크기 제한 환경(PlayMCP 등)용 압축 모드: `ranked_data`가 있으면 `raw_content` 제거, 압축 상한 유지(발췌 500자, 상위 10/3건, 위임 항목 80건), 20,000바이트 초과 결과는 줄이고 `truncated`/`truncated_notes` 표시. 없으면 이미 가져온 내용은 자르지 않음 |
| `TRANSPORT` | `sse` | `http`(Streamable HTTP, `/mcp`) 권장. `sse`는 `/sse` |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 바인드 주소. 리버스 프록시 뒤에서는 `HOST=127.0.0.1` 권장 |
| `LEXLINK_AUTH_TOKENS` | - | `이름:토큰,이름2:토큰2`. 클라이언트는 `Authorization: Bearer <토큰>` 전송. 형식 오류/중복이면 기동 실패 |
| `LEXLINK_ALLOW_NO_AUTH` | - | 정확히 `true`일 때만 토큰 없이 기동 (PlayMCP 인증 없음 등록 전용). 기동 시 강한 경고 로그 출력 |
| `LEXLINK_ALLOWED_HOSTS` | - | 허용 Host 헤더 목록(쉼표 구분, 예: `mcp.example.com`). 설정 시 DNS 리바인딩 보호가 해당 호스트 기준으로 켜짐 |
| `LEXLINK_ALLOWED_ORIGINS` | - | 허용 Origin 목록(쉼표 구분, 예: `https://mcp.example.com`). `LEXLINK_ALLOWED_HOSTS` 없이 설정하면 기동 시 `RuntimeError` |
| `LEXLINK_TRUSTED_PROXIES` | - | `X-Forwarded-For`를 신뢰할 직접 접속 피어 IP 목록(정확히 일치, 쉼표 구분) |
| `LEXLINK_MAX_CONCURRENCY` | `8` | 토큰별 동시 POST 요청 수 (`0`이면 제한 없음) |
| `LEXLINK_RATE_LIMIT_PER_MIN` | `60` | 토큰별 분당 POST 요청 수, 슬라이딩 윈도우 (`0`이면 제한 없음) |
| `LEXLINK_MAX_SESSIONS` | `10000` | 메모리에 보관하는 바인딩된 MCP 세션 상한. 도달하면 새 세션은 503 |
| `LEXLINK_SESSION_IDLE_TTL_SEC` | `3600` | Streamable HTTP 세션이 이 시간(초) 동안 활동이 없으면 서버가 세션을 종료하고 슬롯을 반환 (`0`이면 만료 없음) |
| `LEXLINK_LOG_DIR` | `<repo>/logs/playmcp` | 로그 디렉터리 |
| `LEXLINK_LOG_RETENTION_DAYS` | `30` | 이 일수보다 오래된 `YYYY-MM-DD.jsonl`만 삭제 (`0`이면 삭제 안 함) |
| `LEXLINK_LOG_BODIES` | - | `true`면 인자 값과 결과 본문도 기록 (OC는 제거/마스킹) |
| `LEXLINK_LOG_CAPTURE_MAX_BYTES` | `1048576` | 요청/응답 각각 로그용으로 보관하는 최대 바이트 (스트림 전달에는 영향 없음) |

`LEXLINK_ALLOWED_HOSTS`가 없으면 FastMCP 기본값(localhost만 허용)이 유지되고 경고가 출력됩니다. 공개 도메인으로 접근하려면 반드시 설정하세요. 보호 기능을 끄는 옵션은 제공하지 않습니다.

`X-Forwarded-For`는 직접 접속한 피어가 `LEXLINK_TRUSTED_PROXIES`에 있을 때만 사용하며, 그 목록에 없는 가장 오른쪽 주소를 클라이언트 IP로 기록합니다. 그렇지 않으면 피어 IP를 기록합니다.

## 3. 로그 내용과 개인정보

기본 로그(JSONL, 하루 한 파일)에는 다음만 남습니다.

`timestamp`, `token_id`(토큰 SHA-256 앞 12자; 토큰/이름 아님), `method`(알려진 MCP 메서드만, 그 외 `<unknown>`), `tool_name`(등록된 도구만, 그 외 `<unknown>`), 해당 도구 스키마에 선언된 인자 **키 이름**(값 없음; 선언되지 않은 키는 개수만 `unknown_arg_keys`), `status`(ok/error), `error_code`, `http_status`, `response_bytes`(상한을 넘어도 전체 크기), `duration_ms`, `client_ip`. 캡처 상한을 넘으면 `truncated_capture: true`가 붙습니다.

- 인자 값, 결과 본문, `Authorization` 헤더, 토큰은 기본으로 기록되지 않습니다.
- `LEXLINK_LOG_BODIES=true`는 사용자의 법률 질의 내용이 로그에 남을 수 있으므로 개인정보 처리 방침을 확인한 뒤 사용하세요. 이때도 `oc`/`token`/`authorization` 계열 키는 중첩된 dict/list 및 `result` 안에서도 재귀적으로 제거되고 OC는 마스킹됩니다.
- 쓰기는 별도 백그라운드 스레드가 큐로 처리하며(이벤트 루프 비차단), 종료 시 flush 됩니다.
- 보존 기간 정리는 기록 스레드 시작 시(첫 기록을 기다리지 않음)와 날짜가 바뀔 때 실행됩니다.
- 로그 파일은 권한 `0600`, 디렉터리는 `0700`으로 생성됩니다(이미 존재하는 디렉터리/파일의 권한은 바꾸지 않음).
- 큐(10000건)가 가득 차면 항목이 버려지며, 개수를 세어 최대 1분에 한 번 경고 로그를 남깁니다.

### 알려진 한계

- 세션은 만든 토큰에 묶입니다(`SessionBindingMiddleware`). 다른 토큰이 `Mcp-Session-Id`(Streamable HTTP) 또는 `session_id` 쿼리(SSE `/messages/`)로 남의 세션을 POST/GET/DELETE 하면 앱을 호출하지 않고, 존재하지 않는 세션과 동일한 404를 돌려주므로 세션 존재 여부도 드러나지 않습니다. 세션 헤더 없는 모든 요청(메서드·쿼리 무관)은 세션을 만들 수 있으므로 앱 호출 전에 슬롯을 예약하고, 응답의 세션 id는 항상 바인딩합니다(2xx가 아닌 응답으로 만들어진 세션은 즉시 종료·해제). 쿼리 `session_id`는 SSE `/messages/`에서만 검사합니다. 서로 다른 세션 id를 여러 개 보내면 존재하지 않는 세션과 같은 404입니다. 바인딩은 소유자의 DELETE(2xx) 또는 종료 확인 뒤에만 제거되며(앱의 404만으로는 제거하지 않음), SSE 스트림이 끝나면 id는 모든 토큰에 404가 됩니다.
- 바인딩은 메모리에 최대 `LEXLINK_MAX_SESSIONS`개(기본 10000)만 보관합니다. 오래된 항목을 쫓아내면 그 세션이 "바인딩 없는 세션"이 되어 다른 토큰이 쓸 수 있으므로, 상한에 도달하면 새 세션 생성을 503(`too_many_sessions`, `Retry-After`)으로 거절합니다(기존 세션은 유지). 클라이언트가 DELETE 없이 사라져도 `LEXLINK_SESSION_IDLE_TTL_SEC`(기본 3600초, `0`이면 끔) 동안 활동이 없으면 서버가 세션 자체를 종료(내부 DELETE)한 뒤 바인딩을 제거해 슬롯이 반환됩니다. 진행 중인 요청이나 열린 GET 스트림이 있는 세션은 유휴가 아니며, 종료에 실패하면 바인딩을 유지하고 세션별 지수 백오프(스윕 간격 min(TTL/4, 60)초에서 시작해 최대 15분)로 재시도하며 경고는 한 줄만 남깁니다(세션 id·트레이스백 없음). 내부 DELETE의 Host는 421/404가 아닌 응답을 받은 요청의 값만 쓰고, 없으면 `LEXLINK_ALLOWED_HOSTS`의 첫 항목을 씁니다. 만료된 세션 id로 온 요청은 소유자 포함 모든 토큰에 존재하지 않는 세션과 같은 404를 반환하므로 클라이언트는 새 세션을 시작하면 됩니다. 인증 없음 모드에서도 동작합니다. SSE 세션은 GET 스트림이 곧 세션이라 스트림 종료 시 정리되며 별도 만료가 없습니다. 단일 프로세스 한정입니다.
- 알려진 한계: SSE 스트림이 끝난 뒤에도 mcp의 `SseServerTransport._read_stream_writers` 항목은 mcp가 제거하지 않고(비공개 속성이라 접근하지 않음) 세션당 작은 객체 하나가 남습니다. Host 검증 실패(421)로 끝난 세션 없는 요청은 mcp 안에 id를 알 수 없는 transport를 하나 남길 수 있습니다(인증된 토큰·속도 제한 안에서만 가능). 두 경우 모두 프로세스 재시작으로 정리됩니다. `LEXLINK_SESSION_IDLE_TTL_SEC=0`이면 유휴 만료는 없고 종료 실패한 비정상 세션만 스위퍼가 재시도합니다.
- `mcp`는 `>=1.26.0,<1.27`로 고정되어 있습니다. 세션 해제가 비공개 속성 `_server_instances`와 내부 DELETE 동작에 의존하므로, 상한을 올릴 때는 이 두 동작을 다시 확인하세요.
- 인증 없음 모드(`LEXLINK_ALLOW_NO_AUTH=true`)에서는 모든 요청의 token_id가 `noauth`로 같으므로 세션 바인딩은 아무 효과가 없습니다(세션 ID를 아는 누구나 사용 가능).
- 401 응답은 로그에 남지 않고(인증이 가장 바깥 미들웨어) 속도 제한도 받지 않습니다. uvicorn 액세스 로그에서만 확인할 수 있습니다.
- 도구 호출이 동기 `httpx` 클라이언트를 사용하므로 업스트림이 느리면 이벤트 루프가 막혀 속도 제한 429 응답도 지연될 수 있습니다.
- 이전 형식(요청/응답 병합 로그)을 읽는 `log_processor.py`는 새 형식을 처리하지 않습니다.

## 4. TLS 리버스 프록시

앱은 TLS를 처리하지 않으므로 프록시에서 종료합니다. 스트림(SSE)을 위해 버퍼링을 끄고, 앱은 `127.0.0.1`에만 바인드하세요. 프록시를 쓰는 경우 `LEXLINK_TRUSTED_PROXIES=127.0.0.1`을 설정하면 실제 클라이언트 IP가 로그에 남습니다.

### Caddy

```caddyfile
mcp.example.com {
    reverse_proxy 127.0.0.1:8000 {
        flush_interval -1
        header_up X-Forwarded-For {remote_host}
    }
}
```

### Nginx

```nginx
server {
    listen 443 ssl;
    server_name mcp.example.com;
    # ssl_certificate / ssl_certificate_key 설정 (예: certbot)

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Authorization 헤더는 기본으로 전달됩니다
    }
}
```

`X-Forwarded-For`를 `$remote_addr`로 덮어써 클라이언트가 위조한 값을 이어붙이지 않도록 했습니다.

## 5. systemd 예시

```ini
[Unit]
Description=LexLink MCP Server
After=network.target

[Service]
Type=simple
User=lexlink
WorkingDirectory=/opt/lexlink-ko-mcp
EnvironmentFile=/etc/lexlink.env
ExecStart=/home/lexlink/.local/bin/uv run serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/lexlink.env` (권한 `600`, 소유자 root 또는 서비스 계정; 값은 예시):

```bash
OC=your_registered_oc
TRANSPORT=http
HOST=127.0.0.1
PORT=8000
LEXLINK_AUTH_TOKENS=playmcp:CHANGE_ME_LONG_RANDOM,internal:CHANGE_ME_TOO
LEXLINK_ALLOWED_HOSTS=mcp.example.com
LEXLINK_ALLOWED_ORIGINS=https://mcp.example.com
LEXLINK_TRUSTED_PROXIES=127.0.0.1
LEXLINK_LOG_DIR=/var/log/lexlink
```

토큰은 충분히 긴 무작위 문자열(예: `openssl rand -hex 32`)을 사용하세요. `/var/log/lexlink`는 서비스 계정이 쓸 수 있어야 합니다.

## 6. PlayMCP 인증 없음 등록 주의

PlayMCP를 "인증 없음"으로 등록하려면 `LEXLINK_ALLOW_NO_AUTH=true`가 필요하며, 이 경우 엔드포인트에 도달할 수 있는 누구나 서버의 OC 할당량을 사용할 수 있습니다. 완화 수단은 속도/동시성 제한(이 모드에서는 모든 호출자가 하나의 버킷 `noauth`을 공유), Host 검증, 프록시 단의 추가 제한뿐입니다. 가능하면 토큰 인증을 사용하세요. PlayMCP 등록 절차 자체는 PlayMCP 공식 안내에서 확인하세요. 이 저장소가 아는 것은 아래 요구사항뿐이며 PlayMCP 쪽 변경은 반영되지 않을 수 있습니다.

- 엔드포인트는 도메인이어야 하며 IP 주소는 거절됩니다. IP만 있으면 `1-2-3-4.sslip.io`처럼 점을 대시로 바꾼 sslip.io 도메인을 쓸 수 있습니다.
- 포트는 80/443이므로 8000번 앞에 Nginx 같은 프록시를 둡니다.
- Streamable HTTP(`TRANSPORT=http`, 경로 `/mcp`)를 사용합니다.
- "인증 없음"으로 등록하려면 서버를 `LEXLINK_ALLOW_NO_AUTH=true`로 시작해야 합니다. `LEXLINK_AUTH_TOKENS`만 설정하면 토큰 없는 요청은 401이 됩니다.

등록 양식 예시(값은 예시):

| 항목 | 값 |
|---|---|
| MCP 이름 / 식별자 | LexLink - 한국 법령정보 / lexlink |
| MCP 설명 | 대한민국 법률, 판례, 행정규칙 검색 및 조회를 위한 MCP 서버. law.go.kr 국가법령정보 API 연동. 66개 도구 지원. |
| 대화 예시 | 민법 제20조 내용 알려줘 / 건축법과 관련된 대법원 판례 검색해줘 / 자동차관리법 시행령 검색 |
| 인증 방식 | 인증 없음 (`LEXLINK_ALLOW_NO_AUTH=true` 필요) |
| MCP Endpoint | `https://<도메인>/mcp` |
| 대표 이미지 | `assets/LexLink_logo.png` |

## 7. law.go.kr OC와 고정 IP 등록

서버 오류 힌트(`client.py`)에 따르면 law.go.kr은 OC와 요청 IP를 짝으로 검증하므로 서버의 공인 IP를 open.law.go.kr에 등록해야 하며, 등록되지 않으면 "사용자 정보 검증에 실패하였습니다" 오류가 납니다. 따라서 고정 공인 IP(예: 탄력적 IP)에서 서버를 운영하세요. 등록 화면의 구체적인 메뉴 이름과 절차는 이 저장소에 문서화되어 있지 않으니 [open.law.go.kr](https://open.law.go.kr)에서 직접 확인하세요.

law.go.kr의 일일 호출 한도(quota)는 이 저장소에 문서화되어 있지 않습니다. 한도는 open.law.go.kr 또는 운영 기관에 직접 확인하세요. 서버의 `LEXLINK_RATE_LIMIT_PER_MIN`/`LEXLINK_MAX_CONCURRENCY`는 서버 보호용이며 law.go.kr 한도와 무관합니다.

계정에 따라 일부 API(예: 현행법령 시행일 본문 `eflaw`)를 open.law.go.kr에서 별도로 신청해야 합니다. 신청하지 않은 OC는 `API_NOT_SUBSCRIBED` 오류를 받으며, 이때는 `law_service`나 `eflaw_josub`을 쓰거나 해당 API를 신청하세요. 사용 중인 OC의 신청 상태는 이 문서로 알 수 없습니다.

## 8. EC2 배포 절차 (Ubuntu 기준)

Amazon Linux는 `apt` 대신 `yum`, 사용자 `ec2-user`, Nginx 설정 위치 `/etc/nginx/conf.d/`만 다릅니다.

1. 인스턴스: Ubuntu 22.04 LTS, t3.micro 이상. 보안 그룹은 SSH(22)는 내 IP만, HTTP(80)와 HTTPS(443)는 공개.
2. 탄력적 IP를 할당해 연결하고, 그 IP를 open.law.go.kr에 등록합니다(7장).
3. 의존성 설치:
   ```bash
   sudo apt update && sudo apt install -y python3.12 python3.12-venv git nginx
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
4. 코드 받기:
   ```bash
   git clone https://github.com/rabqatab/LexLink-ko-mcp.git ~/lexlink-ko-mcp
   cd ~/lexlink-ko-mcp && uv sync
   ```
5. 시험 실행 (토큰이 없으면 시작되지 않음):
   ```bash
   OC=<OC> LEXLINK_AUTH_TOKENS=playmcp:<TOKEN> LEXLINK_ALLOWED_HOSTS=<도메인>,localhost:8000 TRANSPORT=http uv run serve
   ```
   시작 로그에 `Endpoint: http://0.0.0.0:8000/mcp`가 나옵니다.
6. Nginx: 4장의 Nginx 예시를 `/etc/nginx/sites-available/lexlink`에 두고(TLS 없이 80번만 쓸 때는 `listen 80;`과 `server_name <도메인>;`) 활성화합니다.
   ```bash
   sudo ln -s /etc/nginx/sites-available/lexlink /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t && sudo systemctl restart nginx
   ```
7. systemd: 5장의 유닛과 환경 파일을 만들고 `sudo systemctl daemon-reload && sudo systemctl enable --now lexlink`. `User=`, `WorkingDirectory=`, `ExecStart=`의 `uv` 경로는 실제 값과 맞춥니다(대소문자 구분).
8. 확인 (Host 헤더는 `LEXLINK_ALLOWED_HOSTS`에 있는 값이어야 하며 아니면 421):
   ```bash
   curl -X POST http://localhost/mcp \
     -H "Host: <도메인>" \
     -H "Authorization: Bearer <TOKEN>" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
   ```
   토큰이 없거나 틀리면 401, 맞으면 `serverInfo`가 담긴 응답이 옵니다.
9. HTTPS: 도메인이 있으면 `sudo certbot --nginx -d <도메인>`(Let's Encrypt). 시험용으로는 `ngrok http 8000`도 쓸 수 있지만 무료 URL은 재시작마다 바뀝니다.

업데이트:

```bash
cd ~/lexlink-ko-mcp && git pull && uv sync && sudo systemctl restart lexlink
```

PlayMCP처럼 응답 크기 제한이 있는 곳에 붙일 때는 환경 파일에 `SLIM_RESPONSE=true`를 추가합니다. 제한 때문에 못 받은 부분은 `jo`, `page`/`display`, `sections="summary"`로 나누어 조회합니다(`truncated_notes`에 안내가 나옵니다).

## 9. 문제 해결

| 증상 | 확인 |
|---|---|
| 기동 시 `HTTP mode requires authentication` | `LEXLINK_AUTH_TOKENS` 또는 `LEXLINK_ALLOW_NO_AUTH=true` 설정 |
| 401 | `Authorization: Bearer <토큰>` 누락/오류. 인증 없음 등록이면 `LEXLINK_ALLOW_NO_AUTH=true`로 시작했는지 |
| 421 | 요청 Host가 `LEXLINK_ALLOWED_HOSTS`에 없음 |
| 429 | 토큰별 속도/동시성 제한 초과 (`Retry-After` 참고) |
| 404 (세션) | 만료되었거나 다른 토큰의 세션. 새 세션을 시작 |
| 503 `too_many_sessions` | `LEXLINK_MAX_SESSIONS` 도달 |
| Nginx 502 | LexLink 서비스가 내려가 있음: `sudo systemctl status lexlink`, `sudo journalctl -u lexlink -n 50` |
| systemd `status=217/USER` | 유닛의 `User=`가 잘못됨 |
| systemd `status=203/EXEC` | `ExecStart=`의 `uv` 경로 또는 프로젝트 경로가 잘못됨 (`which uv`) |
| 포트 8000 사용 중 | `sudo lsof -i :8000`으로 확인 후 정리 |
| "사용자 정보 검증에 실패하였습니다" | 서버 공인 IP가 OC에 등록되지 않음 (7장) |
| PlayMCP "Endpoint URL의 도메인이 유효하지 않습니다" | IP 대신 도메인(sslip.io 등) 사용 |
| PlayMCP "MCP Server 연결 확인에 실패했습니다" | `TRANSPORT=http`, 경로 `/mcp`, 인증 설정, Host 허용 목록 확인 후 8장의 curl로 직접 시험 |
