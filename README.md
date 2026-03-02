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

- **26 MCP Tools + 2 MCP Resources** for comprehensive Korean law information access
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
  - **Phase 4 - Article Citation Extraction**
    - Extract legal citations from any law article (100% accuracy)
  - **NEW: Phase 5 - AI-Powered Search**
    - Semantic search for natural language queries (aiSearch)
    - Related laws discovery (aiRltLs_search)
  - **MCP Resources - Law ID Cache**
    - Cached mapping of ~20 frequently-used law names to stable 법령ID codes
    - Template lookup by Korean name or abbreviation (`lexlink://law/{name}`)
    - Dynamic caching: search results automatically populate the cache
- **100% Semantic Validation** - All 26 tools confirmed returning real law data
- **Error Handling** - Actionable error messages with resolution hints
- **Korean Text Support** - Proper UTF-8 encoding for Korean characters
- **Response Formats** - HTML or XML (multiple formats supported)

## Project Status

🎉 **Production Ready - Phase 5 Complete!**

| Metric | Status |
|--------|--------|
| **Tools Implemented** | 26/26 (100%) ✅ |
| **Semantic Validation** | 26/26 (100%) ✅ |
| **MCP Prompts** | 6/6 (100%) ✅ |
| **MCP Resources** | 2 (1 static + 1 template) ✅ |
| **API Coverage** | ~17% of 150+ endpoints |
| **LLM Integration** | ✅ Validated (Gemini) |
| **Code Quality** | Clean, documented, tested |
| **Version** | v1.5.0 |

**Latest:** Smithery dependency removed. Clean 2-tier OC resolution (tool arg > env var), 9 fewer dependencies.

## Prerequisites

- **Python 3.10+**
- **law.go.kr OC identifier**: Register at [open.law.go.kr](https://open.law.go.kr)

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure Your OC Identifier

**Option A: Environment Variable (Recommended)**
```bash
# Set OC in your environment
export OC=your_id_here
```

**Option B: Pass in Tool Arguments**
```python
# Override OC in each tool call
eflaw_search(query="법령명", oc="your_id")
```

### 3. Run the Server

```bash
# Stdio transport (for Claude Code, Cursor, etc.)
OC=your_oc uv run stdio

# HTTP transport (for Kakao PlayMCP)
OC=your_oc TRANSPORT=http uv run serve
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

### Phase 5: AI-Powered Search (2 tools - NEW!)

#### 25. `aiSearch` - AI-Powered Semantic Law Search
⭐ **PREFERRED TOOL for vague or natural language queries.** Use this FIRST when user's intent is unclear or conversational.

Uses intelligent/semantic search to find relevant law articles with full article text.

```python
aiSearch(
    query="뺑소니 처벌",           # Natural language query
    search=0,                      # 0: law articles, 1: appendix, 2: admin rules, 3: admin appendix
    display=20,                    # Results per page
    page=1,                        # Page number
    type="XML"                     # Response format (XML only)
)
```

**Best for:** Natural language queries like "음주운전 벌금", "이혼 재산분할", "상속 문제"

#### 26. `aiRltLs_search` - AI-Powered Related Laws Search
⭐ **PREFERRED TOOL for discovering related laws from vague topics.** Use this when user wants to explore laws around a general subject.

Finds laws semantically related to a given law name or keyword.

```python
aiRltLs_search(
    query="민법",                  # Law name or keyword
    search=0,                      # 0: law articles, 1: admin rule articles
    type="XML"                     # Response format (XML only)
)
```

**Best for:** Finding related laws like "민법" → 상법, 의료법, 소송촉진법

### Tool Selection Guide

When searching Korean law, select tools based on query clarity:

| Query Type | Recommended Tools | Examples |
|------------|-------------------|----------|
| 🔍 **Vague/Natural language** | `aiSearch`, `aiRltLs_search` | "음주운전 처벌", "이혼 재산분할" |
| 📋 **Specific law/article** | `eflaw_search`, `law_search` | "형법 제148조의2", "민법 상속편" |
| ⚖️ **Case law** | `prec_search`, `detc_search` | "대법원 2023다12345" |
| 🔗 **Related laws** | `aiRltLs_search` | "민법과 관련된 법률" |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OC` | *(required)* | law.go.kr API identifier (email local part) |
| `LEXLINK_BASE_URL` | `http://www.law.go.kr` | API base URL |
| `LEXLINK_TIMEOUT` | `60` | HTTP request timeout in seconds |
| `SLIM_RESPONSE` | *(unset)* | Set `true` to remove redundant raw XML when parsed data exists (for PlayMCP) |
| `TRANSPORT` | `sse` | Transport type: `sse` or `http` |

### OC Priority

When resolving the OC identifier:
1. **Tool argument** (highest priority) - `oc` parameter in tool call
2. **Environment variable** - `OC` env var (set via .env or HTTP header middleware)

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
        "2. Environment variable: OC=your_value"
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

### Trajectory 8: AI-Powered Natural Language Search (Phase 5)
**User Query:** "What's the penalty for hit-and-run accidents?"

**Tool Calls:**
1. `aiSearch(query="뺑소니 처벌", search=0, display=20, type="XML")` → Semantic search for hit-and-run penalties

**Result:** LLM receives full article text from relevant laws (특정범죄 가중처벌 등에 관한 법률 제5조의3) with complete provisions about hit-and-run penalties, enabling comprehensive answer without needing to know specific law names.

---

### Trajectory 9: Discovering Related Laws (Phase 5)
**User Query:** "What laws are related to the Civil Code?"

**Tool Calls:**
1. `aiRltLs_search(query="민법", search=0, type="XML")` → Find semantically related laws

**Result:** LLM discovers related laws like 상법 (Commercial Act), 의료법 (Medical Service Act), 소송촉진법 (Act on Special Cases Concerning Expedition of Litigation), showing connections across legal domains.

---

### Key Patterns

1. **AI Tools for Vague Queries**: Use `aiSearch` or `aiRltLs_search` FIRST when user intent is unclear or conversational
2. **Search First, Then Retrieve**: Always search to find IDs before calling service tools
3. **Use display=50-100 for Law Searches**: Ensures exact matches are found due to relevance ranking
4. **Combine Phases**: Mix Phase 1 (laws), Phase 2 (administrative rules), Phase 3 (precedents), and Phase 5 (AI search) for complete research
5. **Type Parameter**: Always specify `type="XML"` for consistent, parseable results
6. **Article Numbers**: Use 6-digit format (e.g., "002000" for Article 20) when querying specific articles

## Development

### Project Structure

```
lexlink-ko-mcp/
├── src/lexlink/
│   ├── server.py        # Main MCP server with 26 tools
│   ├── http_server.py   # HTTP/SSE server for Kakao PlayMCP
│   ├── stdio_server.py  # Stdio transport entry point
│   ├── params.py        # Parameter resolution & mapping
│   ├── validation.py    # Input validation
│   ├── parser.py        # XML parsing utilities
│   ├── ranking.py       # Relevance ranking
│   ├── citation.py      # Article citation extraction (Phase 4)
│   ├── client.py        # HTTP client for law.go.kr API
│   ├── errors.py        # Error codes & responses
│   ├── raw_logger.py    # PlayMCP traffic logging
│   └── log_processor.py # Log format converter
├── logs/playmcp/         # PlayMCP traffic logs (daily JSONL)
├── pyproject.toml        # Project configuration
└── README.md             # This file
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
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m e2e
```

### Adding New Tools

**Current Status:** 26/26 tools implemented and validated (Phase 1-5 complete)

For implementing additional tools from the 124+ remaining APIs:
1. Follow the pattern established in `src/lexlink/server.py`
2. Use `ctx: Context = None` parameter for MCP logging/progress
3. Use generic parser functions (`extract_items_list`, `update_items_list`)
4. Add semantic validation tests

**Tool Implementation Pattern:**
- Each tool is a decorated function with MCP schema
- Uses `ctx: Context = None` parameter for MCP context
- 2-tier OC resolution: tool arg > env var
- Generic parser functions work with any XML tag
- Comprehensive error handling with actionable hints

## Deployment

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

For detailed deployment instructions (AWS EC2, Nginx, systemd, HTTPS), see [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md).

### PlayMCP Traffic Logging

LexLink includes built-in logging for PlayMCP traffic analysis. Logs are saved in dashboard-compatible JSONL format.

**Log Location:** `logs/playmcp/YYYY-MM-DD.jsonl`

**Log Schema:**
```json
{
  "rpc_id": "3",
  "request_id": "d8ee45eb",
  "session_id": "9ff9dc23431848a4901b4cb6326ba5bd",
  "timestamp": "2025-12-25T05:40:23.957987",
  "duration_ms": 1.52,
  "method": "tools/call",
  "tool_name": "aiSearch",
  "params": { "arguments": {"query": "뺑소니 처벌"} },
  "client": "PlayMCP",
  "client_version": "2025.0.0",
  "protocol_version": "2025-06-18",
  "client_ip": "220.64.111.219",
  "oc": "user_id",
  "status": "success",
  "status_code": 200,
  "result": { ... }
}
```

**Features:**
- Daily log rotation (one file per day)
- Dashboard-compatible format for filtering and analysis
- Captures request/response pairs with timing
- SSE streaming response parsing

**Converting Old Raw Logs:**
```bash
uv run python -m lexlink.log_processor input.jsonl output.jsonl
```

## Troubleshooting

### "OC parameter is required" error

**Solution:** Set your OC identifier using one of the three methods above.

### Korean characters not displaying correctly

**Solution:** Ensure your terminal supports UTF-8:
```bash
export PYTHONIOENCODING=utf-8
```

### "Timeout" errors

**Solution:** Increase timeout via environment variable:
```bash
export LEXLINK_TIMEOUT=90  # Increase from default 60s
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

## Support

- **Issues:** [GitHub Issues](https://github.com/rabqatab/LexLink-ko-mcp/issues)
- **law.go.kr API:** [Official Documentation](http://open.law.go.kr)

---

## Changelog

### v1.5.0 - 2026-02-28
**Refactor: Remove Smithery Dependency**

- Removed `smithery` package and 8 transitive dependencies
- Simplified OC resolution to 2-tier (tool arg > env var)
- Added `stdio_server.py` entry point for stdio transport
- See [CHANGELOG.md](CHANGELOG.md) for full details

For the full changelog (v1.0.0 – v1.5.0), see [CHANGELOG.md](CHANGELOG.md).

---

**Powered by [MCP](https://modelcontextprotocol.io)**
