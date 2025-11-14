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

- **23 MCP Tools** for comprehensive Korean law information access
  - Search and retrieve Korean laws (effective date & announcement date)
  - Search and retrieve English-translated laws
  - Search and retrieve administrative rules (행정규칙)
  - Query specific articles, paragraphs, and sub-items
  - Law-ordinance linkage (법령-자치법규 연계)
  - Delegated law information (위임법령)
  - **NEW: Phase 3 - Case Law & Legal Research**
    - Court precedents (판례)
    - Constitutional Court decisions (헌재결정례)
    - Legal interpretations (법령해석례)
    - Administrative appeal decisions (행정심판례)
- **100% Semantic Validation** - All 23 tools confirmed returning real law data
- **Session Configuration** - Configure once, use across all tool calls
- **Error Handling** - Actionable error messages with resolution hints
- **Korean Text Support** - Proper UTF-8 encoding for Korean characters
- **Response Formats** - HTML or XML (multiple formats supported)

## Project Status

🎉 **Production Ready - Phase 3 Complete!**

| Metric | Status |
|--------|--------|
| **Tools Implemented** | 23/23 (100%) ✅ |
| **Semantic Validation** | 23/23 (100%) ✅ |
| **API Coverage** | ~15% of 150+ endpoints |
| **LLM Integration** | ✅ Validated (Gemini) |
| **Code Quality** | Clean, documented, tested |
| **Version** | v1.1.0 |

**Latest Achievement:** Phase 3 complete! Added 8 new tools for case law and legal research (+53% tool increase).

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
        "3. Environment variable: LAW_OC=your_value"
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
│   ├── server.py       # Main MCP server with 23 tools
│   ├── config.py       # Session configuration schema
│   ├── params.py       # Parameter resolution & mapping
│   ├── validation.py   # Input validation
│   ├── parser.py       # XML parsing utilities
│   ├── ranking.py      # Relevance ranking
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

**Current Status:** 23/23 tools implemented and validated (Phase 1-3 complete)

For implementing additional tools from the 127+ remaining APIs:
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
- **law.go.kr API:** [Official Documentation](http://open.law.go.kr)

---

## Changelog

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
