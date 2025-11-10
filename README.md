# LexLink - Korean National Law Information MCP Server

[![smithery badge](https://smithery.ai/badge/@rabqatab/lexlink-ko-mcp)](https://smithery.ai/server/@rabqatab/lexlink-ko-mcp)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LexLink is an MCP (Model Context Protocol) server that exposes the Korean National Law Information API ([law.go.kr](http://www.law.go.kr)) to AI agents and LLM applications. It enables AI systems to search, retrieve, and analyze Korean legal information through standardized MCP tools.

## Features

- **15 MCP Tools** for comprehensive Korean law information access
  - Search and retrieve Korean laws (effective date & announcement date)
  - Search and retrieve English-translated laws
  - Search and retrieve administrative rules (행정규칙)
  - Query specific articles, paragraphs, and sub-items
  - Law-ordinance linkage (법령-자치법규 연계)
  - Delegated law information (위임법령)
- **100% Semantic Validation** - All 15 tools confirmed returning real law data
- **Session Configuration** - Configure once, use across all tool calls
- **Error Handling** - Actionable error messages with resolution hints
- **Korean Text Support** - Proper UTF-8 encoding for Korean characters
- **Response Formats** - HTML, XML, or JSON (multiple formats supported)

## Project Status

🎉 **Production Ready!**

| Metric | Status |
|--------|--------|
| **Tools Implemented** | 15/15 (100%) ✅ |
| **Semantic Validation** | 15/15 (100%) ✅ |
| **API Coverage** | ~10% of 150+ endpoints |
| **LLM Integration** | ✅ Validated (Gemini) |
| **Code Quality** | Clean, documented, tested |

**Achievement:** All 15 tools confirmed returning real Korean law data through comprehensive validation testing.

## Prerequisites

- **Python 3.10+**
- **Smithery API key** (optional, for deployment): Get yours at [smithery.ai/account/api-keys](https://smithery.ai/account/api-keys)
- **law.go.kr OC identifier**: Your email local part (e.g., `g4c@korea.kr` → `g4c`)

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure Your OC Identifier

Choose one of three methods:

**Option A: Session Configuration (Recommended)**
```bash
# Start dev server with OC in URL
uv run dev
# Then in Smithery UI, set oc field in session config
```

**Option B: Environment Variable**
```bash
# Copy example file
cp .env.example .env

# Edit .env and set your OC
LAW_OC=your_id_here
```

**Option C: Pass in Tool Arguments**
```python
# Override OC in each tool call
eflaw_search(query="법령명", oc="your_id")
```

### 3. Run the Server

```bash
# Development mode (with hot reload)
uv run dev

# Interactive testing with Smithery Playground
uv run playground
```

## Available Tools

### Phase 1: Core Law APIs (6 tools)

#### 1. `eflaw_search` - Search Laws by Effective Date
Search for laws organized by effective date (시행일 기준).

```python
eflaw_search(
    query="자동차관리법",      # Search keyword
    display=10,                # Results per page
    type="XML",                # Response format
    ef_yd="20240101~20241231"  # Optional date range
)
```

#### 2. `law_search` - Search Laws by Announcement Date
Search for laws organized by announcement date (공포일 기준).

```python
law_search(
    query="민법",
    display=10,
    type="XML"
)
```

#### 3. `eflaw_service` - Retrieve Law Content (Effective Date)
Get full law text and articles by effective date.

```python
eflaw_service(
    id="001823",               # Law ID
    type="XML",
    jo="0001"                  # Optional: specific article
)
```

#### 4. `law_service` - Retrieve Law Content (Announcement Date)
Get full law text and articles by announcement date.

```python
law_service(
    id="001823",
    type="XML"
)
```

#### 5. `eflaw_josub` - Query Article/Paragraph (Effective Date)
Query specific article, paragraph, or sub-item by effective date.

```python
eflaw_josub(
    id="001823",
    jo="0001",                 # Article number
    type="XML"
)
```

#### 6. `law_josub` - Query Article/Paragraph (Announcement Date)
Query specific article, paragraph, or sub-item by announcement date.

```python
law_josub(
    id="001823",
    jo="0001",
    type="XML"
)
```

### Phase 2: Extended APIs (9 tools)

#### 7. `elaw_search` - Search English-Translated Laws
Search for Korean laws translated to English.

```python
elaw_search(
    query="employment",
    display=10,
    type="XML"
)
```

#### 8. `elaw_service` - Retrieve English Law Content
Get full English-translated law text.

```python
elaw_service(
    id="009589",
    type="XML"
)
```

#### 9. `admrul_search` - Search Administrative Rules
Search administrative rules (훈령, 예규, 고시, 공고, 지침).

```python
admrul_search(
    query="학교",
    display=10,
    type="XML"
)
```

#### 10. `admrul_service` - Retrieve Administrative Rule Content
Get full administrative rule text with annexes.

```python
admrul_service(
    id="62505",
    type="XML"
)
```

#### 11. `lnkLs_search` - Search Law-Ordinance Linkage
Find laws linked to local ordinances.

```python
lnkLs_search(
    query="건축",
    display=10,
    type="XML"
)
```

#### 12. `lnkLsOrdJo_search` - Search Ordinance Articles by Law
Find ordinance articles linked to specific law articles.

```python
lnkLsOrdJo_search(
    knd="002118",              # Law ID
    display=10,
    type="XML"
)
```

#### 13. `lnkDep_search` - Search Law-Ordinance Links by Ministry
Find laws linked to ordinances by government ministry.

```python
lnkDep_search(
    org="1400000",             # Ministry code
    display=10,
    type="XML"
)
```

#### 14. `drlaw_search` - Retrieve Law-Ordinance Linkage Statistics
Get linkage statistics table (HTML format).

```python
drlaw_search(
    lid="001823",              # Law ID
    type="HTML"
)
```

#### 15. `lsDelegated_service` - Retrieve Delegated Law Information
Get information about delegated laws, rules, and ordinances.

```python
lsDelegated_service(
    id="001823",
    type="XML"
)
```

## Configuration

### Session Configuration Schema

Configure once in Smithery UI or URL parameters:

```python
{
    "oc": "your_id",              # Required: law.go.kr user ID
    "debug": false,               # Optional: Enable verbose logging
    "base_url": "http://www.law.go.kr",  # Optional: API base URL
    "http_timeout_s": 15          # Optional: HTTP timeout (5-60s)
}
```

### Parameter Priority

When resolving the OC identifier:
1. **Tool argument** (highest priority) - `oc` parameter in tool call
2. **Session config** - Set in Smithery UI/URL
3. **Environment variable** - `LAW_OC` in .env file

## Usage Examples

### Example 1: Basic Search

```python
# Search for automobile management law
result = eflaw_search(
    query="자동차관리법",
    display=5,
    type="JSON"
)

# Returns:
{
    "status": "ok",
    "request_id": "uuid",
    "upstream_type": "JSON",
    "data": {
        # Law search results...
    }
}
```

### Example 2: Search with Date Range

```python
# Find laws effective in 2024
result = eflaw_search(
    query="교통",
    ef_yd="20240101~20241231",
    type="JSON"
)
```

### Example 3: Error Handling

```python
# Missing OC parameter
result = eflaw_search(query="test")

# Returns helpful error:
{
    "status": "error",
    "error_code": "MISSING_OC",
    "message": "OC parameter is required but not provided.",
    "hints": [
        "1. Tool argument: oc='your_value'",
        "2. Session config: Set 'oc' in Smithery settings",
        "3. Environment variable: LAW_OC=your_value"
    ]
}
```

## Development

### Project Structure

```
lexlink-ko-mcp/
├── src/lexlink/
│   ├── server.py       # Main MCP server with 15 tools
│   ├── config.py       # Session configuration schema
│   ├── params.py       # Parameter resolution & mapping
│   ├── validation.py   # Input validation
│   ├── client.py       # HTTP client for law.go.kr API
│   └── errors.py       # Error codes & responses
├── docs/
│   ├── DEVELOPMENT.md              # Project status & history
│   ├── API_SPEC.md                 # API endpoint specifications
│   ├── API_ROADMAP.md              # Implementation plan
│   ├── API_COVERAGE_ANALYSIS.md    # Coverage analysis
│   ├── all_apis.md                 # Complete API catalog
│   └── reference/                  # Historical docs
├── test/
│   ├── test_semantic_validation.py      # Semantic data validation
│   ├── test_llm_integration.py          # LLM + MCP integration
│   ├── test_e2e_with_gemini.py          # E2E workflow tests
│   ├── COMPREHENSIVE_TEST_SUMMARY.md    # Overall test results
│   ├── SEMANTIC_VALIDATION_SUMMARY.md   # Data quality report
│   ├── VALIDATOR_INVESTIGATION_REPORT.md # 100% validation report
│   └── logs/                            # Test execution logs
├── pyproject.toml       # Project configuration
└── README.md            # This file
```

### Running Tests

```bash
# Install test dependencies
uv sync

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/lexlink --cov-report=html

# Run specific test category
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/e2e/
```

### Adding New Tools

**Current Status:** 15/15 core tools implemented and validated

For implementing additional tools from the 150+ available APIs:
1. See `docs/all_apis.md` for complete API catalog
2. Follow the pattern established in `src/lexlink/server.py`
3. Use Context injection for session configuration
4. Add semantic validation tests

**Tool Implementation Pattern:**
- Each tool is a decorated function with MCP schema
- Uses `ctx: Context = None` parameter for session config
- 3-tier parameter resolution: tool arg > session > env
- Comprehensive error handling with actionable hints

## Deployment

### Deploy to Smithery

1. Create a GitHub repository:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

2. Deploy at [smithery.ai/new](https://smithery.ai/new)

3. Configure session settings in Smithery UI

## Documentation

### Core Documentation
- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Current project status and development history
- **[API Specification](docs/API_SPEC.md)** - law.go.kr API endpoint specifications
- **[API Roadmap](docs/API_ROADMAP.md)** - API implementation plan and progress
- **[All APIs](docs/all_apis.md)** - Complete list of available law.go.kr APIs (150+ endpoints)

### Test Reports
- **[Comprehensive Test Summary](test/COMPREHENSIVE_TEST_SUMMARY.md)** - Overall test results (15/15 tools)
- **[Semantic Validation Summary](test/SEMANTIC_VALIDATION_SUMMARY.md)** - Data quality validation
- **[Validator Investigation Report](test/VALIDATOR_INVESTIGATION_REPORT.md)** - 100% validation achievement

### Reference Documentation
- **[API Coverage Analysis](docs/API_COVERAGE_ANALYSIS.md)** - API implementation coverage analysis
- **[Reference Documents](docs/reference/)** - Historical design docs and research

## Troubleshooting

### "OC parameter is required" error

**Solution:** Set your OC identifier using one of the three methods above.

### Korean characters not displaying correctly

**Solution:** Ensure your terminal supports UTF-8:
```bash
export PYTHONIOENCODING=utf-8
```

### "Timeout" errors

**Solution:** Increase timeout in session config:
```python
{
    "oc": "your_id",
    "http_timeout_s": 30  # Increase from default 15s
}
```

### Server won't start after updating dependencies

**Solution:** Re-sync dependencies:
```bash
uv sync --reinstall
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Ensure all tests pass (`uv run pytest`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is open source. See LICENSE file for details.

## Acknowledgments

- **law.go.kr** - Korean National Law Information API
- **MCP** - Model Context Protocol by Anthropic
- **Smithery** - MCP server deployment platform

## Support

- **Issues:** [GitHub Issues](https://github.com/rabqatab/LexLink-ko-mcp/issues)
- **Documentation:** See `docs/` directory
- **law.go.kr API:** [Official Documentation](http://www.law.go.kr)

---

## Changelog

### 2025-11-10 - v1.0.1
**Fix: Remove JSON format option from all tools**

- **Issue:** LLMs were selecting JSON format, but law.go.kr API does not support JSON despite documentation (returns HTML error pages with "미신청된 목록/본문" message)
- **Solution:** Removed JSON as an option from all 14 tool descriptions
- **Changes:**
  - Updated `type` parameter documentation to explicitly state "JSON not supported by API"
  - Added warning in module docstring about JSON format limitation
  - Tool defaults remain XML (working format)
- **Impact:** Prevents LLMs from requesting JSON format and receiving error pages

### 2025-11-10 - v1.0.0
**Initial Release**

- 15 MCP tools for Korean law information access
- 6 core law APIs (eflaw/law search and retrieval)
- 9 extended APIs (English laws, administrative rules, law-ordinance linkage)
- Session configuration via Context injection
- 100% semantic validation
- Production-ready for Smithery deployment

---

**Built with [Smithery](https://smithery.ai) | Powered by [MCP](https://modelcontextprotocol.io)**
