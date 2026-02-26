# law.go.kr API Provider Issues

**Document Type:** Known Issues with Upstream API Provider
**Created:** 2025-11-07
**Status:** Active

---

## Issue #1: JSON Format Not Supported (Critical)

### **Summary**
The law.go.kr Open API documentation claims to support `type=JSON`, but all 6 APIs return HTML error pages instead of JSON data.

### **Status:** ❌ **BROKEN** (Upstream API Issue)

### **Affected Endpoints:**
- ✅ All 6 law.go.kr APIs affected:
  1. `lawSearch.do?target=eflaw` (현행법령 시행일 목록)
  2. `lawService.do?target=eflaw` (현행법령 시행일 본문)
  3. `lawSearch.do?target=law` (현행법령 공포일 목록)
  4. `lawService.do?target=law` (현행법령 공포일 본문)
  5. `lawService.do?target=eflawjosub` (시행일 조항)
  6. `lawService.do?target=lawjosub` (공포일 조항)

### **Evidence:**
```bash
# Test 1: lawSearch (eflaw) with JSON
$ curl "http://www.law.go.kr/DRF/lawSearch.do?OC=your_oc&target=eflaw&type=JSON"
<!DOCTYPE html...  # ❌ Returns HTML error page

# Test 2: lawService (eflaw) with JSON
$ curl "http://www.law.go.kr/DRF/lawService.do?OC=your_oc&target=eflaw&ID=1747&type=JSON"
<!DOCTYPE html...  # ❌ Returns HTML error page

# Test 3: lawSearch (law) with JSON
$ curl "http://www.law.go.kr/DRF/lawSearch.do?OC=your_oc&target=law&type=JSON"
<!DOCTYPE html...  # ❌ Returns HTML error page

# Test 4: lawService (law) with JSON
$ curl "http://www.law.go.kr/DRF/lawService.do?OC=your_oc&target=law&ID=009682&type=JSON"
<!DOCTYPE html...  # ❌ Returns HTML error page
```

**All APIs return the same HTML error page structure instead of JSON data.**

### **Workaround:** ✅ Use XML Format

XML format works perfectly across all endpoints:

```bash
# Test 1: lawSearch (eflaw) with XML - WORKS!
$ curl "http://www.law.go.kr/DRF/lawSearch.do?OC=your_oc&target=eflaw&type=XML"
<?xml version="1.0" encoding="UTF-8"?><LawSearch>
<resultCode>00</resultCode><resultMsg>success</resultMsg>
<totalCnt>163532</totalCnt>...  # ✅ Valid XML

# Test 2: lawService (eflaw) with XML - WORKS!
$ curl "http://www.law.go.kr/DRF/lawService.do?OC=your_oc&target=eflaw&ID=1747&type=XML"
<?xml version="1.0" encoding="utf-8"?><법령 법령키="0017472025100121065">
<기본정보><법령ID>001747</법령ID>...  # ✅ Valid XML

# Test 3: lawSearch (law) with XML - WORKS!
$ curl "http://www.law.go.kr/DRF/lawSearch.do?OC=your_oc&target=law&type=XML"
<?xml version="1.0" encoding="UTF-8"?><LawSearch>
<resultCode>00</resultCode>...  # ✅ Valid XML

# Test 4: lawService (law) with XML - WORKS!
$ curl "http://www.law.go.kr/DRF/lawService.do?OC=your_oc&target=law&ID=009682&type=XML"
<?xml version="1.0" encoding="UTF-8"?><법령>...  # ✅ Valid XML
```

### **Impact on Our Implementation:**

#### **Default Format Change:**
- **Before:** Tools default to `type="XML"` (correct!)
- **Keep:** Continue using XML as default
- **Document:** Note that JSON is not supported despite API documentation

#### **Tool Parameter:**
- **Current:** `type` parameter accepts "HTML", "XML", "JSON"
- **Reality:** Only "HTML" and "XML" actually work
- **Recommendation:** Keep parameter as-is for API compatibility, but document limitation

#### **Error Handling:**
- ✅ **Current behavior is correct:** Our client properly catches the JSON parse error
- ✅ **Error message is accurate:** "Failed to parse JSON response"
- 📝 **Enhancement:** Could add hint: "Note: law.go.kr API doesn't support JSON format. Use XML instead."

### **Implementation Status:**

| Component | Status | Action Required |
|-----------|--------|-----------------|
| Default format | ✅ XML (correct) | None - already correct |
| Tool parameter | ✅ Allows all formats | None - maintain API compatibility |
| Error handling | ✅ Works correctly | Optional: Add hint about XML |
| Documentation | ⚠️ Needs update | Update README and tool descriptions |
| Tests | ⚠️ Using JSON | Change E2E tests to use XML |

### **Documentation Updates:**

#### **Update tool descriptions:**
```python
@server.tool()
def eflaw_search(..., type: str = "XML"):
    """
    Args:
        type: Response format - "HTML" or "XML" (default "XML")
              Note: "JSON" is documented but not supported by law.go.kr API
    """
```

#### **Update README.md:**
```markdown
## Response Formats

The law.go.kr API officially supports:
- ✅ **XML** (default, recommended) - Works on all endpoints
- ✅ **HTML** - Works but less structured
- ❌ **JSON** - Documented but not actually supported by the API

We recommend using XML format for all requests.
```

### **Recommended Actions:**

1. ✅ **No code changes needed** - Our implementation is correct
2. ⚠️ **Update tool descriptions** - Note JSON limitation
3. ⚠️ **Update README.md** - Document format support
4. ⚠️ **Update tests** - Change from JSON to XML
5. ℹ️ **Optional:** Add error hint suggesting XML when JSON fails

### **API Provider Contact:**

If this needs to be reported to law.go.kr:
- **Website:** http://www.law.go.kr
- **API Docs:** http://www.law.go.kr/DRF/lawApiGuide.do
- **Issue:** JSON format returns HTML error pages instead of JSON data
- **Tested:** 2025-11-07 with valid OC identifier "your_oc"
- **All endpoints affected:** lawSearch, lawService (both eflaw and law targets)

---

## Future Issues

Additional API provider issues will be documented here as discovered.

---

**Maintenance Notes:**
- Re-test JSON support periodically in case API provider fixes it
- Document any new API limitations discovered during implementation
- Track if HTML format has any similar issues
