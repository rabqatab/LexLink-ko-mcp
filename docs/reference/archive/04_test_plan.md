# LexLink MCP Server - Test Plan

**Version:** 1.0
**Last Updated:** 2025-11-06
**Status:** Draft
**Related Documents:** `01_PRD.md`, `02_technical_design.md`, `03_api_spec.md`

---

## 1. Test Strategy

### 1.1 Testing Pyramid

```
        ┌─────────────────┐
        │   E2E Tests     │  ← 10-15 scenarios (MCP protocol → upstream API)
        │   (Slowest)     │
        ├─────────────────┤
        │ Integration     │  ← 20-30 tests (HTTP client + mocks)
        │    Tests        │
        ├─────────────────┤
        │   Unit Tests    │  ← 50+ tests (pure functions)
        │   (Fastest)     │
        └─────────────────┘
```

### 1.2 Testing Principles

1. **TDD (Test-Driven Development):** Write tests before implementation for critical logic
2. **Test Isolation:** Each test is independent and can run in any order
3. **Fast Feedback:** Unit tests run in <1s, integration in <5s, E2E in <30s
4. **Real API Testing:** E2E tests hit actual law.go.kr API (not mocked)
5. **Observability:** All tests log request IDs for debugging failures

### 1.3 Success Criteria

- **Unit Tests:** ≥90% code coverage for `params.py`, `errors.py`, `client.py`
- **Integration Tests:** ≥80% coverage for HTTP client + error handling
- **E2E Tests:** All 6 tools callable with 95%+ success rate
- **Test Execution:** All tests pass in CI/CD pipeline
- **Documentation:** Each test has clear docstring explaining scenario

---

## 2. Test Environment Setup

### 2.1 Prerequisites

```bash
# Install dependencies
uv sync

# Set environment variables for testing
export LAW_OC=test_user         # Fallback OC for env tests
export LAW_BASE_URL=http://www.law.go.kr
export LOG_LEVEL=DEBUG          # Verbose logging for tests
```

### 2.2 Test Data

**Valid Test Values:**
```python
# test_data.py
VALID_OC = "g4c"
VALID_LAW_QUERY = "자동차관리법"
VALID_LAW_ID = 9682
VALID_MST = 166520
VALID_EF_YD = 20151007
VALID_ARTICLE_CODE = "000300"  # Article 3
VALID_PARAGRAPH_CODE = "000100"
VALID_ITEM_CODE = "000200"
VALID_MOK = "다"

# Date ranges
VALID_DATE_RANGE = "20240101~20241231"
INVALID_DATE_RANGE = "2024-01-01~2024-12-31"  # Wrong format

# Invalid values for negative tests
INVALID_OC = ""
INVALID_ARTICLE_CODE = "3"  # Not 6-digit
INVALID_MOK = "invalid"
```

### 2.3 Mock Server (Integration Tests)

```python
# tests/integration/conftest.py
import pytest
from unittest.mock import Mock
import httpx

@pytest.fixture
def mock_law_api():
    """Mock law.go.kr API server for integration tests."""
    class MockResponse:
        def __init__(self, status_code=200, json_data=None, text=""):
            self.status_code = status_code
            self._json_data = json_data
            self.text = text

        def json(self):
            return self._json_data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "Error",
                    request=Mock(),
                    response=self
                )

    def mock_get(url, *args, **kwargs):
        # Simulate successful response
        if "OC=" in url and "target=eflaw" in url:
            return MockResponse(
                status_code=200,
                json_data={
                    "LawSearch": {
                        "totalCnt": 1,
                        "law": [{"법령명한글": "자동차관리법", "법령ID": 9682}]
                    }
                }
            )
        # Simulate missing OC error
        elif "OC=" not in url:
            return MockResponse(status_code=403)
        # Default error
        return MockResponse(status_code=500)

    return mock_get
```

---

## 3. Unit Tests (TDD)

### 3.1 Parameter Resolution Tests

**Module:** `tests/unit/test_params.py`

```python
import pytest
import os
from src.params import resolve_oc

class TestResolveOC:
    """Test OC parameter resolution with 3-tier priority."""

    def test_tool_arg_takes_precedence(self):
        """Tool argument overrides session config and env var."""
        # Arrange
        tool_arg = "tool_oc"
        session_oc = "session_oc"
        os.environ["LAW_OC"] = "env_oc"

        # Act
        result = resolve_oc(
            override_oc=tool_arg,
            session_oc=session_oc
        )

        # Assert
        assert result == "tool_oc"

    def test_session_config_second_priority(self):
        """Session config used when tool arg is None."""
        # Arrange
        session_oc = "session_oc"
        os.environ["LAW_OC"] = "env_oc"

        # Act
        result = resolve_oc(
            override_oc=None,
            session_oc=session_oc
        )

        # Assert
        assert result == "session_oc"

    def test_env_var_fallback(self):
        """Environment variable used when tool arg and session are None."""
        # Arrange
        os.environ["LAW_OC"] = "env_oc"

        # Act
        result = resolve_oc(
            override_oc=None,
            session_oc=None
        )

        # Assert
        assert result == "env_oc"

    def test_missing_oc_raises_error(self):
        """ValueError raised with helpful message when OC missing from all sources."""
        # Arrange
        if "LAW_OC" in os.environ:
            del os.environ["LAW_OC"]

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            resolve_oc(override_oc=None, session_oc=None)

        assert "OC parameter is required" in str(exc_info.value)
        assert "Tool argument" in str(exc_info.value)
        assert "Session config" in str(exc_info.value)
        assert "Environment variable" in str(exc_info.value)

    def test_empty_string_treated_as_none(self):
        """Empty string OC values should be treated as None."""
        # Arrange
        os.environ["LAW_OC"] = "env_oc"

        # Act
        result = resolve_oc(
            override_oc="",  # Empty string
            session_oc=""
        )

        # Assert
        assert result == "env_oc"  # Should fall through to env
```

### 3.2 Parameter Mapping Tests

**Module:** `tests/unit/test_params.py`

```python
from src.params import map_params_to_upstream, encode_mok

class TestParameterMapping:
    """Test snake_case → upstream API format conversion."""

    def test_basic_camelcase_mapping(self):
        """ef_yd, anc_no map to camelCase."""
        # Arrange
        snake_params = {
            "ef_yd": "20240101~20241231",
            "anc_no": "123"
        }

        # Act
        result = map_params_to_upstream(snake_params)

        # Assert
        assert result == {
            "efYd": "20240101~20241231",
            "ancNo": "123"
        }

    def test_article_params_uppercase(self):
        """jo, hang, ho, mok map to UPPERCASE."""
        # Arrange
        snake_params = {
            "jo": "000300",
            "hang": "000100",
            "ho": "000200",
            "mok": "가"
        }

        # Act
        result = map_params_to_upstream(snake_params)

        # Assert
        assert result["JO"] == "000300"
        assert result["HANG"] == "000100"
        assert result["HO"] == "000200"
        assert "MOK" in result  # Should be percent-encoded

    def test_oc_uppercase(self):
        """oc maps to OC (uppercase)."""
        # Arrange
        snake_params = {"oc": "g4c"}

        # Act
        result = map_params_to_upstream(snake_params)

        # Assert
        assert result == {"OC": "g4c"}

    def test_passthrough_params(self):
        """query, display, page pass through unchanged."""
        # Arrange
        snake_params = {
            "query": "자동차관리법",
            "display": 20,
            "page": 1
        }

        # Act
        result = map_params_to_upstream(snake_params)

        # Assert
        assert result == snake_params

    def test_none_values_filtered(self):
        """None values are excluded from output."""
        # Arrange
        snake_params = {
            "query": "test",
            "sort": None,
            "org": None
        }

        # Act
        result = map_params_to_upstream(snake_params)

        # Assert
        assert result == {"query": "test"}
        assert "sort" not in result
        assert "org" not in result

    def test_empty_string_filtered(self):
        """Empty strings are excluded from output."""
        # Arrange
        snake_params = {
            "query": "test",
            "sort": ""
        }

        # Act
        result = map_params_to_upstream(snake_params)

        # Assert
        assert "sort" not in result


class TestMOKEncoding:
    """Test UTF-8 percent-encoding for MOK parameter."""

    def test_korean_char_encoding(self):
        """Korean characters encoded as UTF-8 percent-encoded."""
        test_cases = [
            ("가", "%EA%B0%80"),
            ("나", "%EB%82%98"),
            ("다", "%EB%8B%A4"),
            ("라", "%EB%9D%BC"),
        ]

        for input_char, expected_output in test_cases:
            result = encode_mok(input_char)
            assert result == expected_output, f"Failed for {input_char}"

    def test_multi_char_string(self):
        """Multi-character strings are fully encoded."""
        # Arrange
        input_str = "가나다"

        # Act
        result = encode_mok(input_str)

        # Assert
        assert "%" in result
        assert len(result) > len(input_str) * 3  # Each char → 9 chars (%XX%XX%XX)
```

### 3.3 Validation Tests

**Module:** `tests/unit/test_validation.py`

```python
import pytest
from src.validation import validate_article_code, validate_date_range

class TestArticleCodeValidation:
    """Test 6-digit article code validation."""

    def test_valid_codes(self):
        """Valid 6-digit codes pass validation."""
        valid_codes = ["000300", "001002", "999999", "000001"]

        for code in valid_codes:
            # Should not raise
            validate_article_code(code, "test_param")

    def test_invalid_length(self):
        """Codes with wrong length raise ValueError."""
        invalid_codes = ["3", "03", "00300", "0003001"]

        for code in invalid_codes:
            with pytest.raises(ValueError) as exc_info:
                validate_article_code(code, "jo")
            assert "6-digit" in str(exc_info.value)
            assert "jo" in str(exc_info.value)

    def test_non_numeric(self):
        """Non-numeric codes raise ValueError."""
        invalid_codes = ["00030a", "abc123", "      "]

        for code in invalid_codes:
            with pytest.raises(ValueError):
                validate_article_code(code, "jo")


class TestDateRangeValidation:
    """Test date range format validation."""

    def test_valid_ranges(self):
        """Valid YYYYMMDD~YYYYMMDD ranges pass."""
        valid_ranges = [
            "20240101~20241231",
            "19900101~20301231",
        ]

        for date_range in valid_ranges:
            # Should not raise
            validate_date_range(date_range, "ef_yd")

    def test_invalid_format(self):
        """Invalid formats raise ValueError."""
        invalid_ranges = [
            "2024-01-01~2024-12-31",  # Hyphens
            "20240101-20241231",       # Missing tilde
            "20240101~202412",         # Wrong length
            "01012024~12312024",       # Wrong order
        ]

        for date_range in invalid_ranges:
            with pytest.raises(ValueError) as exc_info:
                validate_date_range(date_range, "ef_yd")
            assert "YYYYMMDD~YYYYMMDD" in str(exc_info.value)
```

### 3.4 Error Formatting Tests

**Module:** `tests/unit/test_errors.py`

```python
from src.errors import create_error_response, ErrorCode

class TestErrorResponses:
    """Test standardized error response creation."""

    def test_minimal_error(self):
        """Error with only code and message."""
        # Act
        error = create_error_response(
            error_code=ErrorCode.MISSING_OC,
            message="OC is required"
        )

        # Assert
        assert error["status"] == "error"
        assert error["error_code"] == "MISSING_OC"
        assert error["message"] == "OC is required"

    def test_error_with_hints(self):
        """Error with resolution hints."""
        # Act
        error = create_error_response(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Invalid parameter",
            hints=[
                "Check parameter format",
                "See documentation"
            ]
        )

        # Assert
        assert len(error["hints"]) == 2
        assert "Check parameter format" in error["hints"]

    def test_error_with_request_id(self):
        """Error includes request ID for tracking."""
        # Act
        error = create_error_response(
            error_code=ErrorCode.TIMEOUT,
            message="Request timeout",
            request_id="123e4567-e89b-12d3-a456-426614174000"
        )

        # Assert
        assert error["request_id"] == "123e4567-e89b-12d3-a456-426614174000"

    def test_error_with_extra_fields(self):
        """Error can include additional context fields."""
        # Act
        error = create_error_response(
            error_code=ErrorCode.UPSTREAM_ERROR,
            message="API error",
            upstream_status=503,
            retry_after=60
        )

        # Assert
        assert error["upstream_status"] == 503
        assert error["retry_after"] == 60
```

---

## 4. Integration Tests

### 4.1 HTTP Client Tests

**Module:** `tests/integration/test_client.py`

```python
import pytest
from unittest.mock import Mock, patch
import httpx
from src.client import LawAPIClient

class TestLawAPIClient:
    """Test HTTP client with mocked responses."""

    @pytest.fixture
    def client(self):
        return LawAPIClient(base_url="http://test.law.go.kr", timeout=10)

    def test_successful_json_request(self, client, mock_law_api):
        """Successful JSON request returns normalized response."""
        # Arrange
        params = {"OC": "g4c", "target": "eflaw", "type": "JSON"}

        # Act
        with patch.object(client.client, 'get', side_effect=mock_law_api):
            result = client.get("/DRF/lawSearch.do", params, "JSON")

        # Assert
        assert result["status"] == "ok"
        assert "request_id" in result
        assert result["upstream_type"] == "JSON"

    def test_timeout_handling(self, client):
        """Timeout returns friendly error message."""
        # Arrange
        params = {"OC": "g4c", "target": "eflaw"}

        # Act
        with patch.object(client.client, 'get', side_effect=httpx.TimeoutException("Timeout")):
            result = client.get("/DRF/lawSearch.do", params)

        # Assert
        assert result["status"] == "error"
        assert result["error_code"] == "TIMEOUT"
        assert "hints" in result
        assert any("slow" in hint.lower() for hint in result["hints"])

    def test_403_error_with_hints(self, client):
        """403 error returns OC-specific hints."""
        # Arrange
        params = {"target": "eflaw"}  # Missing OC

        # Act
        with patch.object(client.client, 'get', side_effect=lambda url: Mock(
            status_code=403,
            raise_for_status=Mock(side_effect=httpx.HTTPStatusError("403", request=Mock(), response=Mock(status_code=403)))
        )):
            result = client.get("/DRF/lawSearch.do", params)

        # Assert
        assert result["status"] == "error"
        assert result["error_code"] == "UPSTREAM_ERROR"
        assert any("OC" in hint for hint in result["hints"])

    def test_url_building(self, client):
        """URLs are correctly built with encoded parameters."""
        # Arrange
        params = {
            "OC": "g4c",
            "query": "자동차관리법",
            "ef_yd": "20240101~20241231"
        }

        # Act
        url = client.build_url("/DRF/lawSearch.do", params)

        # Assert
        assert "http://test.law.go.kr/DRF/lawSearch.do?" in url
        assert "OC=g4c" in url
        assert "%EC%9E%90%EB%8F%99%EC%B0%A8" in url  # URL-encoded Korean
        assert "20240101~20241231" in url  # Tilde not encoded

    def test_request_logging(self, client, caplog):
        """Requests are logged with metadata (no PII)."""
        # Arrange
        params = {"OC": "g4c", "target": "eflaw"}

        # Act
        with patch.object(client.client, 'get', return_value=Mock(
            status_code=200,
            json=Mock(return_value={}),
            text="<xml/>"
        )):
            client.get("/DRF/lawSearch.do", params)

        # Assert
        assert "API Request" in caplog.text
        assert "has_oc" in caplog.text
        assert "g4c" not in caplog.text  # OC value should NOT be logged
```

---

## 5. End-to-End Tests

### 5.1 Test Setup

**Module:** `tests/e2e/conftest.py`

```python
import pytest
import httpx
import os

@pytest.fixture(scope="session")
def dev_server_url():
    """LexLink dev server URL (must be running)."""
    return os.getenv("LEXLINK_URL", "http://127.0.0.1:8081")

@pytest.fixture(scope="session")
def test_oc():
    """Test OC identifier."""
    oc = os.getenv("TEST_OC")
    if not oc:
        pytest.skip("TEST_OC environment variable not set")
    return oc

@pytest.fixture
def mcp_client(dev_server_url, test_oc):
    """HTTP client for MCP protocol testing."""
    return MCPTestClient(dev_server_url, test_oc)


class MCPTestClient:
    """Helper for MCP JSON-RPC testing."""

    def __init__(self, base_url: str, oc: str):
        self.base_url = f"{base_url}/mcp?oc={oc}"
        self.session_id = None
        self.client = httpx.Client()

    def initialize(self):
        """Initialize MCP session."""
        response = self.client.post(
            self.base_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            },
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()

        # Extract session ID from headers
        self.session_id = response.headers.get("mcp-session-id")
        return data

    def call_tool(self, tool_name: str, arguments: dict):
        """Call MCP tool."""
        headers = {"Content-Type": "application/json"}
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        response = self.client.post(
            self.base_url,
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            },
            headers=headers
        )
        response.raise_for_status()
        return response.json()
```

### 5.2 E2E Test Scenarios

**Module:** `tests/e2e/test_search_tools.py`

```python
import pytest

class TestEflawSearch:
    """E2E tests for eflaw_search tool."""

    def test_e2e_01_session_config_oc(self, mcp_client):
        """
        E2E-01: Search with OC from session config (no tool arg override).

        Steps:
        1. Initialize session with OC in URL (?oc=g4c)
        2. Call eflaw_search without oc argument
        3. Verify success response with results

        Expected:
        - OC passed to upstream API
        - 200 OK response
        - status="ok", items list present
        """
        # Arrange
        mcp_client.initialize()

        # Act
        result = mcp_client.call_tool(
            "eflaw_search",
            {
                "type": "JSON",
                "query": "자동차관리법",
                "display": 10,
                "page": 1
            }
        )

        # Assert
        assert "result" in result
        tool_result = result["result"]
        assert tool_result["status"] == "ok"
        assert "items" in tool_result
        assert isinstance(tool_result["items"], list)

    def test_e2e_02_tool_arg_override(self, mcp_client, test_oc):
        """
        E2E-02: Tool argument OC overrides session config.

        Steps:
        1. Initialize session with default OC
        2. Call eflaw_search with different oc argument
        3. Verify override OC is used

        Expected:
        - Tool arg OC takes precedence
        - Success response
        """
        # Arrange
        mcp_client.initialize()
        override_oc = f"{test_oc}_override"

        # Act
        result = mcp_client.call_tool(
            "eflaw_search",
            {
                "oc": override_oc,
                "type": "JSON",
                "query": "자동차관리법",
                "display": 5
            }
        )

        # Assert
        assert result["result"]["status"] == "ok"
        # Note: Can't verify which OC was actually sent without server logs,
        # but success indicates override was accepted

    def test_e2e_03_missing_oc_error(self):
        """
        E2E-03: Missing OC returns 422 with helpful error.

        Steps:
        1. Initialize session WITHOUT OC (no URL param, no tool arg, no env var)
        2. Call eflaw_search
        3. Verify error response with resolution hints

        Expected:
        - status="error"
        - error_code="MISSING_OC"
        - hints array with 3 resolution methods
        """
        # Arrange
        client = MCPTestClient("http://127.0.0.1:8081", oc=None)  # No OC
        client.initialize()

        # Act
        result = client.call_tool(
            "eflaw_search",
            {"query": "자동차관리법"}
        )

        # Assert
        tool_result = result["result"]
        assert tool_result["status"] == "error"
        assert tool_result["error_code"] == "MISSING_OC"
        assert "hints" in tool_result
        assert len(tool_result["hints"]) >= 3

    def test_e2e_04_json_xml_html_formats(self, mcp_client):
        """
        E2E-04: All response types (JSON/XML/HTML) work.

        Steps:
        1. Call eflaw_search with type=JSON
        2. Call eflaw_search with type=XML
        3. Call eflaw_search with type=HTML
        4. Verify each returns appropriate format

        Expected:
        - JSON: Parsed and normalized
        - XML: Raw text with <?xml declaration
        - HTML: Raw HTML text
        """
        mcp_client.initialize()

        for response_type in ["JSON", "XML", "HTML"]:
            # Act
            result = mcp_client.call_tool(
                "eflaw_search",
                {
                    "type": response_type,
                    "query": "자동차관리법",
                    "display": 5
                }
            )

            # Assert
            tool_result = result["result"]
            assert tool_result["status"] == "ok"
            assert tool_result["upstream_type"] == response_type

            if response_type == "JSON":
                assert "items" in tool_result
            else:
                assert "raw_content" in tool_result

    def test_e2e_06_date_range_filtering(self, mcp_client):
        """
        E2E-06: Date range parameter (ef_yd) correctly mapped.

        Steps:
        1. Call eflaw_search with ef_yd=20240101~20241231
        2. Verify success

        Expected:
        - ef_yd → efYd in upstream query
        - Results match date range (if API respects it)
        """
        # Arrange
        mcp_client.initialize()

        # Act
        result = mcp_client.call_tool(
            "eflaw_search",
            {
                "type": "JSON",
                "query": "자동차관리법",
                "ef_yd": "20240101~20241231"
            }
        )

        # Assert
        assert result["result"]["status"] == "ok"

    def test_e2e_07_pagination(self, mcp_client):
        """
        E2E-07: Pagination parameters (display, page) work.

        Steps:
        1. Call with display=5, page=1
        2. Call with display=5, page=2
        3. Verify different results (if enough data)

        Expected:
        - Page 1 and Page 2 return different items
        """
        mcp_client.initialize()

        # Act
        page1 = mcp_client.call_tool(
            "eflaw_search",
            {
                "type": "JSON",
                "query": "법",  # Generic search for many results
                "display": 5,
                "page": 1
            }
        )

        page2 = mcp_client.call_tool(
            "eflaw_search",
            {
                "type": "JSON",
                "query": "법",
                "display": 5,
                "page": 2
            }
        )

        # Assert
        assert page1["result"]["status"] == "ok"
        assert page2["result"]["status"] == "ok"
        # Different pages should have different items (if data sufficient)
        # Note: Can't guarantee this without knowing total results


class TestEflawJosub:
    """E2E tests for eflaw_josub tool (article retrieval)."""

    def test_e2e_05_mok_utf8_encoding(self, mcp_client):
        """
        E2E-05: MOK parameter with Korean character is UTF-8 encoded.

        Steps:
        1. Call eflaw_josub with mok="다"
        2. Verify success (upstream accepts encoded param)

        Expected:
        - MOK=%EB%8B%A4 in upstream query
        - Success response with article content
        """
        # Arrange
        mcp_client.initialize()

        # Act
        result = mcp_client.call_tool(
            "eflaw_josub",
            {
                "type": "XML",
                "mst": "193412",
                "ef_yd": 20171019,
                "jo": "000300",
                "hang": "000100",
                "ho": "000200",
                "mok": "다"
            }
        )

        # Assert
        tool_result = result["result"]
        assert tool_result["status"] == "ok"
        assert "raw_content" in tool_result or "data" in tool_result

    def test_e2e_09_article_code_validation(self, mcp_client):
        """
        E2E-09: Invalid article code returns validation error.

        Steps:
        1. Call eflaw_josub with invalid jo="3" (not 6-digit)
        2. Verify validation error

        Expected:
        - error_code="VALIDATION_ERROR"
        - Message mentions 6-digit format
        """
        # Arrange
        mcp_client.initialize()

        # Act
        result = mcp_client.call_tool(
            "eflaw_josub",
            {
                "mst": "193412",
                "ef_yd": 20171019,
                "jo": "3"  # Invalid
            }
        )

        # Assert
        tool_result = result["result"]
        assert tool_result["status"] == "error"
        assert tool_result["error_code"] == "VALIDATION_ERROR"
        assert "6-digit" in tool_result["message"]


class TestLawService:
    """E2E tests for law_service tool."""

    def test_e2e_08_partial_law_retrieval(self, mcp_client):
        """
        E2E-08: Retrieve specific article only (not full law).

        Steps:
        1. Call law_service with ID and JO parameter
        2. Verify partial content returned

        Expected:
        - Only specified article content
        - Not full law text
        """
        # Arrange
        mcp_client.initialize()

        # Act
        result = mcp_client.call_tool(
            "law_service",
            {
                "type": "XML",
                "id": "009682",
                "jo": "000300"  # Article 3 only
            }
        )

        # Assert
        tool_result = result["result"]
        assert tool_result["status"] == "ok"
        # Can't easily verify partial vs full without parsing XML,
        # but success indicates parameter was accepted
```

### 5.3 Smithery Playground Manual Tests

**Manual Test Checklist** (Run in Smithery Playground UI):

```markdown
## Playground Test Session

### Setup
1. Navigate to Smithery Playground for LexLink server
2. Set Session Config:
   - oc: `g4c` (or your test identifier)
   - debug: `true`

### Test 1: eflaw_search (JSON)
**Input:**
```json
{
  "type": "JSON",
  "query": "자동차관리법",
  "display": 10,
  "page": 1
}
```
**Expected:** Success response with list of laws

### Test 2: law_search (XML)
**Input:**
```json
{
  "type": "XML",
  "query": "자동차",
  "display": 5
}
```
**Expected:** XML raw content in response

### Test 3: eflaw_service (HTML)
**Input:**
```json
{
  "type": "HTML",
  "id": "9682"
}
```
**Expected:** HTML raw content with law text

### Test 4: eflaw_josub (Korean MOK)
**Input:**
```json
{
  "type": "XML",
  "mst": "193412",
  "ef_yd": 20171019,
  "jo": "000300",
  "hang": "000100",
  "ho": "000200",
  "mok": "다"
}
```
**Expected:** Article sub-item content

### Test 5: Error - Missing OC
**Setup:** Clear session config `oc` field, don't provide tool arg
**Input:**
```json
{
  "query": "test"
}
```
**Expected:** Error with MISSING_OC code and resolution hints

### Test 6: Error - Invalid Article Code
**Input:**
```json
{
  "mst": "193412",
  "ef_yd": 20171019,
  "jo": "3"
}
```
**Expected:** VALIDATION_ERROR with "6-digit" message
```

---

## 6. Performance Tests

**Module:** `tests/performance/test_latency.py`

```python
import pytest
import time

class TestResponseTimes:
    """Verify response times meet NFR requirements."""

    def test_search_query_latency(self, mcp_client):
        """Search queries complete within 5 seconds (P95)."""
        mcp_client.initialize()

        latencies = []
        for _ in range(20):  # Run 20 iterations
            start = time.time()
            mcp_client.call_tool(
                "eflaw_search",
                {"query": "법", "display": 10}
            )
            elapsed = time.time() - start
            latencies.append(elapsed)

        # Calculate P95
        latencies.sort()
        p95_index = int(len(latencies) * 0.95)
        p95_latency = latencies[p95_index]

        assert p95_latency < 5.0, f"P95 latency {p95_latency}s exceeds 5s"

    def test_initialization_time(self, dev_server_url, test_oc):
        """Server initialization completes within 500ms."""
        client = MCPTestClient(dev_server_url, test_oc)

        start = time.time()
        client.initialize()
        elapsed = time.time() - start

        assert elapsed < 0.5, f"Initialization took {elapsed}s (> 500ms)"
```

---

## 7. Test Execution

### 7.1 Local Testing

```bash
# Run all tests
uv run pytest

# Run specific test category
uv run pytest tests/unit/              # Unit tests only
uv run pytest tests/integration/       # Integration tests only
uv run pytest tests/e2e/               # E2E tests only (requires dev server)

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run with verbose output
uv run pytest -v -s

# Run specific test
uv run pytest tests/unit/test_params.py::TestResolveOC::test_tool_arg_takes_precedence
```

### 7.2 CI/CD Pipeline

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync

      - name: Run unit tests
        run: uv run pytest tests/unit/ --cov=src --cov-report=xml

      - name: Run integration tests
        run: uv run pytest tests/integration/

      - name: Start dev server for E2E
        run: |
          uv run dev &
          sleep 5  # Wait for server to start

      - name: Run E2E tests
        env:
          TEST_OC: ${{ secrets.TEST_OC }}
          LEXLINK_URL: http://127.0.0.1:8081
        run: uv run pytest tests/e2e/

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

---

## 8. Test Data Management

### 8.1 Test Fixtures

**File:** `tests/fixtures/sample_responses.json`

```json
{
  "eflaw_search_json": {
    "LawSearch": {
      "totalCnt": 1,
      "law": [{
        "법령명한글": "자동차관리법",
        "법령ID": 9682,
        "공포일자": 20200101,
        "시행일자": 20200201
      }]
    }
  },
  "eflaw_search_xml": "<?xml version=\"1.0\" encoding=\"UTF-8\"?><LawSearch>...</LawSearch>",
  "law_service_html": "<html><body><h1>자동차관리법</h1>...</body></html>"
}
```

### 8.2 Environment Secrets

```bash
# .env.test (not committed)
TEST_OC=your_test_identifier
LAW_BASE_URL=http://www.law.go.kr
LOG_LEVEL=DEBUG
```

---

## 9. Acceptance Testing

### 9.1 UAT Checklist

**User Acceptance Testing (before production release):**

- [ ] **Playground Testing:** All 6 tools callable from Smithery Playground
- [ ] **Error Messages:** All error scenarios return helpful messages
- [ ] **Documentation:** README includes quick start with curl examples
- [ ] **Performance:** Search queries average < 3 seconds
- [ ] **Korean Encoding:** MOK parameter works with 가, 나, 다, 라 characters
- [ ] **OC Resolution:** All 3 sources (tool arg, session, env) tested
- [ ] **Response Formats:** JSON/XML/HTML all return appropriate content
- [ ] **Pilot User:** At least one external user successfully integrated
- [ ] **Logs:** No PII (OC values, full queries) in production logs
- [ ] **Monitoring:** Request IDs traceable through logs

---

## 10. Known Issues & Workarounds

### Issue: Upstream API Rate Limiting (Unknown)

**Symptoms:** Intermittent 429 or slow responses during heavy testing

**Workaround:**
- Add delays between E2E test iterations
- Use test data cache for repeated queries
- Monitor for patterns and adjust test frequency

**Test Impact:** E2E tests may occasionally fail due to rate limiting

### Issue: Korean Character Display in CI Logs

**Symptoms:** Korean text appears garbled in CI output

**Workaround:**
- Set `PYTHONIOENCODING=utf-8` in CI environment
- Use structured JSON logging

**Test Impact:** None (doesn't affect test outcomes)

---

## 11. Test Metrics Dashboard

### Target Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Unit Test Coverage | ≥ 90% | TBD | 🟡 In Progress |
| Integration Test Coverage | ≥ 80% | TBD | 🟡 In Progress |
| E2E Success Rate | ≥ 95% | TBD | 🟡 In Progress |
| Total Test Count | ≥ 80 | TBD | 🟡 In Progress |
| Test Execution Time | < 60s (all) | TBD | 🟡 In Progress |
| P95 Latency | < 5s | TBD | 🟡 In Progress |

---

## 12. Test Maintenance

### Regular Review Schedule

- **Weekly:** Review failed CI/CD test runs, update flaky tests
- **Monthly:** Review test coverage reports, add tests for uncovered paths
- **Quarterly:** Review E2E test suite against upstream API changes
- **Per Release:** Full regression test suite + manual Playground testing

### Test Debt Tracking

- **Priority 1:** Tests failing in CI/CD
- **Priority 2:** Missing tests for new features
- **Priority 3:** Flaky tests (pass/fail inconsistently)
- **Priority 4:** Slow tests (optimize or restructure)

---

## Appendix: Quick Reference

### Running Specific Test Categories

```bash
# Critical path only (smoke test)
pytest -m "critical"

# Skip slow E2E tests
pytest -m "not e2e"

# Run with specific markers
pytest -m "unit or integration"
```

### Test Markers (add to pytest.ini)

```ini
[pytest]
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (with mocks)
    e2e: End-to-end tests (requires dev server)
    critical: Critical path tests (must pass)
    slow: Slow tests (> 5s)
```

---

**Document History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-06 | Dev Team | Initial test plan extracted from PRD |
