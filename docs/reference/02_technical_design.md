# LexLink MCP Server - Technical Design Document

**Version:** 1.0
**Last Updated:** 2025-11-06
**Status:** Draft
**Related Documents:** `01_PRD.md`, `04_test_plan.md`, `03_api_spec.md`

---

## 1. Overview

This document details the technical architecture and implementation approach for the LexLink MCP server. It covers session configuration, parameter mapping, error handling patterns, and code structure to meet the requirements specified in `01_PRD.md`.

### Design Principles
1. **Explicit over Implicit:** Configuration sources clearly prioritized and documented
2. **Fail Fast with Guidance:** Early validation with actionable error messages
3. **Separation of Concerns:** MCP layer, API client, and data transformation are distinct
4. **Testability First:** All critical logic isolated in pure functions

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Client (Claude/GPT)                  │
└─────────────────────────┬───────────────────────────────────┘
                          │ JSON-RPC (MCP Protocol)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│               Smithery Platform (HTTP Transport)             │
│  - Session Management                                        │
│  - Config Injection (?oc=g4c)                               │
└─────────────────────────┬───────────────────────────────────┘
                          │ FastMCP Protocol
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   LexLink MCP Server                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Server Factory (create_server)                       │  │
│  │  - Receives session_config from Smithery             │  │
│  │  - Registers 6 MCP tools                             │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Tool Layer                                           │  │
│  │  - eflaw_search / law_search (목록 조회)             │  │
│  │  - eflaw_service / law_service (본문 조회)           │  │
│  │  - eflaw_josub / law_josub (조항 조회)               │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Parameter Resolution & Mapping Layer                 │  │
│  │  - resolve_oc() - Priority: arg > session > env     │  │
│  │  - map_params_to_upstream() - snake → camelCase     │  │
│  │  - encode_korean_params() - UTF-8 encoding          │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ HTTP Client Layer                                    │  │
│  │  - Request building                                  │  │
│  │  - Timeout handling (15s)                           │  │
│  │  - Response parsing (HTML/XML/JSON)                 │  │
│  │  - Error normalization                               │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Logging & Observability                              │  │
│  │  - Request metadata (no PII)                         │  │
│  │  - OC presence indicator                             │  │
│  │  - Latency tracking                                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP GET
                          ▼
┌─────────────────────────────────────────────────────────────┐
│        law.go.kr Open API (Upstream Government API)         │
│  - Requires OC parameter (uppercase)                         │
│  - Returns HTML/XML/JSON                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Session Configuration Design

### 3.1 Configuration Schema

**Implementation:**
```python
from pydantic import BaseModel, Field

class LexLinkConfig(BaseModel):
    """
    Session configuration schema for LexLink MCP server.
    Passed via Smithery URL query parameters or UI.
    """
    oc: str = Field(
        description="User identifier (email local part). Required for law.go.kr API. "
                    "Example: g4c@korea.kr → g4c"
    )
    debug: bool = Field(
        default=False,
        description="Enable verbose logging for troubleshooting"
    )
    base_url: str = Field(
        default="http://www.law.go.kr",
        description="Base URL for law.go.kr API (override for testing)"
    )
    http_timeout_s: int = Field(
        default=15,
        ge=5,
        le=60,
        description="HTTP request timeout in seconds"
    )
```

**Design Decisions:**
- **Field naming:** Use snake_case (not camelCase) per Smithery recommendation
- **Avoid reserved words:** `api_key`, `profile`, `config` are Smithery-reserved
- **Required vs Optional:** Only `oc` is required; others have sensible defaults
- **Validation:** Use Pydantic validators for range checks (timeout 5-60s)

### 3.2 Configuration Injection Pattern

**Problem:** Past implementations failed because `create_server()` didn't accept `session_config` parameter.

**Solution (Recommended): Closure Pattern**

```python
from fastmcp import FastMCP
from smithery import smithery

@smithery.server(config_schema=LexLinkConfig)
def create_server(session_config: LexLinkConfig | None = None) -> FastMCP:
    """
    Server factory function. Smithery injects session_config.

    Args:
        session_config: User configuration from Smithery session

    Returns:
        Configured FastMCP server instance
    """
    server = FastMCP("LexLink")

    # Closure captures session_config - no global state needed
    def resolve_oc(override_oc: str | None = None) -> str:
        """
        Resolve OC parameter from multiple sources (priority order).

        Args:
            override_oc: Optional override from tool argument

        Returns:
            Resolved OC value

        Raises:
            ValueError: If OC cannot be resolved from any source
        """
        # Priority 1: Tool argument override
        if override_oc:
            return override_oc

        # Priority 2: Session configuration
        if session_config and session_config.oc:
            return session_config.oc

        # Priority 3: Environment variable
        env_oc = os.getenv("LAW_OC")
        if env_oc:
            return env_oc

        # Fail with helpful message
        raise ValueError(
            "OC parameter is required but not provided. "
            "Please provide it via:\n"
            "  1. Tool argument: oc='your_value'\n"
            "  2. Session config: Set 'oc' in Smithery settings\n"
            "  3. Environment variable: LAW_OC=your_value"
        )

    # Register tools (shown in next section)
    @server.tool()
    def eflaw_search(
        query: str,
        display: int = 20,
        page: int = 1,
        oc: str | None = None,
        type: str = "XML",
        # ... other params
    ) -> dict:
        """Search current laws by effective date."""
        resolved_oc = resolve_oc(oc)  # Closure access to session_config
        # ... implementation
        return {"status": "ok", "items": []}

    return server
```

**Alternative: Global State Pattern (Faster to implement, less clean)**

```python
# Module-level global (avoid if possible)
_SESSION_CONFIG: LexLinkConfig | None = None

@smithery.server(config_schema=LexLinkConfig)
def create_server(session_config: LexLinkConfig | None = None) -> FastMCP:
    global _SESSION_CONFIG
    _SESSION_CONFIG = session_config

    server = FastMCP("LexLink")

    @server.tool()
    def eflaw_search(query: str, oc: str | None = None, ...) -> dict:
        # Access global state
        resolved_oc = oc or (_SESSION_CONFIG.oc if _SESSION_CONFIG else None) or os.getenv("LAW_OC")
        if not resolved_oc:
            return {"status": "error", "error_code": "MISSING_OC", ...}
        # ...

    return server
```

**Recommendation:** Use closure pattern for cleaner testing and no global state pollution.

---

## 4. Parameter Mapping Design

### 4.1 Naming Convention Mapping

**Problem:** MCP tools use snake_case (Python convention), but law.go.kr API uses mixed formats (camelCase, UPPERCASE).

**Solution:** Centralized mapping function

```python
def map_params_to_upstream(snake_params: dict) -> dict:
    """
    Convert snake_case tool parameters to law.go.kr API format.

    Mapping rules:
    - Most params: snake_case → camelCase (ef_yd → efYd)
    - Article params: UPPERCASE (jo → JO, hang → HANG)
    - OC: Always uppercase (oc → OC)

    Args:
        snake_params: Parameters from MCP tool (snake_case)

    Returns:
        Parameters ready for law.go.kr API (original format)

    Example:
        >>> map_params_to_upstream({"ef_yd": "20240101~20241231", "jo": "000300", "oc": "g4c"})
        {"efYd": "20240101~20241231", "JO": "000300", "OC": "g4c"}
    """
    # Define mapping table (extend as needed)
    PARAM_MAP = {
        # Session/auth
        "oc": "OC",

        # Common search params
        "ef_yd": "efYd",      # 시행일자 범위
        "anc_yd": "ancYd",    # 공포일자 범위
        "anc_no": "ancNo",    # 공포번호 범위
        "rr_cls_cd": "rrClsCd",  # 제개정 종류 코드
        "pop_yn": "popYn",    # 팝업 여부
        "ls_chap_no": "lsChapNo",  # 법령체계 장번호

        # Service params (ID/MST uppercase per API convention)
        "id": "ID",
        "mst": "MST",
        "chr_cls_cd": "chrClsCd",

        # Article navigation (UPPERCASE)
        "jo": "JO",          # 조
        "hang": "HANG",      # 항
        "ho": "HO",          # 호
        "mok": "MOK",        # 목 (requires UTF-8 encoding)

        # Pass-through (no change needed)
        "target": "target",
        "type": "type",
        "query": "query",
        "display": "display",
        "page": "page",
        "sort": "sort",
        "date": "date",
        "nb": "nb",
        "org": "org",
        "knd": "knd",
        "gana": "gana",
        "search": "search",
        "nw": "nw",
        "ld": "ld",
        "ln": "ln",
        "lm": "lm",
        "lang": "lang",
    }

    upstream_params = {}
    for snake_key, value in snake_params.items():
        if value is None or value == "":
            continue  # Skip empty values

        upstream_key = PARAM_MAP.get(snake_key, snake_key)

        # Special handling for MOK (UTF-8 encoding)
        if upstream_key == "MOK" and isinstance(value, str):
            upstream_params[upstream_key] = encode_mok(value)
        else:
            upstream_params[upstream_key] = value

    return upstream_params


def encode_mok(value: str) -> str:
    """
    UTF-8 percent-encode MOK parameter (e.g., "다" → "%EB%8B%A4").

    Args:
        value: Korean character for sub-item (가, 나, 다, ...)

    Returns:
        Percent-encoded string
    """
    from urllib.parse import quote
    return quote(value.encode("utf-8"))
```

### 4.2 Parameter Validation

```python
from typing import Any

def validate_article_code(code: str, param_name: str) -> None:
    """
    Validate 6-digit article/paragraph/item codes.

    Args:
        code: Code to validate (e.g., "000300")
        param_name: Parameter name for error message

    Raises:
        ValueError: If code format is invalid
    """
    if not code.isdigit() or len(code) != 6:
        raise ValueError(
            f"{param_name} must be 6-digit numeric string (e.g., '000300'), got: {code}"
        )


def validate_date_range(date_range: str, param_name: str) -> None:
    """
    Validate date range format (YYYYMMDD~YYYYMMDD).

    Args:
        date_range: Date range string
        param_name: Parameter name for error message

    Raises:
        ValueError: If format is invalid
    """
    import re
    pattern = r"^\d{8}~\d{8}$"
    if not re.match(pattern, date_range):
        raise ValueError(
            f"{param_name} must be in format YYYYMMDD~YYYYMMDD, got: {date_range}"
        )
```

---

## 5. HTTP Client Design

### 5.1 Request Building

```python
import httpx
from typing import Literal

class LawAPIClient:
    """HTTP client for law.go.kr API."""

    def __init__(self, base_url: str, timeout: int = 15):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def build_url(self, endpoint: str, params: dict) -> str:
        """
        Build complete URL with query parameters.

        Args:
            endpoint: API endpoint path (e.g., "/DRF/lawSearch.do")
            params: Query parameters (already mapped to upstream format)

        Returns:
            Complete URL with encoded query string
        """
        from urllib.parse import urlencode
        query_string = urlencode(params, safe="~")  # Don't encode tilde in date ranges
        return f"{self.base_url}{endpoint}?{query_string}"

    def get(
        self,
        endpoint: str,
        params: dict,
        response_type: Literal["HTML", "XML", "JSON"] = "XML"
    ) -> dict:
        """
        Execute GET request to law.go.kr API.

        Args:
            endpoint: API endpoint
            params: Query parameters (must include OC)
            response_type: Expected response format

        Returns:
            Normalized response dict with status, data, or error

        Raises:
            httpx.TimeoutException: If request exceeds timeout
            httpx.HTTPStatusError: If response status is error
        """
        import uuid
        import time

        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Ensure type parameter is set
        params["type"] = response_type

        url = self.build_url(endpoint, params)

        # Log request (no PII)
        logger.info(
            "API Request",
            extra={
                "request_id": request_id,
                "endpoint": endpoint,
                "has_oc": "OC" in params,  # Boolean, not value
                "response_type": response_type,
            }
        )

        try:
            response = self.client.get(url)
            response.raise_for_status()

            elapsed = time.time() - start_time
            logger.info(
                "API Response",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "elapsed_ms": int(elapsed * 1000),
                }
            )

            # Parse response based on type
            if response_type == "JSON":
                return self._parse_json_response(response, request_id)
            elif response_type == "XML":
                return self._passthrough_response(response, request_id, "XML")
            else:  # HTML
                return self._passthrough_response(response, request_id, "HTML")

        except httpx.TimeoutException:
            logger.error("API Timeout", extra={"request_id": request_id})
            return {
                "status": "error",
                "request_id": request_id,
                "error_code": "TIMEOUT",
                "message": f"Request to law.go.kr timed out after {self.timeout}s",
                "hints": [
                    "The upstream API may be slow or unavailable",
                    "Try reducing the query scope (fewer results)",
                    "Retry after a few seconds"
                ]
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                "API HTTP Error",
                extra={
                    "request_id": request_id,
                    "status_code": e.response.status_code
                }
            )
            return {
                "status": "error",
                "request_id": request_id,
                "error_code": "UPSTREAM_ERROR",
                "message": f"law.go.kr API returned error: {e.response.status_code}",
                "upstream_status": e.response.status_code,
                "hints": self._get_error_hints(e.response.status_code)
            }

    def _parse_json_response(self, response: httpx.Response, request_id: str) -> dict:
        """Parse and normalize JSON response."""
        data = response.json()
        # Apply normalization (see 03_api_spec.md for schema)
        return {
            "status": "ok",
            "request_id": request_id,
            "upstream_type": "JSON",
            "data": data  # Normalized in actual implementation
        }

    def _passthrough_response(
        self,
        response: httpx.Response,
        request_id: str,
        format: str
    ) -> dict:
        """Return HTML/XML as-is for client parsing."""
        return {
            "status": "ok",
            "request_id": request_id,
            "upstream_type": format,
            "raw_content": response.text
        }

    def _get_error_hints(self, status_code: int) -> list[str]:
        """Provide contextual hints based on HTTP status."""
        hints = {
            403: [
                "Check that OC parameter is provided and valid",
                "Verify OC format: email local part only (g4c@korea.kr → g4c)",
                "Check if your IP is blocked by law.go.kr"
            ],
            404: [
                "Verify the law ID or MST exists",
                "Check endpoint URL is correct"
            ],
            500: [
                "law.go.kr internal error - not your fault",
                "Retry after a few seconds",
                "Try a different query to isolate issue"
            ]
        }
        return hints.get(status_code, ["Unexpected error - check logs for details"])
```

---

## 6. Tool Implementation Template

### 6.1 Search Tool Example

```python
@server.tool()
def eflaw_search(
    query: str,
    display: int = 20,
    page: int = 1,
    oc: str | None = None,
    type: str = "XML",
    sort: str | None = None,
    ef_yd: str | None = None,
    org: str | None = None,
    # ... additional params per 03_api_spec.md
) -> dict:
    """
    Search current laws by effective date.

    Args:
        query: Search keyword (law name or content)
        display: Number of results per page (max 100)
        page: Page number (1-based)
        oc: Optional OC override (defaults to session config or env)
        type: Response format (HTML, XML, JSON)
        sort: Sort order (lasc, ldes, dasc, ddes, nasc, ndes, efasc, efdes)
        ef_yd: Effective date range (YYYYMMDD~YYYYMMDD)
        org: Ministry code filter

    Returns:
        Search results with law list or error

    Examples:
        >>> eflaw_search(query="자동차관리법", display=10)
        {"status": "ok", "items": [...]}
    """
    try:
        # 1. Resolve OC (closure has access to session_config)
        resolved_oc = resolve_oc(oc)

        # 2. Build parameter dict (snake_case)
        snake_params = {
            "oc": resolved_oc,
            "target": "eflaw",
            "type": type,
            "query": query,
            "display": display,
            "page": page,
        }

        # Add optional params
        if sort:
            snake_params["sort"] = sort
        if ef_yd:
            validate_date_range(ef_yd, "ef_yd")
            snake_params["ef_yd"] = ef_yd
        if org:
            snake_params["org"] = org

        # 3. Map to upstream format
        upstream_params = map_params_to_upstream(snake_params)

        # 4. Execute request
        api_client = LawAPIClient(
            base_url=session_config.base_url if session_config else "http://www.law.go.kr",
            timeout=session_config.http_timeout_s if session_config else 15
        )

        return api_client.get("/DRF/lawSearch.do", upstream_params, type)

    except ValueError as e:
        # Configuration or validation error
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": str(e)
        }
    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error in eflaw_search")
        return {
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": f"Unexpected error: {str(e)}"
        }
```

### 6.2 Service Tool Example (Article Retrieval)

```python
@server.tool()
def eflaw_josub(
    mst: str,
    ef_yd: int,
    jo: str,
    hang: str | None = None,
    ho: str | None = None,
    mok: str | None = None,
    oc: str | None = None,
    type: str = "XML"
) -> dict:
    """
    Retrieve specific article/paragraph/item/sub-item from law (effective date version).

    Args:
        mst: Law sequence identifier
        ef_yd: Effective date (YYYYMMDD)
        jo: Article code (6-digit, e.g., "000300" for Article 3)
        hang: Optional paragraph code (6-digit)
        ho: Optional item code (6-digit)
        mok: Optional sub-item (Korean char: 가, 나, 다, ...)
        oc: Optional OC override
        type: Response format

    Returns:
        Article content or error
    """
    try:
        resolved_oc = resolve_oc(oc)

        # Validate article code format
        validate_article_code(jo, "jo")
        if hang:
            validate_article_code(hang, "hang")
        if ho:
            validate_article_code(ho, "ho")

        snake_params = {
            "oc": resolved_oc,
            "target": "eflawjosub",
            "type": type,
            "mst": mst,
            "ef_yd": ef_yd,
            "jo": jo,
        }

        if hang:
            snake_params["hang"] = hang
        if ho:
            snake_params["ho"] = ho
        if mok:
            snake_params["mok"] = mok  # Will be UTF-8 encoded in mapping

        upstream_params = map_params_to_upstream(snake_params)

        api_client = LawAPIClient(
            base_url=session_config.base_url if session_config else "http://www.law.go.kr",
            timeout=session_config.http_timeout_s if session_config else 15
        )

        return api_client.get("/DRF/lawService.do", upstream_params, type)

    except ValueError as e:
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": str(e)
        }
```

---

## 7. Error Handling Strategy

### 7.1 Error Code Taxonomy

```python
class ErrorCode:
    """Standardized error codes for LexLink."""
    MISSING_OC = "MISSING_OC"           # OC not provided
    VALIDATION_ERROR = "VALIDATION_ERROR"  # Parameter validation failed
    TIMEOUT = "TIMEOUT"                 # Request timeout
    UPSTREAM_ERROR = "UPSTREAM_ERROR"   # law.go.kr API error
    INTERNAL_ERROR = "INTERNAL_ERROR"   # Unexpected server error
```

### 7.2 Error Response Format

```python
def create_error_response(
    error_code: str,
    message: str,
    hints: list[str] | None = None,
    request_id: str | None = None,
    **extra
) -> dict:
    """
    Create standardized error response.

    Args:
        error_code: Error code from ErrorCode class
        message: Human-readable error message
        hints: Optional list of resolution suggestions
        request_id: Optional request ID for tracking
        **extra: Additional context fields

    Returns:
        Error response dict
    """
    response = {
        "status": "error",
        "error_code": error_code,
        "message": message,
    }

    if hints:
        response["hints"] = hints
    if request_id:
        response["request_id"] = request_id

    response.update(extra)
    return response
```

---

## 8. Logging & Observability

### 8.1 Logging Configuration

```python
import logging
import json

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }

        # Add extra fields from record
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(debug: bool = False):
    """Configure logging for LexLink server."""
    level = logging.DEBUG if debug else logging.INFO

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    logger = logging.getLogger("lexlink")
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger
```

### 8.2 Request Logging Template

```python
# Log request start
logger.info(
    "MCP Tool Called",
    extra={
        "tool_name": "eflaw_search",
        "session_id": ctx.session_id if ctx else None,
        "has_oc_override": oc is not None,
        "query_length": len(query),
    }
)

# Log parameter resolution
logger.debug(
    "OC Resolved",
    extra={
        "source": "tool_arg" if oc else ("session" if session_config else "env"),
        "has_value": bool(resolved_oc),
    }
)

# Log API call
logger.info(
    "Upstream API Call",
    extra={
        "request_id": request_id,
        "endpoint": "/DRF/lawSearch.do",
        "has_oc": "OC" in upstream_params,
        "param_count": len(upstream_params),
    }
)

# Log response
logger.info(
    "Tool Response",
    extra={
        "request_id": request_id,
        "status": "ok",
        "result_count": len(results.get("items", [])),
        "elapsed_ms": elapsed_time,
    }
)
```

---

## 9. Testing Strategy (Summary)

**Detailed specifications in `04_test_plan.md`**

### Unit Testing Focus
- `resolve_oc()` priority order
- `map_params_to_upstream()` all mappings
- `encode_mok()` UTF-8 encoding
- `validate_article_code()` edge cases
- Error response formatting

### Integration Testing Focus
- HTTP client with mock server
- Timeout handling
- Error status code handling
- Response parsing (JSON/XML/HTML)

### E2E Testing Focus
- Full MCP protocol flow
- Session config injection
- All 6 tools with real API
- Error scenarios

---

## 10. Deployment Considerations

### 10.1 Environment Variables

```bash
# Optional overrides (session config takes precedence)
LAW_OC=g4c                    # Fallback OC identifier
LAW_BASE_URL=http://www.law.go.kr  # API base URL
LAW_TIMEOUT=15                # HTTP timeout in seconds
LOG_LEVEL=INFO                # Logging level
```

### 10.2 Smithery Configuration

```yaml
# smithery.yaml
name: lexlink-ko-mcp
version: 1.0.0
config_schema: LexLinkConfig
entry_point: src.server:create_server
```

### 10.3 Performance Tuning

- **Connection pooling:** Use `httpx.Client` instance per server (not per request)
- **Timeout tuning:** 15s default, configurable via session
- **Response size limits:** Consider streaming for large HTML/XML responses
- **Caching:** Consider Redis for frequently accessed laws (Phase 2)

---

## 11. Security Considerations

### 11.1 Input Validation
- Validate all user inputs before passing to upstream API
- Sanitize query strings to prevent injection
- Limit parameter lengths to prevent DoS

### 11.2 PII Protection
- Never log actual OC values (only presence indicator)
- Never log full query strings (may contain sensitive terms)
- Mask session IDs in non-debug logs

### 11.3 Rate Limiting
- Respect upstream API limits (implement client-side limiting)
- Return friendly errors when rate limited
- Consider exponential backoff for retries

---

## 12. Migration from Previous Implementation

### Issues to Fix
1. **OC not passed:** Ensure `create_server(session_config)` signature
2. **Case sensitivity:** Map `oc` → `OC` in upstream params
3. **Context injection:** Use `ctx: Context` without default value
4. **Error messages:** Replace generic errors with structured responses

### Migration Checklist
- [ ] Update `create_server()` to accept `session_config`
- [ ] Implement `resolve_oc()` with 3-tier priority
- [ ] Add `map_params_to_upstream()` with PARAM_MAP
- [ ] Replace all error returns with structured format
- [ ] Add request logging with OC presence indicator
- [ ] Validate all article codes (6-digit format)
- [ ] UTF-8 encode MOK parameter
- [ ] Test all 6 tools in Smithery Playground

---

## 13. Future Architecture Enhancements

### Phase 2
- **Async HTTP client:** Replace `httpx.Client` with `httpx.AsyncClient`
- **Response streaming:** Stream large HTML/XML responses
- **Smart caching:** Cache by query hash with TTL
- **Circuit breaker:** Fail fast when upstream is down

### Phase 3
- **Multi-API support:** Integrate precedent search, admin rules APIs
- **GraphQL layer:** Expose unified legal data graph
- **WebSocket support:** Real-time law update notifications

---

## Appendix: Reference Implementation Checklist

- [ ] `src/config.py` - LexLinkConfig schema
- [ ] `src/server.py` - create_server() factory with closure
- [ ] `src/params.py` - resolve_oc(), map_params_to_upstream()
- [ ] `src/client.py` - LawAPIClient class
- [ ] `src/tools/` - 6 tool implementations
- [ ] `src/errors.py` - Error codes and response builders
- [ ] `src/logging.py` - Structured logging setup
- [ ] `tests/unit/` - Pure function tests
- [ ] `tests/integration/` - HTTP client tests
- [ ] `tests/e2e/` - Full MCP protocol tests

---

**Document History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-06 | Dev Team | Initial technical design extracted from PRD |
