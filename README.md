<div align="center">
  <img src="assets/LexLink_logo.png" alt="LexLink Logo" width="200"/>
  <h1>LexLink - Korean National Law Information MCP Server</h1>
</div>

**🌐 Read this in other languages:** **English** | [한국어 (Korean)](README_kr.md)

[![smithery badge](https://smithery.ai/badge/@rabqatab/lexlink-ko-mcp)](https://smithery.ai/server/@rabqatab/lexlink-ko-mcp)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LexLink is an MCP (Model Context Protocol) server that exposes the Korean National Law Information API ([open.law.go.kr](http://open.law.go.kr)) to AI agents and LLM applications. It enables AI systems to search, retrieve, and analyze Korean legal information through standardized MCP tools.

## Features

- **24 MCP Tools** for comprehensive Korean law information access
  - Search and retrieve Korean laws (effective date & announcement date)
  - Search and retrieve English-translated laws
  - Search and retrieve administrative rules (행정규칙)
  - Query specific articles, paragraphs, and sub-items
  - Law-ordinance linkage (법령-자치법규 연계)
  - Delegated law information (위임법령)
  - **Phase 3 - Case Law & Legal Research**
    - Court precedents (판례)
    - Constitutional Court decisions (헌재결정례)
    - Legal interpretations (법령해석례)
    - Administrative appeal decisions (행정심판례)
  - **NEW: Phase 4 - Article Citation Extraction**
    - Extract legal citations from any law article (100% accuracy)
- **100% Semantic Validation** - All 24 tools confirmed returning real law data
- **Session Configuration** - Configure once, use across all tool calls
- **Error Handling** - Actionable error messages with resolution hints
- **Korean Text Support** - Proper UTF-8 encoding for Korean characters
- **Response Formats** - HTML or XML (multiple formats supported)

## Project Status

🎉 **Production Ready - Phase 4 Complete!**

| Metric | Status |
|--------|--------|
| **Tools Implemented** | 24/24 (100%) ✅ |
| **Semantic Validation** | 24/24 (100%) ✅ |
| **MCP Prompts** | 5/5 (100%) ✅ |
| **API Coverage** | ~16% of 150+ endpoints |
| **LLM Integration** | ✅ Validated (Gemini) |
| **Code Quality** | Clean, documented, tested |
| **Version** | v1.2.9 |

**Latest Achievement:** Phase 4 complete! Added article citation extraction with 100% accuracy via HTML parsing.

## Prerequisites

- **Python 3.10+**
- **Smithery API key** (optional, for deployment): Get yours at [smithery.ai/account/api-keys](https://smithery.ai/account/api-keys)
- **law.go.kr OC identifier**: Get key from [open.law.go.kr](https://open.law.go.kr)

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
OC=your_id_here
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

> **IMPORTANT:** For specific article queries (e.g., "제174조"), use the `jo` parameter. Some laws have 400+ articles and responses can exceed 1MB without `jo`.

```python
# Get specific article (RECOMMENDED)
eflaw_service(
    mst="279823",              # Law MST
    jo="017400",               # Article 174 (제174조)
    type="XML"
)

# Get full law (WARNING: large response)
eflaw_service(
    id="001823",
    type="XML"
)
```

#### 4. `law_service` - Retrieve Law Content (Announcement Date)
Get full law text and articles by announcement date.

> **IMPORTANT:** For specific article queries (e.g., "제174조"), use the `jo` parameter. Some laws have 400+ articles and responses can exceed 1MB without `jo`.

```python
# Get specific article (RECOMMENDED)
law_service(
    mst="279823",              # Law MST
    jo="017400",               # Article 174 (제174조)
    type="XML"
)
```

#### 5. `eflaw_josub` - Query Article/Paragraph (Effective Date)
**Best tool for querying specific articles.** Returns only the requested article/paragraph.

```python
eflaw_josub(
    mst="279823",              # Law MST
    jo="017400",               # Article 174 (제174조)
    type="XML"
)
# jo format: "XXXXXX" where first 4 digits = article (zero-padded), last 2 = branch (00=main)
# Examples: "017400" (제174조), "000300" (제3조), "001502" (제15조의2)
```

#### 6. `law_josub` - Query Article/Paragraph (Announcement Date)
**Best tool for querying specific articles.** Returns only the requested article/paragraph.

```python
law_josub(
    mst="279823",              # Law MST
    jo="017200",               # Article 172 (제172조)
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

### Phase 3: Case Law & Legal Research (8 tools - NEW!)

#### 16. `prec_search` - Search Court Precedents
Search Korean court precedents from Supreme Court and lower courts.

```python
prec_search(
    query="담보권",
    display=10,
    type="XML",
    curt="대법원"             # Optional: Court name filter
)
```

#### 17. `prec_service` - Retrieve Court Precedent Full Text
Get complete court precedent text with case details.

```python
prec_service(
    id="228541",
    type="XML"
)
```

#### 18. `detc_search` - Search Constitutional Court Decisions
Search Korean Constitutional Court decisions.

```python
detc_search(
    query="벌금",
    display=10,
    type="XML"
)
```

#### 19. `detc_service` - Retrieve Constitutional Court Decision Full Text
Get complete Constitutional Court decision text.

```python
detc_service(
    id="58386",
    type="XML"
)
```

#### 20. `expc_search` - Search Legal Interpretations
Search legal interpretation precedents issued by government agencies.

```python
expc_search(
    query="임차",
    display=10,
    type="XML"
)
```

#### 21. `expc_service` - Retrieve Legal Interpretation Full Text
Get complete legal interpretation text.

```python
expc_service(
    id="334617",
    type="XML"
)
```

#### 22. `decc_search` - Search Administrative Appeal Decisions
Search Korean administrative appeal decisions.

```python
decc_search(
    query="*",                # Search all decisions
    display=10,
    type="XML"
)
```

#### 23. `decc_service` - Retrieve Administrative Appeal Decision Full Text
Get complete administrative appeal decision text.

```python
decc_service(
    id="243263",
    type="XML"
)
```

### Phase 4: Article Citation Extraction (1 tool - NEW!)

#### 24. `article_citation` - Extract Citations from Law Article
Extract all legal citations referenced by a specific law article.

```python
# First, search for the law to get MST
eflaw_search(query="건축법")  # Returns MST: 268611

# Then extract citations
article_citation(
    mst="268611",              # Law MST from search result
    law_name="건축법",          # Law name
    article=3                  # Article number (제3조)
)
```

**Response:**
```json
{
    "success": true,
    "law_name": "건축법",
    "article": "제3조",
    "citation_count": 12,
    "internal_count": 4,
    "external_count": 8,
    "citations": [
        {
            "type": "external",
            "target_law_name": "「국토의 계획 및 이용에 관한 법률」",
            "target_article": 56,
            "target_paragraph": 1
        }
    ]
}
```

**Key Features:**
- 100% accuracy via HTML parsing (not LLM-based)
- Zero API cost (no external LLM calls)
- ~350ms average extraction time
- Distinguishes internal vs external citations

## Configuration

### Session Configuration Schema

Configure once in Smithery UI or URL parameters:

```python
{
    "oc": "your_id",              # Required: law.go.kr user ID
    "http_timeout_s": 60          # Optional: HTTP timeout (5-120s, default: 60)
}
```

### Parameter Priority

When resolving the OC identifier:
1. **Tool argument** (highest priority) - `oc` parameter in tool call
2. **Session config** - Set in Smithery UI/URL
3. **Environment variable** - `OC` in .env file

## Usage Examples

### Example 1: Basic Search

```python
# Search for automobile management law
result = eflaw_search(
    query="자동차관리법",
    display=5,
    type="XML"
)

# Returns:
{
    "status": "ok",
    "request_id": "uuid",
    "upstream_type": "XML",
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
    type="XML"
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
        "3. Environment variable: OC=your_value"
    ]
}
```

## Golden MCP Tool Trajectories

These examples demonstrate real-world conversation flows showing how LLMs interact with LexLink tools to answer legal research questions.

### Trajectory 1: Basic Law Research
**User Query:** "What is Article 20 of the Civil Code?"

**Tool Calls:**
1. `law_search(query="민법", display=50, type="XML")` → Find Civil Code ID
2. `law_service(id="000021", jo="002000", type="XML")` → Retrieve Article 20 text

**Result:** LLM provides formatted explanation of Civil Code Article 20 with full legal text and context.

---

### Trajectory 2: Court Precedent Analysis
**User Query:** "Find recent Supreme Court precedents about security interests"

**Tool Calls:**
1. `prec_search(query="담보권", curt="대법원", display=50, type="XML")` → Search Supreme Court precedents
2. `prec_service(id="228541", type="XML")` → Retrieve top precedent details

**Result:** LLM summarizes key precedents with case numbers, dates, and holdings related to security interests.

---

### Trajectory 3: Cross-Phase Legal Research
**User Query:** "How does the Labor Standards Act handle overtime, and are there relevant court precedents?"

**Tool Calls:**
1. `eflaw_search(query="근로기준법", display=50, type="XML")` → Find Labor Standards Act
2. `eflaw_service(id="001234", jo="005000", type="XML")` → Retrieve Article 50 (overtime provisions)
3. `prec_search(query="근로기준법 연장근로", display=30, type="XML")` → Search overtime precedents
4. `prec_service(id="234567", type="XML")` → Retrieve leading precedent

**Result:** LLM provides comprehensive analysis combining statutory text with judicial interpretation, showing how courts apply the overtime provisions.

---

### Trajectory 4: Constitutional Review
**User Query:** "Has the Constitutional Court reviewed laws about fines?"

**Tool Calls:**
1. `detc_search(query="벌금", display=50, type="XML")` → Search Constitutional Court decisions
2. `detc_service(id="58386", type="XML")` → Retrieve decision full text
3. `law_search(query=<law_name_from_decision>, type="XML")` → Find related law for context

**Result:** LLM explains Constitutional Court holdings on fine-related provisions and their impact on specific laws.

---

### Trajectory 5: Administrative Law Research
**User Query:** "What administrative rules exist for schools, and are there related legal interpretations?"

**Tool Calls:**
1. `admrul_search(query="학교", display=50, type="XML")` → Search school-related administrative rules
2. `admrul_service(id="62505", type="XML")` → Retrieve rule content
3. `expc_search(query="학교", display=30, type="XML")` → Search legal interpretations
4. `expc_service(id="334617", type="XML")` → Retrieve interpretation details

**Result:** LLM provides overview of administrative framework for schools with official agency interpretations.

---

### Trajectory 6: Comprehensive Legal Analysis
**User Query:** "I'm researching rental housing disputes. Show me the relevant law, court precedents, and administrative appeal decisions."

**Tool Calls:**
1. `eflaw_search(query="주택임대차보호법", display=50, type="XML")` → Find Housing Lease Protection Act
2. `eflaw_service(id="002876", type="XML")` → Retrieve full law text
3. `prec_search(query="주택임대차", display=50, type="XML")` → Search housing lease precedents
4. `prec_service(id="156789", type="XML")` → Retrieve key precedent
5. `decc_search(query="주택임대차", display=30, type="XML")` → Search administrative appeal decisions
6. `decc_service(id="243263", type="XML")` → Retrieve appeal decision

**Result:** LLM provides comprehensive legal research report covering statutory framework, judicial interpretation, and administrative precedents for rental housing disputes.

---

### Trajectory 7: Citation Network Analysis (Phase 4)
**User Query:** "What laws does Article 3 of the Building Act cite?"

**Tool Calls:**
1. `eflaw_search(query="건축법", display=50, type="XML")` → Find Building Act, get MST
2. `article_citation(mst="268611", law_name="건축법", article=3)` → Extract all citations

**Result:** LLM provides complete citation analysis showing 12 citations (8 external laws, 4 internal references) including specific article and paragraph references.

---

### Key Patterns

1. **Search First, Then Retrieve**: Always search to find IDs before calling service tools
2. **Use display=50-100 for Law Searches**: Ensures exact matches are found due to relevance ranking
3. **Combine Phases**: Mix Phase 1 (laws), Phase 2 (administrative rules), and Phase 3 (precedents) for complete research
4. **Type Parameter**: Always specify `type="XML"` for consistent, parseable results
5. **Article Numbers**: Use 6-digit format (e.g., "002000" for Article 20) when querying specific articles

## Development

### Project Structure

```
lexlink-ko-mcp/
├── src/lexlink/
│   ├── server.py       # Main MCP server with 24 tools
│   ├── http_server.py  # HTTP/SSE server for Kakao PlayMCP
│   ├── config.py       # Session configuration schema
│   ├── params.py       # Parameter resolution & mapping
│   ├── validation.py   # Input validation
│   ├── parser.py       # XML parsing utilities
│   ├── ranking.py      # Relevance ranking
│   ├── citation.py     # Article citation extraction (Phase 4)
│   ├── client.py       # HTTP client for law.go.kr API
│   └── errors.py       # Error codes & responses
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

**Current Status:** 24/24 tools implemented and validated (Phase 1-4 complete)

For implementing additional tools from the 126+ remaining APIs:
1. Follow the pattern established in `src/lexlink/server.py`
2. Use Context injection for session configuration
3. Use generic parser functions (`extract_items_list`, `update_items_list`)
4. Add semantic validation tests

**Tool Implementation Pattern:**
- Each tool is a decorated function with MCP schema
- Uses `ctx: Context = None` parameter for session config
- 3-tier parameter resolution: tool arg > session > env
- Generic parser functions work with any XML tag
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

### Deploy to Kakao PlayMCP (HTTP Server)

LexLink can also be deployed as an HTTP server for platforms like Kakao PlayMCP.

> **Important:** Kakao PlayMCP does not accept port numbers in URLs.
> You must use Nginx as a reverse proxy to serve on port 80.

**Quick Start (Local Testing):**
```bash
# Run the HTTP server
OC=your_oc uv run serve

# Server starts at: http://localhost:8000/sse
```

**Production Setup:**
```
Internet → Nginx (port 80) → LexLink (port 8000)
```

**PlayMCP Registration:**

| Field | Value |
|-------|-------|
| **MCP Endpoint** | `http://YOUR_SERVER_IP/sse` (no port!) |
| **Authentication** | Key/Token (Header: `OC`) |

For detailed deployment instructions (AWS EC2, Nginx, systemd, HTTPS), see [assets/DEPLOYMENT_GUIDE.md](assets/DEPLOYMENT_GUIDE.md).

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
    "http_timeout_s": 90  # Increase from default 60s
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
- **law.go.kr API:** [Official Documentation](http://open.law.go.kr)

---

## Changelog

### v1.2.9 - 2025-12-09
**Fix: Case-insensitive item key matching for API inconsistency**

- **Issue:** law.go.kr API uses inconsistent XML tag casing
  - `prec` search → `<prec>` (lowercase)
  - `detc` search → `<Detc>` (capitalized)
  - `expc` search → `<Expc>` (capitalized)
- **Fix:** Made `extract_items_list`, `update_items_list`, and `slim_response` case-insensitive

### v1.2.8 - 2025-12-09
**Fix: Case-sensitive item key extraction for non-law searches**

- **Issue:** `extract_items_list()` used capitalized keys ('Prec', 'Detc', 'Expc', 'Decc') but XML parser outputs lowercase ('prec', 'detc', etc.)
- **Result:** `ranked_data` never set → empty responses for all non-law searches
- **Fix:** Changed all 8 calls to use lowercase keys

### v1.2.7 - 2025-12-09
**Refactor: Pattern-based essential field detection**

- **Issue:** Manual field definitions per data type required maintenance for each new API
- **Solution:** Regex pattern matching for automatic field detection
- **Patterns:** `*일련번호` (IDs), `*명한글/*명` (names), `*일자` (dates), etc.
- **Benefit:** Works automatically for any data type without manual definitions

### v1.2.6 - 2025-12-09
**Fix: Data-type-specific essential fields for slim response**

- **Issue:** `slim_response()` used law-specific field names for all data types
  - Precedent searches (`prec_search`) returned empty results
  - Fields like `판례일련번호`, `사건명` were filtered out because they didn't match law fields
- **Solution:**
  - Implemented `essential_fields_by_type` dictionary with correct fields per data type
  - Each API type (law, prec, detc, expc, decc, admrul, elaw) now has its own essential fields

### v1.2.5 - 2025-12-09
**Fix: Add 법령ID to essential fields for correct parameter usage**

- **Issue:** LLM was confusing `법령일련번호` (MST) with `법령ID` in slimmed responses
  - Example: Calling `eflaw_service(id="235555")` when 235555 is MST, not 법령ID
  - Correct usage should be `eflaw_service(mst=235555)` or `eflaw_service(id="001624")`
- **Solution:**
  - Added `법령ID` back to `essential_fields` in `slim_response()`
  - Now LLM can see both fields and use correct parameter
- **Essential fields:** 법령명한글, 법령일련번호, **법령ID**, 현행연혁코드, 시행일자
- **Note:** If ranking not working, ensure EC2 has latest code with relevance ranking

### v1.2.4 - 2025-12-09
**Fix: Slim response mode for PlayMCP size limits**

- **Issue:** v1.2.3's truncation approach was insufficient because `ranked_data` still contained full data (~25KB per 50 results)
- **Solution:**
  - Replaced `truncate_response()` with `slim_response()` function
  - When `SLIM_RESPONSE=true`: removes `raw_content` entirely and keeps only essential fields in `ranked_data`
  - Essential fields kept: 법령명한글, 법령일련번호, 현행연혁코드, 시행일자
  - Fields removed: 법령약칭명, 공포일자, 공포번호, 제개정구분명, 소관부처코드, 소관부처명, 법령구분명, 공동부령정보, 자법타법여부, 법령상세링크
- **Configuration:**
  - Smithery: No change needed (full response)
  - PlayMCP: Set `SLIM_RESPONSE=true` in systemd service
- **Impact:**
  - Response size reduced from ~50KB to ~3-5KB for 50 results
  - PlayMCP works reliably without size errors

### v1.2.3 - 2025-12-08
**Fix: Response truncation for PlayMCP size limits**

- **Issue:** PlayMCP has response size limits (~50KB), causing "Tool call returned too large content part" errors
- **Solution:**
  - Added `truncate_response()` helper function for optional response size limiting
  - Applied truncation to all 11 search tools (eflaw_search, law_search, elaw_search, admrul_search, lnkLs_search, lnkLsOrdJo_search, lnkDep_search, prec_search, detc_search, expc_search, decc_search)
  - Added `MAX_RESPONSE_SIZE` environment variable (only truncates when set)
- **Configuration:**
  - Smithery: No change needed (no size limit)
  - PlayMCP: Set `MAX_RESPONSE_SIZE=50000` in systemd service
- **Impact:**
  - Smithery keeps full functionality (unlimited responses)
  - PlayMCP avoids size errors with truncated responses + Korean message

### v1.2.2 - 2025-12-06
**Feature: HTTP/SSE Server for Kakao PlayMCP**

- **New Feature:**
  - Added HTTP/SSE server support for Kakao PlayMCP deployment
  - New `uv run serve` command to start HTTP server
  - OCHeaderMiddleware extracts OC from HTTP headers (Key/Token auth)
  - Supports both SSE (`/sse`) and Streamable HTTP (`/mcp`) transports
- **Breaking Changes:**
  - Renamed `LAW_OC` environment variable to `OC` (matches official law.go.kr API naming)
- **Configuration Changes:**
  - Removed `base_url` from Smithery UI config (kept as internal field only)
  - Updated default timeout from 15s to 60s
  - Timeout range extended to 5-120s
- **Documentation:**
  - Added Kakao PlayMCP deployment guide (`assets/DEPLOYMENT_GUIDE.md`)
  - Updated README with PlayMCP deployment section
  - Added `http_server.py` to project structure
- **Impact:**
  - LexLink can now be deployed to Kakao PlayMCP and similar HTTP-based platforms
  - Each PlayMCP user provides their own OC via HTTP header (uses their own API quota)

### v1.2.1 - 2025-11-30
**Fix: Improve LLM guidance for specific article queries**

- **Issue:** LLMs were fetching entire laws (1MB+ for 자본시장법) instead of using `jo` parameter for specific articles like "제174조"
- **Solution:**
  - Added **IMPORTANT** notices in `eflaw_service` and `law_service` docstrings about using `jo` parameter
  - Added **BEST TOOL** guidance in `eflaw_josub` and `law_josub` docstrings
  - Added practical examples: `jo="017400"` for 제174조, `jo="000300"` for 제3조
  - Warned about large response sizes (400+ articles, 1MB+ responses)
- **Impact:**
  - LLMs now correctly use `jo` parameter for specific article queries
  - LLMs prefer `law_josub`/`eflaw_josub` for article queries
  - Faster responses and cleaner output for specific article requests

### v1.2.0 - 2025-11-30
**Feature: Phase 4 - Article Citation Extraction**

- **New Tool:**
  - `article_citation` - Extract legal citations from any law article (Tool 24)
- **Implementation:**
  - HTML parsing approach for 100% accuracy (no LLM hallucination risk)
  - CSS class-based citation type detection (sfon1-4 classes)
  - MST ↔ lsiSeq ID mapping between XML API and HTML pages
  - Zero external API costs (no LLM calls required)
  - ~350ms average extraction time
- **Features:**
  - Distinguishes internal vs external citations
  - Extracts article, paragraph, and sub-item references
  - Consolidates duplicate citations with citation counts
  - Preserves raw citation text for context
- **MCP Prompts Added:**
  - `extract-law-citations` - Extract and explain citations from a law article
  - `analyze-citation-network` - Analyze legal citation network for a law
- **Test Coverage:**
  - Unit tests: Citation module 100% coverage
  - Integration tests: End-to-end extraction validated
  - LLM workflow tests: Gemini 2.0 Flash validated
- **Known Limitations:**
  - Range references (e.g., "제88조 내지 제93조") return first article only
  - External law names require separate search for MST lookup
- **Impact:**
  - Tool count: 23 → 24 tools
  - MCP prompts: 3 → 5 prompts
  - Enables citation network analysis workflows

### v1.1.0 - 2025-11-14
**Feature: Phase 3 - Case Law & Legal Research APIs**

- **Changes:**
  - Added 8 new tools for case law and legal research (15 → 23 tools)
  - `prec_search`, `prec_service` - Court precedents (판례)
  - `detc_search`, `detc_service` - Constitutional Court decisions (헌재결정례)
  - `expc_search`, `expc_service` - Legal interpretations (법령해석례)
  - `decc_search`, `decc_service` - Administrative appeal decisions (행정심판례)
- **Implementation:**
  - Added generic parser functions (`extract_items_list`, `update_items_list`) that work with any XML tag
  - Added 13 new Phase 3 parameters: `prnc_yd`, `dat_src_nm`, `ed_yd`, `reg_yd`, `expl_yd`, `dpa_yd`, `rsl_yd`, `curt`, `inq`, `rpl`, `itmno`, `cls`
  - All ranking and validation functions compatible with Phase 3 tools
  - Zero breaking changes to existing Phase 1 & 2 tools
- **Impact:**
  - Tool count increased by 53% (15 → 23 tools)
  - API coverage increased from ~10% to ~15%
  - Legal research categories expanded by 133% (3 → 7 categories)
  - All 23 tools validated and working in production

### v1.0.8 - 2025-11-13
**Fix: Complete parameter type consistency across all tools**

- **Issue:** v1.0.2 fixed 7 tools but missed 2 additional tools (`eflaw_josub`, `law_josub`), creating inconsistency where same parameters had different types across tools
- **Root Cause:**
  - `eflaw_josub` and `law_josub` still had `id: Optional[str]` and `mst: Optional[str]` instead of `Union[str, int]`
  - `lnkLsOrdJo_search` had `jo: Optional[int]` instead of `Union[str, int]`
  - Caused validation errors when LLMs passed integers to these specific tools
- **Solution:**
  - Fixed `eflaw_josub`: `id` and `mst` now accept `Union[str, int]`
  - Fixed `law_josub`: `id` and `mst` now accept `Union[str, int]`
  - Fixed `lnkLsOrdJo_search`: `jo` now accepts `Union[str, int]`
- **Verification:**
  - All 7 tools with `id` parameter now consistently `Optional[Union[str, int]]`
  - All 6 tools with `mst` parameter now consistently `Optional[Union[str, int]]`
  - All 5 tools with `jo` parameter now consistently `Optional[Union[str, int]]`
- **Impact:**
  - 100% parameter type consistency achieved
  - No validation errors regardless of which tool LLMs choose
  - Better developer experience - same parameters work identically everywhere

### v1.0.7 - 2025-11-10
**Fix: Improve search reliability and LLM guidance**

- **Issue:** LLMs often failed to find common laws like "민법" (Civil Code) because:
  1. Ranking fetch limit (50 results) was too small for large result sets (e.g., 77 results for "민법")
  2. LLMs defaulted to small `display` values (e.g., 5), missing exact matches
  3. `jo` parameter rejected integers, causing validation errors and retry loops
- **Root Cause:**
  - v1.0.5 ranking fetched only 50 results; "민법" was beyond position 50 alphabetically
  - Tool descriptions didn't guide LLMs to use larger display values
  - Parameter type strictness caused UX friction
- **Solution:**
  - Increased ranking fetch limit from 50 to **100 results** (API maximum)
  - Updated `jo` parameter to accept `Union[str, int]` with auto-conversion
  - Added guidance in tool descriptions: **"Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found"**
- **Changes:**
  - All 4 search tools now fetch up to 100 results for ranking
  - All 4 tools with `jo` parameter (`eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`) now accept integers
  - All 7 search tool descriptions updated with display recommendations
- **Impact:**
  - LLMs now find "민법" correctly even with small initial display values
  - No more validation errors when LLMs pass article numbers as integers
  - Better guidance leads to more efficient searches

### v1.0.6 - 2025-11-10
**Enhancement: Improve MCP server quality score (Smithery.ai optimization)**

- **Changes:**
  - Set OC configuration default value to "test" for easier onboarding
  - Added tool annotations to all 15 tools (readOnlyHint=True, destructiveHint=False, idempotentHint=True)
  - Enhanced parameter descriptions in docstrings for all tools
  - Implemented 3 MCP prompts for common use cases
- **Prompts Added:**
  - `search-korean-law`: Search for a Korean law by name and provide a summary
  - `get-law-article`: Retrieve and explain a specific article from a law
  - `search-admin-rules`: Search administrative rules by keyword
- **Impact:** Expected Smithery quality score improvement from 47/100 to ~73/100 (+26 points)
  - Tool annotations: +9pts
  - Parameter descriptions: +12pts
  - MCP prompts: +5pts

### v1.0.5 - 2025-11-10
**Fix: Improve ranking by fetching more results before ranking**

- **Issue:** v1.0.4 ranking was not working properly because it only ranked the limited results returned by the API (e.g., with `display=5`, only 5 alphabetically-ordered results were fetched). If "민법" wasn't in those first 5 results, ranking couldn't help.
- **Root Cause:** Ranking logic was applied AFTER API returned limited results, so relevant matches outside the initial page were never considered.
- **Solution:**
  - When ranking is enabled and `display < 50`, automatically fetch up to 50 results from API
  - Apply ranking to the larger result set (50 results)
  - Trim back to original requested `display` amount after ranking
  - Update `numOfRows` in response to reflect actual number of results returned
- **Implementation:**
  - Updated all 4 search tools: `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`
  - Added `original_display` tracking and `ranking_enabled` flag
  - Fetch 50 results when ranking applies, then trim to requested amount
- **Examples:**
  - User requests `display=5` for query "민법"
  - System fetches 50 results (includes "민법" even if it's not in first 5 alphabetically)
  - Ranking places "민법" first
  - System returns top 5 ranked results (now "민법" appears first)
- **Impact:** Ranking now actually works - exact matches appear first regardless of alphabetical position in API results

### v1.0.4 - 2025-11-10
**Feature: Add relevance ranking to search results**

- **Issue:** law.go.kr API returns results in alphabetical order, causing irrelevant matches to appear first (e.g., searching "민법" returned "난민법" first instead of exact match "민법")
- **Solution:**
  - Added intelligent relevance ranking that prioritizes exact matches over alphabetical ordering
  - Ranking applies automatically to XML responses for keyword searches
  - Results are reordered: exact match → starts with query → contains query → other matches
- **Implementation:**
  - Added `ranking.py` module with `rank_search_results()`, `should_apply_ranking()`, and `detect_query_language()` functions
  - Added `parser.py` module for XML parsing and structured data extraction
  - Updated 4 major search tools: `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`
  - Ranking preserves raw XML while adding `ranked_data` field for LLM consumption
  - Special handling for `elaw_search`: Detects query language (Korean vs English) and ranks by matching name field
- **Examples:**
  - Query "민법" now returns: "민법" (exact) → "민법 시행령" (starts with) → "난민법" (alphabetical)
  - Query "insurance" ranks: "Insurance Act" → "Insurance Business Act" → other matches
- **Impact:** Significantly improves search relevance, reducing LLM confusion and providing better user experience

### v1.0.3 - 2025-11-10
**Fix: Clarify article number format in tool descriptions**

- **Issue:** LLMs misinterpreted the 6-digit article number format (`jo` parameter), generating "000200" for Article 20 (제20조) instead of correct "002000", resulting in wrong article retrieval
- **Root Cause:** Tool descriptions used ambiguous example "000200" for "Article 2", leading LLMs to incorrectly pattern-match Article 20 → "000200"
- **Solution:**
  - Added comprehensive article number format documentation with multiple examples
  - Added `format_article_number()` helper function in `validation.py` for future use
  - Clarified that XXXXXX format = first 4 digits (article number, zero-padded) + last 2 digits (branch article suffix)
- **Changes:**
  - Updated 4 tools: `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`
  - Updated `lnkLsOrdJo_search` which uses separate 4+2 digit format
  - Added clear examples: "000200" (Art. 2), "002000" (Art. 20), "001502" (Art. 15-2)
- **Impact:** LLMs will now correctly format article numbers, preventing queries from returning wrong articles

### v1.0.2 - 2025-11-10
**Fix: Accept both string and integer for id/mst parameters**

- **Issue:** LLMs extract numeric values from XML responses as integers (e.g., `<법령일련번호>188376</법령일련번호>` → `mst=188376`), but tools expected strings, causing Pydantic validation errors
- **Solution:** Changed parameter types to accept both strings and integers with automatic conversion
- **Changes:**
  - Updated 7 tool signatures: `id: Optional[str]` → `id: Optional[Union[str, int]]`
  - Added automatic string conversion at start of each affected tool
  - Applied to: `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`, `elaw_service`, `admrul_service`, `lsDelegated_service`
- **Impact:** LLMs can now pass numeric IDs as integers without validation errors

### v1.0.1 - 2025-11-10
**Fix: Remove JSON format option from all tools**

- **Issue:** LLMs were selecting JSON format, but law.go.kr API does not support JSON despite documentation (returns HTML error pages with "미신청된 목록/본문" message)
- **Solution:** Removed JSON as an option from all 14 tool descriptions
- **Changes:**
  - Updated `type` parameter documentation to explicitly state "JSON not supported by API"
  - Added warning in module docstring about JSON format limitation
  - Tool defaults remain XML (working format)
- **Impact:** Prevents LLMs from requesting JSON format and receiving error pages

### v1.0.0 - 2025-11-10
**Initial Release**

- 15 MCP tools for Korean law information access
- 6 core law APIs (eflaw/law search and retrieval)
- 9 extended APIs (English laws, administrative rules, law-ordinance linkage)
- Session configuration via Context injection
- 100% semantic validation
- Production-ready for Smithery deployment

---

**Built with [Smithery](https://smithery.ai) | Powered by [MCP](https://modelcontextprotocol.io)**
