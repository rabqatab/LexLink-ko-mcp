# LexLink - Bugs and Issues Tracker

**Last Updated:** 2025-12-09
**Purpose:** Track bugs, errors, and issues found during testing and deployment
**Status:** Active tracking document

---

## 🐛 Active Issues

### Issue #4: PlayMCP Response Size Limit Error ✅ RESOLVED
**Discovered:** 2025-12-09
**Status:** ✅ **FIXED** in v1.2.4
**Severity:** HIGH - Blocks all search tool responses on PlayMCP
**Platform:** Kakao PlayMCP (not affecting Smithery.ai)

**Symptoms:**
```
Error: Tool call returned too large content part
```
All search tools (`eflaw_search`, `prec_search`, etc.) fail on PlayMCP while working fine on Smithery.ai.

**Root Cause:**
- PlayMCP has a strict response size limit (~50KB for tool responses)
- LexLink search responses contain data in two formats:
  - `raw_content`: Full XML response from law.go.kr API (~25KB for 50 results)
  - `ranked_data`: Parsed JSON with same data (~25KB for 50 results)
- Total response size: ~50KB, exceeding PlayMCP limit

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

| Category | Total | Fixed | Open | Won't Fix |
|----------|-------|-------|------|-----------|
| **Critical Bugs** | 2 | 2 | 0 | 0 |
| **Medium Bugs** | 2 | 2 | 0 | 0 |
| **API Limitations** | 1 | 0 | 0 | 1 |
| **Documentation** | 0 | 0 | 0 | 0 |
| **Total** | 5 | 4 | 0 | 1 |

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
