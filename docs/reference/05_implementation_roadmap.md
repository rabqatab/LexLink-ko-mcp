# LexLink Implementation Roadmap

**Generated:** 2025-11-06
**Purpose:** Gap analysis between 04_test_plan.md requirements and current project state

---

## Current Project Status

**Project Type:** Smithery "Hello World" template
**Current Module:** `hello_server` (needs replacement with `lexlink`)
**Tests:** None (0% coverage)
**Documentation:** ✅ Complete (PRD, Technical Design, Test Plan, API Spec)

---

## 📋 Document Alignment Status

### ✅ Complete Documentation
All planning documents exist and are aligned:

| Document | Status | Purpose |
|----------|--------|---------|
| `01_PRD.md` | ✅ Complete | Product requirements and business goals |
| `02_technical_design.md` | ✅ Complete | Architecture, patterns, code structure |
| `04_test_plan.md` | ✅ Complete | TDD specs, E2E scenarios, test fixtures |
| `03_api_spec.md` | ✅ Complete | law.go.kr API endpoint documentation |

**Cross-references:** All documents properly reference each other ✅

---

## 🚧 Implementation Gaps

### Phase 1: Project Structure Setup

#### 1.1 Configuration Files (Need Updates)

**`pyproject.toml`** - ⚠️ Needs major updates
```diff
[project]
- name = "hello-server"
+ name = "lexlink-ko-mcp"
- description = "An MCP server built with Smithery"
+ description = "MCP server for Korean National Law Information API"
authors = [
-   {name = "Your Name", email = "your.email@example.com"}
+   {name = "LexLink Team", email = "minhan.nick.cho@gmail.com"}
]

requires-python = ">=3.10"
dependencies = [
    "mcp>=1.15.0",
    "smithery>=0.4.2",
+   "httpx>=0.27.0",
+   "pydantic>=2.0.0",
]

+ [tool.pytest.ini_options]
+ testpaths = ["tests"]
+ python_files = ["test_*.py"]
+ python_classes = ["Test*"]
+ python_functions = ["test_*"]
+ markers = [
+     "unit: Unit tests (fast, isolated)",
+     "integration: Integration tests (with mocks)",
+     "e2e: End-to-end tests (requires dev server)",
+     "critical: Critical path tests (must pass)",
+     "slow: Slow tests (> 5s)",
+ ]

[tool.smithery]
- server = "hello_server.server:create_server"
+ server = "lexlink.server:create_server"
log_level = "warning"
```

**`smithery.yaml`** - ⚠️ Minimal, may need expansion
```yaml
runtime: python
# Consider adding:
# name: lexlink-ko-mcp
# description: Korean National Law Information API via MCP
```

**`pytest.ini`** - ❌ Missing (create new)
```ini
[pytest]
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (with mocks)
    e2e: End-to-end tests (requires dev server)
    critical: Critical path tests (must pass)
    slow: Slow tests (> 5s)

testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
```

**`.env.test`** - ❌ Missing (create for testing)
```bash
# Test environment configuration
LAW_OC=test_user
LAW_BASE_URL=http://www.law.go.kr
LOG_LEVEL=DEBUG
PYTHONIOENCODING=utf-8
```

**`.env.example`** - ❌ Missing (create for documentation)
```bash
# Example environment configuration
# Copy to .env and fill in your values

# Required: Your law.go.kr API identifier (email local part)
LAW_OC=your_id_here

# Optional overrides
LAW_BASE_URL=http://www.law.go.kr
LAW_TIMEOUT=15
LOG_LEVEL=INFO
```

**`README.md`** - ⚠️ Needs complete rewrite for LexLink
- Replace "Hello World" instructions with LexLink setup
- Add OC configuration instructions
- Link to docs/ for detailed documentation
- Include quick start examples with actual law queries

---

### Phase 2: Source Code Implementation

#### 2.1 Module Restructure

**Current:** `src/hello_server/` (template)
**Target:** `src/lexlink/` (law API server)

**Action:** Rename/refactor module
```bash
# Rename module
mv src/hello_server src/lexlink

# Update __init__.py to expose key components
```

#### 2.2 Core Modules to Create

Referenced in `04_test_plan.md` with 90%+ coverage requirement:

##### **`src/lexlink/config.py`** - ❌ Missing
```python
"""Session configuration schema."""
from pydantic import BaseModel, Field

class LexLinkConfig(BaseModel):
    oc: str = Field(description="User identifier (email local part)")
    debug: bool = Field(default=False, description="Enable verbose logging")
    base_url: str = Field(default="http://www.law.go.kr", description="API base URL")
    http_timeout_s: int = Field(default=15, ge=5, le=60, description="HTTP timeout")
```

Referenced in:
- `04_test_plan.md`: Line 37 (unit test coverage target)
- `02_technical_design.md`: Section 3.1 (configuration schema)
- `01_PRD.md`: FR11, FR12 (session config requirements)

##### **`src/lexlink/params.py`** - ❌ Missing
```python
"""Parameter resolution and mapping."""
import os
from typing import Optional

def resolve_oc(
    override_oc: Optional[str] = None,
    session_oc: Optional[str] = None
) -> str:
    """Resolve OC from tool arg > session > env."""
    # Implementation per 02_technical_design.md section 3.2
    pass

def map_params_to_upstream(snake_params: dict) -> dict:
    """Convert snake_case to law.go.kr API format."""
    # Implementation per 02_technical_design.md section 4.1
    pass

def encode_mok(value: str) -> str:
    """UTF-8 percent-encode MOK parameter."""
    # Implementation per 02_technical_design.md section 4.1
    pass
```

Referenced in:
- `04_test_plan.md`: Lines 37, 139-358 (unit tests TestResolveOC, TestParameterMapping, TestMOKEncoding)
- `02_technical_design.md`: Section 4 (parameter mapping design)
- `01_PRD.md`: FR2, FR4, FR6 (OC resolution, encoding, mapping)

##### **`src/lexlink/validation.py`** - ❌ Missing
```python
"""Parameter validation functions."""

def validate_article_code(code: str, param_name: str) -> None:
    """Validate 6-digit article codes."""
    # Implementation per 02_technical_design.md section 4.2
    pass

def validate_date_range(date_range: str, param_name: str) -> None:
    """Validate YYYYMMDD~YYYYMMDD format."""
    # Implementation per 02_technical_design.md section 4.2
    pass
```

Referenced in:
- `04_test_plan.md`: Lines 359-419 (unit tests TestArticleCodeValidation, TestDateRangeValidation)
- `02_technical_design.md`: Section 4.2 (parameter validation)
- `01_PRD.md`: FR9 (article code handling)

##### **`src/lexlink/client.py`** - ❌ Missing
```python
"""HTTP client for law.go.kr API."""
import httpx
from typing import Literal

class LawAPIClient:
    """HTTP client for law.go.kr API."""

    def __init__(self, base_url: str, timeout: int = 15):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def build_url(self, endpoint: str, params: dict) -> str:
        """Build complete URL with encoded parameters."""
        # Implementation per 02_technical_design.md section 5.1
        pass

    def get(self, endpoint: str, params: dict, response_type: str = "XML") -> dict:
        """Execute GET request with error handling."""
        # Implementation per 02_technical_design.md section 5.1
        pass
```

Referenced in:
- `04_test_plan.md`: Lines 37, 496-598 (integration tests TestLawAPIClient)
- `02_technical_design.md`: Section 5 (HTTP client design)
- `01_PRD.md`: NFR1, NFR3, NFR4 (performance, reliability)

##### **`src/lexlink/errors.py`** - ❌ Missing
```python
"""Error codes and response builders."""

class ErrorCode:
    MISSING_OC = "MISSING_OC"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

def create_error_response(
    error_code: str,
    message: str,
    hints: list[str] | None = None,
    request_id: str | None = None,
    **extra
) -> dict:
    """Create standardized error response."""
    # Implementation per 02_technical_design.md section 7
    pass
```

Referenced in:
- `04_test_plan.md`: Lines 37, 426-472 (unit tests TestErrorResponses)
- `02_technical_design.md`: Section 7 (error handling strategy)
- `01_PRD.md`: FR5 (actionable error messages)

##### **`src/lexlink/logging_setup.py`** - ❌ Missing
```python
"""Structured logging configuration."""
import logging
import json

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    # Implementation per 02_technical_design.md section 8.1
    pass

def setup_logging(debug: bool = False) -> logging.Logger:
    """Configure logging for LexLink server."""
    # Implementation per 02_technical_design.md section 8.1
    pass
```

Referenced in:
- `02_technical_design.md`: Section 8 (logging & observability)
- `01_PRD.md`: FR7, NFR8 (logging without PII)

##### **`src/lexlink/server.py`** - ❌ Missing (replace hello_server/server.py)
```python
"""Main MCP server factory."""
from mcp.server.fastmcp import FastMCP, Context
from smithery.decorators import smithery
from .config import LexLinkConfig
from .params import resolve_oc, map_params_to_upstream
from .client import LawAPIClient
# ... imports

@smithery.server(config_schema=LexLinkConfig)
def create_server(session_config: LexLinkConfig | None = None) -> FastMCP:
    """Create LexLink MCP server with session config."""
    server = FastMCP("LexLink")

    # Closure pattern for OC resolution
    def _resolve_oc(override: str | None = None) -> str:
        return resolve_oc(override, session_config.oc if session_config else None)

    # Register 6 tools (see tools/ directory)
    # ...

    return server
```

Referenced in:
- `04_test_plan.md`: Lines 600+ (E2E tests initialize server)
- `02_technical_design.md`: Section 3.2 (session config injection)
- `01_PRD.md`: FR1, FR11, FR12 (tools, session config, context injection)
- `pyproject.toml`: Line 25 (entry point)

##### **`src/lexlink/tools/`** - ❌ Missing directory
Six tool modules (one per endpoint):
- `eflaw_search.py` - Search laws by effective date
- `eflaw_service.py` - Retrieve law by effective date
- `law_search.py` - Search laws by announcement date
- `law_service.py` - Retrieve law by announcement date
- `eflaw_josub.py` - Query article/paragraph (effective)
- `law_josub.py` - Query article/paragraph (announcement)

OR single file:
- `tools.py` - All 6 tools in one module

Referenced in:
- `04_test_plan.md`: E2E tests (lines 600+)
- `02_technical_design.md`: Section 6 (tool implementation)
- `01_PRD.md`: FR1 (6 MCP tools requirement)
- `03_api_spec.md`: All sections (endpoint specs)

---

### Phase 3: Test Suite Implementation

#### 3.1 Test Directory Structure

**All missing** - Create complete test hierarchy per `04_test_plan.md`:

```
tests/
├── __init__.py
├── unit/
│   ├── __init__.py
│   ├── test_params.py          ← Lines 139-358 in 04_test_plan.md
│   ├── test_validation.py      ← Lines 359-419
│   └── test_errors.py           ← Lines 426-472
├── integration/
│   ├── __init__.py
│   ├── conftest.py              ← Lines 86-135 (mock fixtures)
│   └── test_client.py           ← Lines 496-598
├── e2e/
│   ├── __init__.py
│   ├── conftest.py              ← Lines 600-653 (MCPTestClient)
│   └── test_search_tools.py    ← Lines 655-898
├── performance/
│   ├── __init__.py
│   └── test_latency.py          ← Lines 950-1000 (performance tests)
└── fixtures/
    └── sample_responses.json    ← Lines 1050+ (test data)
```

#### 3.2 Test Files to Create

##### **`tests/unit/test_params.py`** - ❌ Missing
Contains 3 test classes:
- `TestResolveOC` (6 tests)
- `TestParameterMapping` (6 tests)
- `TestMOKEncoding` (2 tests)

Spec: Lines 139-358 in `04_test_plan.md`
Coverage target: 90%+ for `src/lexlink/params.py`

##### **`tests/unit/test_validation.py`** - ❌ Missing
Contains 2 test classes:
- `TestArticleCodeValidation` (3 tests)
- `TestDateRangeValidation` (2 tests)

Spec: Lines 359-419 in `04_test_plan.md`
Coverage target: 90%+ for `src/lexlink/validation.py`

##### **`tests/unit/test_errors.py`** - ❌ Missing
Contains 1 test class:
- `TestErrorResponses` (4 tests)

Spec: Lines 426-472 in `04_test_plan.md`
Coverage target: 90%+ for `src/lexlink/errors.py`

##### **`tests/integration/conftest.py`** - ❌ Missing
Mock server fixtures:
- `mock_law_api()` - Returns MockResponse for various scenarios

Spec: Lines 86-135 in `04_test_plan.md`

##### **`tests/integration/test_client.py`** - ❌ Missing
Contains 1 test class:
- `TestLawAPIClient` (6 tests)

Spec: Lines 496-598 in `04_test_plan.md`
Coverage target: 80%+ for HTTP client logic

##### **`tests/e2e/conftest.py`** - ❌ Missing
MCP protocol test client:
- `MCPTestClient` class
- `dev_server_url`, `test_oc`, `mcp_client` fixtures

Spec: Lines 600-653 in `04_test_plan.md`

##### **`tests/e2e/test_search_tools.py`** - ❌ Missing
Contains 3 test classes:
- `TestEflawSearch` (7 E2E scenarios)
- `TestEflawJosub` (2 E2E scenarios)
- `TestLawService` (1 E2E scenario)

Spec: Lines 655-898 in `04_test_plan.md`
Success target: 95%+ pass rate

##### **`tests/performance/test_latency.py`** - ❌ Missing
Contains 1 test class:
- `TestResponseTimes` (2 performance tests)

Spec: Lines 950-1000 in `04_test_plan.md`
Target: P95 < 5s, initialization < 500ms

##### **`tests/fixtures/sample_responses.json`** - ❌ Missing
Sample API responses for testing:
- `eflaw_search_json`
- `eflaw_search_xml`
- `law_service_html`

Spec: Lines 1050+ in `04_test_plan.md`

---

### Phase 4: CI/CD and Automation

#### 4.1 GitHub Actions Workflow

**`.github/workflows/test.yml`** - ❌ Missing

Spec: Lines 1100-1150 in `04_test_plan.md`

```yaml
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
          sleep 5
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

**Required GitHub Secrets:**
- `TEST_OC` - Valid law.go.kr OC identifier for E2E tests

---

## 📊 Implementation Priority Matrix

### Priority 1: Critical Path (Week 1) ✅ **COMPLETE**
**Goal:** Basic server functional with session config

1. ✅ Update `pyproject.toml` (project name, dependencies)
2. ✅ Create `src/lexlink/config.py` (LexLinkConfig)
3. ✅ Create `src/lexlink/params.py` (resolve_oc, mapping)
4. ✅ Create `src/lexlink/server.py` (with Context injection pattern)
5. ✅ Create two tools (`eflaw_search`, `law_search`) as proof of concept
6. ✅ Create `.env.example` and `.env.test`
7. ⚠️ Update `README.md` with LexLink setup instructions (PARTIAL - needs expansion)

**Validation:** ✅ E2E tests passing 5/5 (100%) WITHOUT environment variable

### Priority 2: Core Functionality (Week 2) ⚠️ **IN PROGRESS**
**Goal:** All 6 tools working, basic error handling

8. ✅ Create `src/lexlink/client.py` (LawAPIClient)
9. ✅ Create `src/lexlink/errors.py` (error responses)
10. ✅ Create `src/lexlink/validation.py` (parameter validation)
11. ⚠️ Implement remaining 4 tools (eflaw_service, law_service, eflaw_josub, law_josub)
12. ❌ Create `tests/unit/test_params.py` (resolve_oc tests)
13. ❌ Create `tests/unit/test_validation.py`
14. ❌ Create `tests/unit/test_errors.py`

**Validation:** ✅ E2E tests passing, unit tests not yet implemented

### Priority 3: Integration & E2E (Week 3)
**Goal:** Full test suite passing

15. ✅ Create `tests/integration/conftest.py` (mocks)
16. ✅ Create `tests/integration/test_client.py`
17. ✅ Create `tests/e2e/conftest.py` (MCPTestClient)
18. ✅ Create `tests/e2e/test_search_tools.py` (10 E2E scenarios)
19. ✅ Create `pytest.ini` with markers
20. ✅ Create `tests/fixtures/sample_responses.json`

**Validation:** E2E tests pass at 95%+ rate

### Priority 4: Production Ready (Week 4)
**Goal:** CI/CD, monitoring, documentation

21. ✅ Create `src/lexlink/logging_setup.py` (structured logging)
22. ✅ Create `.github/workflows/test.yml` (CI/CD)
23. ✅ Create `tests/performance/test_latency.py`
24. ✅ Update `smithery.yaml` with metadata
25. ✅ Add monitoring/observability
26. ✅ User acceptance testing (UAT) with pilot user

**Validation:** All acceptance criteria from `01_PRD.md` section 10 met

---

## 🔍 Cross-Reference Matrix

| Source Code Module | Test Module | PRD Requirement | Tech Design Section |
|-------------------|-------------|-----------------|---------------------|
| `src/lexlink/config.py` | - | FR11, FR12 | 3.1 |
| `src/lexlink/params.py` | `tests/unit/test_params.py` | FR2, FR4, FR6 | 3.2, 4.1 |
| `src/lexlink/validation.py` | `tests/unit/test_validation.py` | FR9 | 4.2 |
| `src/lexlink/client.py` | `tests/integration/test_client.py` | NFR1, NFR3, NFR4 | 5.1 |
| `src/lexlink/errors.py` | `tests/unit/test_errors.py` | FR5 | 7 |
| `src/lexlink/logging_setup.py` | - | FR7, NFR8 | 8 |
| `src/lexlink/server.py` | `tests/e2e/*` | FR1, FR11, FR12 | 3.2, 6 |
| `src/lexlink/tools/*.py` | `tests/e2e/test_search_tools.py` | FR1 | 6 |

---

## 📝 Acceptance Checklist

From `01_PRD.md` section 10:

### Minimum Viable Product (MVP)
- [ ] All 6 tools callable from Smithery Playground
- [ ] OC parameter successfully passed through all three sources
- [ ] At least one successful E2E call per tool documented
- [ ] Error handling returns structured error objects
- [ ] Korean characters correctly encoded
- [ ] Documentation includes quick start guide
- [ ] API spec matches implementation

### Quality Gates
- [ ] 95%+ success rate in E2E test suite (≥10 scenarios)
- [ ] All error conditions covered with test cases
- [ ] No PII/sensitive data in logs
- [ ] Tool descriptions clear for AI agents
- [ ] Response schemas consistent across formats

### Launch Readiness
- [ ] Published to Smithery marketplace
- [ ] README with installation instructions
- [ ] At least one external user integrated (pilot)
- [ ] Monitoring provides error visibility
- [ ] Known issues documented

---

## 🚀 Quick Start Commands

After implementing missing files:

```bash
# Install dependencies
uv sync

# Run unit tests (should have 90%+ coverage)
uv run pytest tests/unit/ --cov=src/lexlink --cov-report=html

# Run integration tests
uv run pytest tests/integration/

# Start dev server
uv run dev

# In another terminal: Run E2E tests
export TEST_OC=your_test_oc
uv run pytest tests/e2e/

# Run all tests with coverage
uv run pytest --cov=src/lexlink --cov-report=term-missing

# Test in Smithery Playground
uv run playground
```

---

## 📦 Deliverables Summary

| Category | Total Items | Completed | Missing | Priority |
|----------|------------|-----------|---------|----------|
| **Documentation** | 5 | 5 ✅ | 0 | Done |
| **Config Files** | 6 | 6 ✅ | 0 | Done |
| **Source Modules** | 8 | 6 ✅ | 2 ⚠️ | P1-P2 |
| **Test Modules** | 10 | 1 ✅ | 9 ⚠️ | P2-P3 |
| **CI/CD** | 1 | 0 | 1 ❌ | P4 |
| **Total** | **30** | **18** | **12** | - |

**Completion:** 60% (18/30) - Core architecture complete, 4 tools + full test suite remaining

**UPDATE (2025-11-07):** Core implementation complete with Context injection working. E2E tests passing 5/5 (100%). Ready for tool implementation phase.

---

## Next Steps

1. **Review this roadmap** with the team
2. **Start with Priority 1** items (critical path)
3. **Follow TDD approach** - write tests first for each module
4. **Test incrementally** - validate each module before moving to next
5. **Use 02_technical_design.md** as implementation reference
6. **Use 04_test_plan.md** for exact test specifications

**Estimated Timeline:** 4 weeks to full MVP (assuming 1 developer full-time)

---

**Related Documents:**
- `01_PRD.md` - Product requirements (WHAT to build)
- `02_technical_design.md` - Implementation guide (HOW to build)
- `04_test_plan.md` - Test specifications (HOW to verify)
- `03_api_spec.md` - API endpoint details (WHAT to integrate)
