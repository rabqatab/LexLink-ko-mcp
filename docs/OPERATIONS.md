# LexLink HTTP 서버 운영 가이드

HTTP/SSE 모드(`uv run serve`)를 외부에 노출할 때의 인증, 로깅, 제한, 배포 설정을 설명합니다. stdio 모드는 이 문서의 영향을 받지 않습니다.

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
| `TRANSPORT` | `sse` | `http` 권장 |
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

- 세션은 만든 토큰에 묶입니다(`SessionBindingMiddleware`). 다른 토큰이 `Mcp-Session-Id`(Streamable HTTP) 또는 `session_id` 쿼리(SSE `/messages/`)로 남의 세션을 POST/GET/DELETE 하면 앱을 호출하지 않고, 존재하지 않는 세션과 동일한 404를 돌려주므로 세션 존재 여부도 드러나지 않습니다. 소유자의 DELETE(2xx), SSE 스트림 종료 시 바인딩이 제거됩니다.
- 바인딩은 메모리에 최대 `LEXLINK_MAX_SESSIONS`개(기본 10000)만 보관합니다. 오래된 항목을 쫓아내면 그 세션이 "바인딩 없는 세션"이 되어 다른 토큰이 쓸 수 있으므로, 상한에 도달하면 새 세션 생성을 503(`too_many_sessions`, `Retry-After`)으로 거절합니다(기존 세션은 유지). 클라이언트가 DELETE 없이 사라져도 `LEXLINK_SESSION_IDLE_TTL_SEC`(기본 3600초, `0`이면 끔) 동안 활동이 없으면 서버가 세션 자체를 종료(내부 DELETE)한 뒤 바인딩을 제거해 슬롯이 반환됩니다. 진행 중인 요청이나 열린 GET 스트림이 있는 세션은 유휴가 아니며, 종료에 실패하면 바인딩을 유지하고 다음 스윕(간격 min(TTL/4, 60)초)에서 재시도합니다. 만료된 세션 id로 온 요청은 소유자 포함 모든 토큰에 존재하지 않는 세션과 같은 404를 반환하므로 클라이언트는 새 세션을 시작하면 됩니다. 인증 없음 모드에서도 동작합니다. SSE 세션은 GET 스트림이 곧 세션이라 스트림 종료 시 정리되며 별도 만료가 없습니다. 단일 프로세스 한정입니다.
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

PlayMCP를 "인증 없음"으로 등록하려면 `LEXLINK_ALLOW_NO_AUTH=true`가 필요하며, 이 경우 엔드포인트에 도달할 수 있는 누구나 서버의 OC 할당량을 사용할 수 있습니다. 완화 수단은 속도/동시성 제한(이 모드에서는 모든 호출자가 하나의 버킷 `noauth`을 공유), Host 검증, 프록시 단의 추가 제한뿐입니다. 가능하면 토큰 인증을 사용하세요. PlayMCP 등록 절차 자체는 이 저장소에 문서화되어 있지 않으므로 PlayMCP 공식 안내에서 확인하세요(이 저장소의 `docs/DEPLOYMENT_GUIDE.md`에는 인증 방식 "인증 없음", 도메인 필요, 80/443 포트 요구 정도만 적혀 있습니다).

## 7. law.go.kr OC와 고정 IP 등록

`docs/DEPLOYMENT_GUIDE.md`와 서버 오류 힌트(`client.py`)에 따르면 law.go.kr은 OC와 요청 IP를 짝으로 검증하므로 서버의 공인 IP를 open.law.go.kr에 등록해야 하며, 등록되지 않으면 "사용자 정보 검증에 실패하였습니다" 오류가 납니다. 따라서 고정 공인 IP(예: 탄력적 IP)에서 서버를 운영하세요. 등록 화면의 구체적인 메뉴 이름과 절차는 이 저장소에 문서화되어 있지 않으니 [open.law.go.kr](https://open.law.go.kr)에서 직접 확인하세요.

law.go.kr의 일일 호출 한도(quota)는 이 저장소에 문서화되어 있지 않습니다. 한도는 open.law.go.kr 또는 운영 기관에 직접 확인하세요. 서버의 `LEXLINK_RATE_LIMIT_PER_MIN`/`LEXLINK_MAX_CONCURRENCY`는 서버 보호용이며 law.go.kr 한도와 무관합니다.
