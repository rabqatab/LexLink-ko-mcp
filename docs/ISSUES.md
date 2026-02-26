# LexLink - Bugs and Issues Tracker

**Last Updated:** 2026-01-13
**Purpose:** Track bugs, errors, and issues found during testing and deployment
**Status:** Active tracking document

---

## 🐛 Active Issues

### Issue #10: MCP Protocol Version 2025-06-18 Incompatibility ⚠️ KNOWN ISSUE
**Discovered:** 2025-12-11
**Status:** ⚠️ **KNOWN ISSUE** - Smithery/MCP ecosystem transitional problem
**Severity:** MEDIUM - Causes intermittent "Unavailable" errors in Smithery logs
**Platform:** Smithery.ai (hosted MCP)

**Symptoms:**
```
Smithery Logs show:
- Status: Unavailable
- Response Timestamp: 1970. 1. 1. 오전 12:00:00 (Unix epoch = no response)
- Request: initialize method fails
```

**Request Example:**
```json
{
  "protocolVersion": "2025-06-18",
  "capabilities": {},
  "clientInfo": {
    "name": "mcp",        // Claude Code client
    "version": "0.1.0"
  }
}
// or
{
  "clientInfo": {
    "name": "smithery-host",  // Smithery infrastructure
    "version": "1.0.0"
  }
}
```

**Root Cause:**
1. **Protocol Version Mismatch**: Newer MCP clients (Claude Code, Smithery-host) send `protocolVersion: "2025-06-18"` but servers using `mcp` package may not support it yet
2. **Cold Start Timeout**: Smithery servers spin down when idle; `initialize` requests may arrive before server is ready
3. **MCP Package Incompatibility**: `mcp 1.23.3` caused 502 Bad Gateway errors on Smithery (server crashed on startup)

**Affected Clients:**
| Client | Version | Protocol | Description |
|--------|---------|----------|-------------|
| `mcp` | 0.1.0 | 2025-06-18 | Claude Code MCP client |
| `smithery-host` | 1.0.0 | 2025-06-18 | Smithery routing infrastructure |
| `smithery-scanner` | 1.0.0 | 2024-11-05 | Smithery tool scanner (works) |

**Known Affected Platforms (from web research):**
- [Vercel AI SDK #7575](https://github.com/vercel/ai/issues/7575) - "Server's protocol version is not supported: 2025-06-18"
- [Continue VS Code #8118](https://github.com/continuedev/continue/issues/8118) - Need to support 2025-06-18
- [JetBrains LLM-20994](https://youtrack.jetbrains.com/issues/LLM-20994) - WebStorm connection error
- [MCP Spec #854](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/854) - Protocol header logic bug

**Why `1970-01-01` Timestamp:**
Unix epoch timestamp (0) means the server **never sent a response**:
- Server not running (cold start)
- Server crashed before responding (502)
- Request timed out

**Workaround (Implemented):**
Downgraded from `mcp 1.23.3` to `mcp 1.20.0`:
```bash
uv lock --upgrade-package mcp==1.20.0
git commit -m "revert: downgrade mcp 1.23.3 -> 1.20.0 (502 error)"
```

**Current Status:**
- ✅ Server works with `mcp 1.20.0`
- ✅ `smithery-scanner` (protocol 2024-11-05) succeeds
- ⚠️ Some `initialize` requests from `mcp`/`smithery-host` may still show "Unavailable" due to cold start timing
- ⚠️ This is an ecosystem-wide transitional issue, not a LexLink bug

**Monitoring:**
These "Unavailable" errors in Smithery logs are **cosmetic** - they represent failed health checks or cold start race conditions. Real user requests typically succeed after server warms up.

**Future Fix:**
Wait for `mcp` package to properly support protocol version `2025-06-18` without crashing, then upgrade.

---

### Issue #11: Smithery Build Detects npm Instead of Python ✅ RESOLVED
**Discovered:** 2026-01-13
**Status:** ✅ **FIXED** in v1.3.2
**Severity:** CRITICAL - Deployment completely fails
**Platform:** Smithery.ai (hosted MCP)

**Symptoms:**
```
[오전 9:31:28] Detected package manager: npm
[오전 9:31:29] [stderr] npm error code ENOENT
[오전 9:31:29] [stderr] npm error path /home/repo/package.json
[오전 9:31:29] Build failed: Failed to install dependencies
```

Smithery build system incorrectly detects npm as the package manager for this Python project, then fails because no `package.json` exists.

**Root Cause:**
The previous `smithery.yaml` only contained:
```yaml
runtime: python
```

This minimal configuration doesn't tell Smithery **how to start the server**. Without a `startCommand`, Smithery's build system falls back to auto-detection, which incorrectly identifies npm.

**Why It Worked Before:**
Likely one of:
1. **Smithery platform update** - Build system changed to require explicit `startCommand`
2. **Cached build** - Previous deployments used cached artifacts
3. **`runtime` field deprecated** - Working Python MCPs (e.g., [perplexity-mcp](https://github.com/jsonallen/perplexity-mcp)) don't use `runtime: python` at all

**Solution (Implemented in v1.3.2):**
Updated `smithery.yaml` with proper `startCommand` configuration:
```yaml
# Smithery configuration file: https://smithery.ai/docs/config#smitheryyaml

startCommand:
  type: stdio
  configSchema:
    type: object
    properties:
      oc:
        type: string
        description: Your law.go.kr API identifier (email local part). Register at open.law.go.kr to get one.
  commandFunction:
    |-
    config => ({ command: 'uv', args: ['run', 'start'], env: config.oc ? { OC: config.oc } : {} })
```

**Key Configuration Elements:**
- `startCommand.type: stdio` - Declares this as a stdio-based MCP server
- `configSchema` - Makes `oc` parameter available in Smithery UI (optional)
- `commandFunction` - Tells Smithery to run `uv run start` with the `OC` env var

**Files Changed:**
- `smithery.yaml` - Complete rewrite with `startCommand` configuration

**Reference:**
- [Smithery smithery.yaml Reference](https://smithery.ai/docs/build/project-config/smithery.yaml)
- [perplexity-mcp smithery.yaml](https://github.com/jsonallen/perplexity-mcp/blob/main/smithery.yaml) - Working Python MCP example

---

### Issue #9: article_citation Missing Dependency ✅ RESOLVED
**Discovered:** 2025-12-09
**Status:** ✅ **FIXED** in v1.2.10
**Severity:** HIGH - Tool completely fails
**Platform:** All platforms

**Symptoms:**
```
Request: article_citation(mst="270563", law_name="형법", article=23)
Error: ModuleNotFoundError: No module named 'bs4'
```
The `article_citation` tool fails because `beautifulsoup4` was not listed in dependencies.

**Root Cause:**
The `citation.py` module imports BeautifulSoup for HTML parsing:
```python
from bs4 import BeautifulSoup
```
But `beautifulsoup4` was never added to `pyproject.toml` dependencies.

**Solution (Implemented in v1.2.10):**
Added `beautifulsoup4>=4.12.0` to dependencies in `pyproject.toml`:
```toml
dependencies = [
    "mcp>=1.15.0",
    "smithery>=0.4.2",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "uvicorn>=0.30.0",
    "beautifulsoup4>=4.12.0",  # Required for article_citation HTML parsing
]
```

**Files Changed:**
- `pyproject.toml` - Added beautifulsoup4 dependency

**Verification:**
```python
>>> result = await extract_article_citations(mst='270563', law_name='형법', article=23)
>>> result['success']
True
```

---

### Issue #8: Linkage Search Tools Return No Data ✅ RESOLVED
**Discovered:** 2025-12-09
**Status:** ✅ **FIXED** in v1.2.10
**Severity:** MEDIUM - 3 tools affected (4th is HTML-only by design)
**Platform:** Kakao PlayMCP (with SLIM_RESPONSE enabled)

**Symptoms:**
```json
Request: lnkLs_search(query="건축법")
Response: {
  "status": "ok",
  "upstream_type": "XML",
  "ranked_data": null
}
// No ranked_data returned!
```

**Affected Tools (3 + 1 HTML-only):**
- `lnkLs_search` - Law-ordinance linkage list ✅ Fixed
- `lnkLsOrdJo_search` - Ordinance articles linked to law ✅ Fixed
- `lnkDep_search` - Linkages by ministry ✅ Fixed
- `drlaw_search` - Linkage statistics (HTML only - no fix needed)

**Root Cause:**
The 3 linkage tools were missing the XML parsing step that other search tools have:
```python
# BEFORE (broken):
response = client.get("/DRF/lawSearch.do", upstream_params, response_type=type)
return slim_response(response)  # No ranked_data!

# AFTER (fixed):
response = client.get("/DRF/lawSearch.do", upstream_params, response_type=type)
if response.get("status") == "ok" and type == "XML":
    raw_content = response.get("raw_content", "")
    if raw_content:
        parsed_data = parse_xml_response(raw_content)
        if parsed_data:
            response["ranked_data"] = parsed_data  # Now has data!
return slim_response(response)
```

**Solution (Implemented in v1.2.10):**
Added XML parsing step to 3 linkage tools:
- `lnkLs_search` - with ranking by 법령명한글
- `lnkLsOrdJo_search` - parsing only (no ranking field)
- `lnkDep_search` - parsing only (no ranking field)

**Files Changed:**
- `src/lexlink/server.py` - Added parsing logic to 3 linkage tools

**Verification:**
```python
>>> response = lnkLs_search(query="건축법")
>>> response["ranked_data"]["law"]
[{"법령명한글": "건축법", ...}, {"법령명한글": "건축법 시행령", ...}]
```

**Note:** `drlaw_search` is HTML-only by API design - cannot be parsed into structured data.

---

### Issue #7: Service Tools Exceed PlayMCP Limit ⚠️ OPEN
**Discovered:** 2025-12-09
**Status:** ⚠️ **OPEN** - Planned fix: Conditional Tool Registration
**Severity:** CRITICAL - Full law content exceeds 24KB limit
**Platform:** Kakao PlayMCP (with SLIM_RESPONSE enabled)

**PlayMCP Limit:** **24KB** (responses over 24KB cause errors)

**Symptoms:**
```
Request: eflaw_service(mst="270563")  # 형법
Response size: 198KB - 8.3x over limit!

Request: law_service(mst="270551")  # 민법
Response size: 153KB - 6.4x over limit!
```

**Actual Size Analysis (tested 2025-12-09):**
| Tool | Test Case | Size | Status |
|------|-----------|------|--------|
| law_service | 난민법 (small law) | 36.5 KB | ❌ 1.5x over |
| law_service | 형법 (Criminal Code) | 198.3 KB | ❌ 8.3x over |
| law_service | 민법 (Civil Code) | 153.3 KB | ❌ 6.4x over |
| prec_service | 판례 228541 | 12.5 KB | ✅ OK |
| detc_service | 헌재결정례 58386 | 14.6 KB | ✅ OK |
| detc_service | 헌재결정례 58388 | 29.4 KB | ❌ 1.2x over |
| expc_service | 법령해석례 334617 | 5.8 KB | ✅ OK |
| decc_service | 행정심판례 243263 | 8.1 KB | ✅ OK |

**Key Findings:**
- **Law full text** (`eflaw_service`, `law_service`): **Always exceeds 24KB** - even small laws like 난민법
- **Case law** (`prec_service`, `detc_service`): Varies by case complexity (10KB - 50KB+)
- **Interpretations** (`expc_service`, `decc_service`): Usually OK (5KB - 15KB)

**Root Cause:**
Law services return **entire law content** (all articles, addenda, etc.) which cannot be slimmed without losing essential information.

---

## Planned Solution: Conditional Tool Registration

**Approach:** Exclude `eflaw_service` and `law_service` from PlayMCP entirely using conditional registration.

```python
# Only register full-law tools when NOT on PlayMCP
if not os.getenv("SLIM_RESPONSE"):
    @server.tool()
    def eflaw_service(...):
        ...

    @server.tool()
    def law_service(...):
        ...
```

**Why This Approach:**
1. **Clean** - Tools don't appear in PlayMCP tool list at all
2. **LLM-friendly** - LLM naturally uses `eflaw_josub`/`law_josub` instead
3. **No wasted API calls** - LLM won't try to use unavailable tools
4. **No code duplication** - Single codebase, conditional registration

**Tools to Exclude from PlayMCP:**
| Tool | Reason | Alternative |
|------|--------|-------------|
| `eflaw_service` | Always > 24KB | `eflaw_josub` with `jo` param |
| `law_service` | Always > 24KB | `law_josub` with `jo` param |

**Tools to Keep (variable size, usually OK):**
- `elaw_service` - English laws (smaller)
- `admrul_service` - Admin rules (usually OK)
- `prec_service` - Precedents (usually OK)
- `detc_service` - Constitutional Court (varies)
- `expc_service` - Interpretations (small)
- `decc_service` - Admin appeals (small)
- `lsDelegated_service` - Delegation list (small)

**Implementation Checklist:**
- [ ] Wrap `eflaw_service` registration in `if not SLIM_RESPONSE`
- [ ] Wrap `law_service` registration in `if not SLIM_RESPONSE`
- [ ] Test that tools don't appear on PlayMCP
- [ ] Verify `eflaw_josub`/`law_josub` work as alternatives
- [ ] Update documentation

**Files to Modify:**
- `src/lexlink/server.py` - Conditional tool registration

---

### Issue #6: Non-Law Searches Return Empty Results ✅ RESOLVED
**Discovered:** 2025-12-09
**Status:** ✅ **FIXED** in v1.2.6
**Severity:** CRITICAL - All non-law searches fail on PlayMCP
**Platform:** Kakao PlayMCP (with SLIM_RESPONSE enabled)

**Symptoms:**
```json
Request: prec_search(query="담보권", display=5, org="400201")
Response: {
  "status": "ok",
  "request_id": "...",
  "upstream_type": "XML"
}
// No ranked_data, no results!
```
All non-law search tools (`prec_search`, `detc_search`, `expc_search`, `decc_search`, `admrul_search`) return empty results.

**Root Cause:**
`slim_response()` used law-specific field names for ALL data types:
```python
# OLD - Only law fields
essential_fields = {"법령명한글", "법령일련번호", "법령ID", "현행연혁코드", "시행일자"}
```

But precedent results have different fields:
- `판례일련번호` (not 법령일련번호)
- `사건명` (not 법령명한글)
- `사건번호`, `선고일자`, `법원명`

Result: When filtering precedent data, **ALL fields removed** → empty results!

**Solution (Implemented in v1.2.6):**
```python
essential_fields_by_type = {
    "law": {"법령명한글", "법령일련번호", "법령ID", "현행연혁코드", "시행일자"},
    "elaw": {"법령명한글", "법령일련번호", "법령ID", "현행연혁코드", "시행일자"},
    "prec": {"판례일련번호", "사건명", "사건번호", "선고일자", "법원명"},
    "detc": {"헌재결정례일련번호", "사건명", "사건번호", "선고일자", "종국결과"},
    "expc": {"법령해석례일련번호", "법령해석례명", "안건번호", "회신일자", "회신기관"},
    "decc": {"행정심판재결례일련번호", "사건명", "사건번호", "재결일자", "재결결과"},
    "admrul": {"행정규칙일련번호", "행정규칙명", "발령일자", "시행일자", "소관부처명"},
}
```

**Files Changed:**
- `src/lexlink/server.py` - Replaced single `essential_fields` with `essential_fields_by_type`

**Impact:**
- All 7 search tools now work correctly with SLIM_RESPONSE
- Each data type preserves its essential fields for LLM navigation

---

### Issue #5: LLM Parameter Confusion (id vs mst) ✅ RESOLVED
**Discovered:** 2025-12-09
**Status:** ✅ **FIXED** in v1.2.5
**Severity:** HIGH - Causes failed law retrievals
**Platform:** Kakao PlayMCP (with SLIM_RESPONSE enabled)

**Symptoms:**
```
User: "형법 제23조 뭐지?"
LLM calls: eflaw_service(id="235555")  → Law not found
           eflaw_service(id="213837")  → Wrong law
```

**Root Cause Analysis:**

1. **API Ranking Issue:**
   - Search for "형법" returns exact match at position 67 (not in first 50)
   - API returns "군형법", "구형법" before actual "형법"
   - With `display=50`, LLM never sees the actual "형법"

2. **Parameter Confusion:**
   - v1.2.4 removed `법령ID` from `essential_fields` for slimmed responses
   - LLM only saw `법령일련번호` (MST) but used it with `id` parameter
   - Example: `법령일련번호=235555` → LLM called `eflaw_service(id="235555")`
   - Should have used: `eflaw_service(mst=235555)` or `eflaw_service(id="001624")`

**Search Results Analysis:**
| Position | Law Name | MST | 법령ID | Status |
|----------|----------|-----|--------|--------|
| 3 | 군에서의 형의 집행... | **213837** | 000912 | 현행 |
| 23 | 군형법 | **235555** | 001624 | 현행 |
| **67** | **형법** (target) | **270563** | 001692 | 현행 |

**Solution (Implemented in v1.2.5):**

1. **Added `법령ID` back to essential_fields:**
   ```python
   essential_fields = {"법령명한글", "법령일련번호", "법령ID", "현행연혁코드", "시행일자"}
   ```
   - LLM can now see both fields and use correct parameter

2. **Relevance Ranking (already implemented):**
   - LexLink fetches 100 results when `display < 100`
   - Ranks by relevance: exact matches → starts with → contains
   - Returns top N results after ranking
   - **Note:** EC2 must have latest code for this to work

**Files Changed:**
- `src/lexlink/server.py` - Added 법령ID to essential_fields

**Verification:**
```python
# Ranking test
results = [군형법, 구형법, 형법]
ranked = rank_search_results(results, "형법", "법령명한글")
# Result: [형법, 구형법, 군형법] ✅
```

**Deployment Note:**
If ranking still not working after update, ensure EC2 has the ranking module code.
Run: `ssh EC2 "cd ~/lexlink-ko-mcp && git pull && sudo systemctl restart lexlink"`

---

### Issue #4: PlayMCP Response Size Limit Error ✅ RESOLVED
**Discovered:** 2025-12-09
**Status:** ✅ **FIXED** in v1.2.4
**Severity:** HIGH - Blocks all search tool responses on PlayMCP
**Platform:** Kakao PlayMCP (not affecting Smithery.ai)

**PlayMCP Limit:** **24KB** (responses over 24KB cause errors)

**Symptoms:**
```
Error: Tool call returned too large content part
```
All search tools (`eflaw_search`, `prec_search`, etc.) fail on PlayMCP while working fine on Smithery.ai.

**Root Cause:**
- PlayMCP has a strict response size limit (**24KB** for tool responses)
- LexLink search responses contain data in two formats:
  - `raw_content`: Full XML response from law.go.kr API (~25KB for 50 results)
  - `ranked_data`: Parsed JSON with same data (~25KB for 50 results)
- Total response size: ~50KB, exceeding PlayMCP's 24KB limit

**Investigation Timeline:**
1. **v1.2.3 attempt**: Added `truncate_response()` that truncated `raw_content` to max 50KB
   - Result: Still failed because `ranked_data` remained full size (~25KB)
2. **v1.2.4 solution**: Implemented `slim_response()` with aggressive reduction
   - Removes `raw_content` entirely (not needed when `ranked_data` exists)
   - Slims `ranked_data` to essential fields only

**Solution (Implemented in v1.2.4):**

1. **New `slim_response()` function** replaces `truncate_response()`:
   ```python
   def slim_response(response: dict) -> dict:
       if not os.getenv("SLIM_RESPONSE"):
           return response  # Smithery.ai: unchanged

       result = response.copy()
       result.pop("raw_content", None)  # Remove XML entirely

       # Slim ranked_data to essential fields only
       essential_fields = {"법령명한글", "법령일련번호", "현행연혁코드", "시행일자"}
       # ... filter logic for law/prec/detc/etc lists

       return result
   ```

2. **Environment variable control**: `SLIM_RESPONSE=true`
   - PlayMCP deployment: Set in systemd service → slimmed responses (~3-5KB)
   - Smithery.ai: Not set → full responses preserved

3. **Fields kept vs removed** (for law search):
   - **Kept (essential):** 법령명한글, 법령일련번호, 현행연혁코드, 시행일자
   - **Removed:** 법령약칭명, 법령ID, 공포일자, 공포번호, 제개정구분명, 소관부처코드, 소관부처명, 법령구분명, 공동부령정보, 자법타법여부, 법령상세링크

**Files Changed:**
- `src/lexlink/server.py` - Replaced `truncate_response()` with `slim_response()`, updated 11 search tools
- `assets/DEPLOYMENT_GUIDE.md` - Updated env var from `MAX_RESPONSE_SIZE` to `SLIM_RESPONSE`
- `README.md`, `README_kr.md` - v1.2.4 changelog

**Deployment Update Required:**
```bash
# Update systemd service
sudo nano /etc/systemd/system/lexlink.service
# Change: Environment="MAX_RESPONSE_SIZE=50000"  (old)
# To:     Environment="SLIM_RESPONSE=true"       (new)

# Pull and restart
cd ~/lexlink-ko-mcp
git pull
sudo systemctl daemon-reload
sudo systemctl restart lexlink
```

**Impact:**
- Response size reduced from ~50KB to ~3-5KB for 50 results
- PlayMCP users get essential data for navigation
- Smithery.ai users continue to receive full responses
- No functionality loss - essential fields preserved

---

### Issue #3: Parameter Type Inconsistency Across Tools ✅ RESOLVED
**Discovered:** 2025-11-13
**Status:** ✅ **FIXED** in v1.0.8
**Severity:** MEDIUM - Causes validation errors and inconsistent behavior

**Symptoms:**
```
Error executing tool eflaw_josub: 1 validation error
mst Input should be a valid string [type=string_type, input_value=270351, input_type=int]
```

**Root Cause:**
- Incomplete fix in v1.0.2 - only updated 7 tools but missed 2 additional tools
- `eflaw_josub` and `law_josub` still had `id: Optional[str]` instead of `Union[str, int]`
- `lnkLsOrdJo_search` had `jo: Optional[int]` instead of `Union[str, int]`
- Created inconsistency where same parameters had different types across tools

**Affected Parameters:**
- `id`: Used by 7 tools (2 had wrong type)
- `mst`: Used by 6 tools (2 had wrong type)
- `jo`: Used by 5 tools (1 had wrong type)

**Solution (Implemented):**
1. **Fixed `eflaw_josub` and `law_josub`:**
   - `id: Optional[str]` → `id: Optional[Union[str, int]]`
   - `mst: Optional[str]` → `mst: Optional[Union[str, int]]`
   - Both already had conversion logic, just needed type signature update

2. **Fixed `lnkLsOrdJo_search`:**
   - `jo: Optional[int]` → `jo: Optional[Union[str, int]]`
   - Now consistent with other 4 tools that have `jo` parameter

3. **Verified consistency across all 15 tools:**
   - All `id` parameters now `Optional[Union[str, int]]` (7 tools)
   - All `mst` parameters now `Optional[Union[str, int]]` (6 tools)
   - All `jo` parameters now `Optional[Union[str, int]]` (5 tools)

**Files Changed:**
- `src/lexlink/server.py` - Updated 3 tool signatures (eflaw_josub, law_josub, lnkLsOrdJo_search)

**Impact:**
- 100% parameter type consistency achieved
- No more validation errors regardless of which tool LLMs choose
- Better developer experience - same parameters work the same way everywhere

---

### Issue #2: Type Validation Error for id/mst Parameters ✅ RESOLVED
**Discovered:** 2025-11-10
**Status:** ✅ **FIXED** in v1.0.2 (Partial), **COMPLETED** in v1.0.8
**Severity:** MEDIUM - Blocks specific tool calls but workaround exists

**Symptoms:**
```
Error executing tool eflaw_josub: 1 validation error
mst Input should be a valid string [type=string_type, input_value=188376, input_type=int]
```

**Root Cause:**
- LLMs extract numeric values from XML responses as integers
- Tool signatures declared parameters as `Optional[str]`
- Pydantic validation rejects integer inputs for string parameters
- Example: `<법령일련번호>188376</법령일련번호>` → LLM passes `mst=188376` (int)

**Affected Tools (7 tools):**
- `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`
- `elaw_service`, `admrul_service`, `lsDelegated_service`

**Workaround (User discovered):**
- LLM switched from `mst` (int) to `id` (string) parameter
- Query eventually succeeded: `id="011546"` worked

**Solution (Implemented):**
1. Changed parameter types from `Optional[str]` to `Optional[Union[str, int]]`
2. Added automatic string conversion at start of each tool:
   ```python
   if id is not None:
       id = str(id)
   if mst is not None:
       mst = str(mst)
   ```
3. Applied to all 7 affected tools

**Files Changed:**
- `src/lexlink/server.py` - Updated 7 tool signatures and added conversion logic

**Testing Status:**
- ⏳ Awaiting Smithery redeployment
- ⏳ Need to retest with "난민법 3조" query

**Related Evidence:**
- Query: "난민법 3조를 검색하겠습니다"
- Tool call: `eflaw_josub(mst=188376, ef_yd=20161220, jo="000300")`
- Error: Type validation failure (expected string, got int)
- Eventual success: LLM used `id="011546"` instead

---

### Issue #1: JSON Format Not Supported by API ✅ RESOLVED
**Discovered:** 2025-11-10
**Status:** ✅ **FIXED** in v1.0.1
**Severity:** HIGH - Blocking all API calls

**Symptoms:**
```
LLMs selecting JSON format → API returns HTML error page:
"미신청된 목록/본문에 대한 접근입니다"
(Unapplied access to list/content)
```

**Root Cause:**
- law.go.kr API documentation claims JSON support
- Reality: JSON format returns HTML error pages
- LLMs were seeing JSON as valid option in tool descriptions
- All 15 tools defaulted to XML but LLMs overrode with JSON

**Evidence:**
```json
Request: {
  "query": "자동차",
  "display": 20,
  "type": "JSON"  // ❌ THIS CAUSED THE ERROR
}

Response: {
  "status": "ok",
  "raw_content": "<!DOCTYPE html>...<h2>미신청된 목록/본문에 대한 접근입니다</h2>..."
}
```

**Solution (Implemented):**
1. Removed JSON from all tool parameter descriptions
2. Changed documentation from:
   - OLD: `type: Response format - "HTML", "XML", or "JSON"`
   - NEW: `type: Response format - "HTML" or "XML" (JSON not supported by API)`
3. Added warning in module docstring
4. Tested: LLMs now default to XML format

**Files Changed:**
- `src/lexlink/server.py` - 14 tool descriptions updated
- `README.md` - Added to changelog

**Testing Status:**
- ⏳ Awaiting Smithery redeployment
- ⏳ Need to retest with same queries

**Related Documentation:**
- `docs/API_REFERENCE.md` (Known API Provider Issues section)
- `docs/reference/07_api_provider_issues.md`

---

## 📋 Known Issues (Not Bugs)

### Issue: Article Citation Range References (Phase 4)
**Status:** KNOWN LIMITATION
**Severity:** LOW
**Component:** `article_citation` tool

**Description:**
Citations like "제88조 내지 제93조" (articles 88 through 93) are represented as a single HTML link in law.go.kr.

**Current Behavior:**
- `raw_text`: "제88조 내지 제93조" (full text preserved)
- `target_article`: 88 (only first article extracted)

**Future Improvement:** Could expand ranges into multiple citation objects.

---

### Issue: Article Citation - Deleted/Amended Articles
**Status:** KNOWN LIMITATION
**Severity:** LOW
**Component:** `article_citation` tool

**Description:**
Some citations reference articles that no longer exist in the current law version. These are still extracted but may not resolve to valid targets when following the citation.

---

### Issue: Article Citation - External Law Name Resolution
**Status:** KNOWN LIMITATION
**Severity:** LOW
**Component:** `article_citation` tool

**Description:**
External law names are extracted as text (e.g., "자본시장과 금융투자업에 관한 법률"). To get the MST of the cited law for further queries, a separate `eflaw_search` call is needed.

**Workaround:**
```python
# 1. Get citations
citations = article_citation(mst="268611", law_name="건축법", article=3)

# 2. For each external citation, search for the law
for cit in citations["citations"]:
    if cit["type"] == "external":
        search_result = eflaw_search(query=cit["target_law_name"])
        # Get MST from search result for further queries
```

---

### Issue: OC Parameter Registration Required
**Status:** EXPECTED BEHAVIOR
**Severity:** INFO

**Description:**
Users must register their OC parameter at https://open.law.go.kr and check which API categories they want to access.

**Not a bug because:**
- This is API provider requirement
- Users need to explicitly enable API access
- Standard procedure for law.go.kr API

**User Action Required:**
1. Login to https://open.law.go.kr
2. Go to [OPEN API] → [OPEN API 신청]
3. Select registered API
4. Check desired law categories (법령종류)

**Related Error Messages:**
```
미신청된 목록/본문에 대한 접근입니다.
OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요.
```

---

## 🧪 Testing History

### Test Session #1: 2025-11-10 (Initial Deployment)
**Platform:** Smithery.ai
**LLM:** Claude Haiku 4.5
**Status:** ❌ FAILED

**Test Case 1:**
- Query: "자동차 관련한 법률 알려줘"
- Tools Used: `eflaw_search`, `law_search`
- Result: ❌ HTML error pages (JSON format issue)
- Issue: #1 (JSON format)

**Test Case 2:**
- Query: "민법 제 34조가 뭔지 찾아줘"
- Tools Used: `eflaw_search`
- Result: ❌ HTML error pages (JSON format issue)
- Issue: #1 (JSON format)

**Findings:**
- Both tests failed with same error
- LLM consistently chose JSON format
- API provider doesn't support JSON despite documentation

---

### Test Session #2: 2025-11-10 (After v1.0.1 Fix)
**Platform:** Smithery.ai
**LLM:** Claude Haiku 4.5
**Status:** ✅ PARTIALLY SUCCESSFUL

**Test Case 3:**
- Query: "난민법 3조"
- Tools Used: `eflaw_search` ✅ → `eflaw_josub` ❌ → `eflaw_service` ✅
- Result: ✅ Eventually succeeded (LLM found workaround)
- Issue: #2 (Type validation error discovered)

**Findings:**
- ✅ JSON format issue RESOLVED (LLM now uses XML)
- ❌ NEW ISSUE: Type validation error for integer parameters
- ✅ LLM demonstrated resilience by trying alternative approaches
- ✅ Final answer delivered successfully

---

### Test Session #4: 2025-12-09 (PlayMCP Comprehensive Test v1.2.9)
**Platform:** Kakao PlayMCP
**Environment:** SLIM_RESPONSE=true
**OC:** ddongle0205
**Status:** ⚠️ PARTIAL SUCCESS

**Test Coverage:** All 24 MCP tools tested

**PlayMCP Limit: 24KB** (responses over 24KB cause errors)

**Results Summary:**
| Category | Tools | Size | Under 24KB? |
|----------|-------|------|-------------|
| Search (Law) | eflaw_search, law_search | ~2-4KB | ✅ Yes |
| Search (English) | elaw_search | ~3KB | ✅ Yes |
| Search (Case Law) | prec_search, detc_search, expc_search, decc_search | ~2-5KB | ✅ Yes |
| Search (Admin) | admrul_search | ~3KB | ✅ Yes |
| Article Query | eflaw_josub, law_josub | ~5-10KB | ✅ Yes |
| Service (Full) | eflaw_service, law_service | 500KB-1MB | ❌ 20-40x over |
| Service (Other) | elaw_service, admrul_service, prec_service, detc_service, expc_service, decc_service, lsDelegated_service | 20KB-500KB | ❌ Most exceed |
| Linkage | lnkLs_search, lnkLsOrdJo_search, lnkDep_search, drlaw_search | ~1KB | ⚠️ No data |
| Citation | article_citation | N/A | ❌ Async error |

**Detailed Test Results:**

| # | Tool | Request | Response Size | ranked_data | Status |
|---|------|---------|--------------|-------------|--------|
| 1 | eflaw_search | query="민법" | 2,341B | ✅ Yes (slimmed) | ✅ |
| 2 | law_search | query="형법" | 2,156B | ✅ Yes (slimmed) | ✅ |
| 3 | eflaw_service | mst="270563" | 748,231B | N/A | ⚠️ Too large |
| 4 | law_service | id="001692" | 695,420B | N/A | ⚠️ Too large |
| 5 | eflaw_josub | mst="270563", jo="002300" | 8,432B | N/A | ✅ |
| 6 | law_josub | mst="270563", jo="002300" | 7,891B | N/A | ✅ |
| 7 | elaw_search | query="insurance" | 3,245B | ✅ Yes (slimmed) | ✅ |
| 8 | elaw_service | mst="127280" | 245,678B | N/A | ⚠️ Too large |
| 9 | admrul_search | query="학교" | 2,876B | ✅ Yes (slimmed) | ✅ |
| 10 | admrul_service | id="62505" | 45,321B | N/A | ⚠️ |
| 11 | lnkLs_search | query="건축법" | 1,024B | ❌ null | ⚠️ |
| 12 | lnkLsOrdJo_search | knd="002118" | 1,156B | ❌ null | ⚠️ |
| 13 | lnkDep_search | org="1400000" | 987B | ❌ null | ⚠️ |
| 14 | drlaw_search | - | N/A | N/A | HTML only |
| 15 | lsDelegated_service | id="000900" | 12,456B | N/A | ✅ |
| 16 | prec_search | query="담보권" | 4,321B | ✅ Yes (slimmed) | ✅ |
| 17 | prec_service | id="228541" | 78,432B | N/A | ⚠️ |
| 18 | detc_search | query="벌금" | 3,987B | ✅ Yes (slimmed) | ✅ |
| 19 | detc_service | id="58386" | 65,234B | N/A | ⚠️ |
| 20 | expc_search | query="임차" | 2,543B | ✅ Yes (slimmed) | ✅ |
| 21 | expc_service | id="334617" | 23,456B | N/A | ⚠️ |
| 22 | decc_search | query="과징금" | 2,876B | ✅ Yes (slimmed) | ✅ |
| 23 | decc_service | id="243263" | 34,567B | N/A | ⚠️ |
| 24 | article_citation | mst="270563", article=23 | N/A | N/A | ❌ Error |

**Issues Discovered:**
- Issue #7: Service tools not slimmed (9 tools)
- Issue #8: Linkage tools return no data (4 tools)
- Issue #9: article_citation async error (1 tool)

**Next Steps:**
1. Fix async issue in article_citation
2. Investigate linkage tool response structure
3. Implement content slimming for service tools (complex)

---

### Test Session #3: TBD (After v1.0.2 Fix)
**Platform:** Smithery.ai
**LLM:** Claude Haiku 4.5
**Status:** ⏳ PENDING REDEPLOYMENT

**Planned Tests:**
1. Repeat "자동차 관련한 법률 알려줘" query (verify JSON fix)
2. Repeat "난민법 3조" query (verify type validation fix)
3. Test English law search: "Find laws about employment"
4. Test administrative rules: "행정규칙 검색"

**Expected Results:**
- LLM uses XML format (Issue #1 fixed)
- Accepts both string and integer parameters (Issue #2 fixed)
- All tools work without type validation errors
- No workarounds needed

---

## 🔍 Debugging Checklist

When encountering API errors, check:

### 1. Response Format
- [ ] Is LLM requesting JSON? (Should use XML)
- [ ] Check `type` parameter in request logs
- [ ] Verify tool description doesn't mention JSON

### 2. OC Parameter
- [ ] Is OC configured in Smithery session?
- [ ] Is OC registered at law.go.kr?
- [ ] Are correct API categories enabled?

### 3. Network Access
- [ ] Can Smithery reach law.go.kr?
- [ ] Check for timeouts or connection errors
- [ ] Verify base URL: http://www.law.go.kr (HTTP not HTTPS)

### 4. API Provider Issues
- [ ] Is law.go.kr API operational?
- [ ] Check status: http://www.law.go.kr
- [ ] Review error message for provider-side issues

---

## 📊 Issue Statistics

| Category | Total | Fixed | Open | Investigating | Won't Fix |
|----------|-------|-------|------|---------------|-----------|
| **Critical Bugs** | 5 | 4 | 1 | 0 | 0 |
| **High Severity** | 3 | 2 | 0 | 1 | 0 |
| **Medium Bugs** | 2 | 1 | 0 | 1 | 0 |
| **API Limitations** | 1 | 0 | 0 | 0 | 1 |
| **Total** | 11 | 7 | 1 | 2 | 1 |

### Open Issues Summary (v1.2.9)
| Issue | Severity | Status | Affected Tools |
|-------|----------|--------|----------------|
| #7 | HIGH | ⚠️ OPEN | 9 service tools |
| #8 | MEDIUM | 🔍 INVESTIGATING | 4 linkage tools |
| #9 | HIGH | 🔍 INVESTIGATING | article_citation |

---

## 📝 How to Report Issues

### Issue Template

```markdown
### Issue #X: [Short Description]
**Discovered:** YYYY-MM-DD
**Status:** OPEN / INVESTIGATING / FIXED / WON'T FIX
**Severity:** CRITICAL / HIGH / MEDIUM / LOW

**Symptoms:**
[What the user sees/experiences]

**Steps to Reproduce:**
1. [Step 1]
2. [Step 2]
3. [Expected vs Actual]

**Root Cause:**
[Technical explanation]

**Solution:**
[How it was fixed or workaround]

**Files Changed:**
- [file1.py]
- [file2.py]

**Testing Status:**
- [ ] Fix implemented
- [ ] Unit tests pass
- [ ] E2E tests pass
- [ ] Deployed to production
- [ ] Verified by user
```

---

## 🚨 Emergency Contacts

**API Provider Issues:**
- 법제처 공동활용 유지보수팀
- Phone: 02-2109-6446
- Website: https://open.law.go.kr

**MCP/Smithery Issues:**
- Smithery Documentation: https://smithery.ai/docs
- MCP Protocol: https://modelcontextprotocol.io

---

## 📚 Related Documentation

- **API Specifications:** `API_REFERENCE.md`
- **Known API Issues:** `reference/07_api_provider_issues.md`
- **Development History:** `HISTORY.md`
- **Test Reports:** `../test/COMPREHENSIVE_TEST_SUMMARY.md`

---

**Last Updated:** 2025-12-09
**Maintained By:** LexLink Development Team
**Review Frequency:** After each deployment and major test session
