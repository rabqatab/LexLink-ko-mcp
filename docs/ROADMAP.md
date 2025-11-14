# LexLink API Implementation Roadmap

**Last Updated:** 2025-11-07
**Status:** ✅ PHASE 2 COMPLETE
**Achievement:** All 15 core tools implemented and validated (100%)

---

## Phase 1: Core Law APIs ✅ COMPLETE

**Timeline:** Completed 2025-11-07
**Tools Implemented:** 6/6 (100%)
**Semantic Validation:** 6/6 (100%) ✅

| Tool Name | Korean Name | Status | Validation |
|-----------|-------------|--------|------------|
| `eflaw_search` | 현행법령(시행일) 목록 조회 | ✅ LIVE | ✅ 100% |
| `eflaw_service` | 현행법령(시행일) 본문 조회 | ✅ LIVE | ✅ 100% |
| `law_search` | 현행법령(공포일) 목록 조회 | ✅ LIVE | ✅ 100% |
| `law_service` | 현행법령(공포일) 본문 조회 | ✅ LIVE | ✅ 100% |
| `eflaw_josub` | 현행법령(시행일) 조항호목 조회 | ✅ LIVE | ✅ 100% |
| `law_josub` | 현행법령(공포일) 조항호목 조회 | ✅ LIVE | ✅ 100% |

---

## Phase 2: Extended APIs ✅ COMPLETE

**Timeline:** Completed 2025-11-07
**Tools Implemented:** 9/9 (100%)
**Semantic Validation:** 9/9 (100%) ✅
**Time Taken:** ~18 minutes

### Priority 1: English Laws (영문법령) - 2 Tools ✅

| Tool Name | Korean Name | Status | Validation |
|-----------|-------------|--------|------------|
| `elaw_search` | 영문법령 목록 조회 | ✅ LIVE | ✅ 100% |
| `elaw_service` | 영문법령 본문 조회 | ✅ LIVE | ✅ 100% |

#### 1. `elaw_search` - 영문법령 목록 조회 ✅
**Endpoint:** `/DRF/lawSearch.do?target=elaw`
**Purpose:** Search English-translated Korean laws
**Status:** ✅ IMPLEMENTED & VALIDATED
**Implementation Pattern:** Same as eflaw_search

**Key Parameters:**
- `query` (string): Search keyword (Korean or English)
- `display` (int): Results per page (max 100)
- `page` (int): Page number
- `oc` (string): User identifier
- `type` (string): Response format (HTML/XML/JSON)
- `sort` (string): Sort order

**Implementation Notes:**
- Similar to eflaw_search but target=elaw
- Bilingual search support (Korean + English)
- Same validation rules

---

#### 2. `elaw_service` - 영문법령 본문 조회
**Endpoint:** `/DRF/lawService.do?target=elaw`
**Purpose:** Retrieve English law full text
**Priority:** High
**Implementation Pattern:** Same as eflaw_service

**Key Parameters:**
- `id` (string): Law ID (required if mst not provided)
- `mst` (string): Law master number (required if id not provided)
- `lm` (string): Law name
- `ld` (int): Announcement date
- `ln` (int): Announcement number
- `oc` (string): User identifier
- `type` (string): Response format

**Implementation Notes:**
- ID or MST required (mutually exclusive)
- Same structure as law_service
- English content field names

---

### Priority 2: Administrative Rules (행정규칙) - 2 Tools

#### 3. `admrul_search` - 행정규칙 목록 조회
**Endpoint:** `/DRF/lawSearch.do?target=admrul`
**Purpose:** Search administrative rules (훈령, 예규, 고시, etc.)
**Priority:** High
**Implementation Pattern:** Same as eflaw_search

**Key Parameters:**
- `query` (string): Search keyword
- `nw` (int): 1=현행, 2=연혁 (default 1)
- `search` (int): 1=규칙명, 2=본문검색
- `display` (int): Results per page
- `page` (int): Page number
- `org` (string): Ministry code
- `knd` (string): Rule type (1=훈령, 2=예규, 3=고시, 4=공고, 5=지침, 6=기타)
- `date` (int): Promulgation date (YYYYMMDD)
- `oc` (string): User identifier
- `type` (string): Response format

**Implementation Notes:**
- Different field names (rule_seq_no, promulgation_date, etc.)
- Rule type filtering (knd parameter)
- Ministry filtering important

---

#### 4. `admrul_service` - 행정규칙 본문 조회
**Endpoint:** `/DRF/lawService.do?target=admrul`
**Purpose:** Retrieve administrative rule full text
**Priority:** High
**Implementation Pattern:** Same as eflaw_service

**Key Parameters:**
- `id` (string): Rule sequence number (required)
- `lid` (string): Rule ID (alternative)
- `lm` (string): Rule name
- `oc` (string): User identifier
- `type` (string): Response format

**Implementation Notes:**
- ID required (no MST alternative)
- Different response structure (article_content, addendum, annex)
- Includes attachments (annex_form_file_link, annex_form_pdf_link)

---

### Priority 3: Law-Ordinance Linkage (법령-자치법규 연계) - 4 Tools

#### 5. `lnkLs_search` - 법령-자치법규 연계 목록 조회
**Endpoint:** `/DRF/lawSearch.do?target=lnkLs`
**Purpose:** Search laws linked to local ordinances
**Priority:** Medium
**Implementation Pattern:** Same as eflaw_search

**Key Parameters:**
- `query` (string): Search keyword
- `display` (int): Results per page
- `page` (int): Page number
- `sort` (string): Sort order
- `oc` (string): User identifier
- `type` (string): Response format

**Implementation Notes:**
- Simpler parameter set than law searches
- Returns basic law info
- Used to find laws with ordinance linkages

---

#### 6. `lnkLsOrdJo_search` - 연계 법령별 조례 조문 목록 조회
**Endpoint:** `/DRF/lawSearch.do?target=lnkLsOrdJo`
**Purpose:** Search ordinance articles linked to specific law articles
**Priority:** Medium
**Implementation Pattern:** Same as eflaw_search

**Key Parameters:**
- `query` (string): Search keyword
- `knd` (string): Law type code (required)
- `jo` (int): Article number (4 digits, e.g., 0020)
- `jobr` (int): Article branch number (2 digits, e.g., 02)
- `display` (int): Results per page
- `page` (int): Page number
- `oc` (string): User identifier
- `type` (string): Response format

**Implementation Notes:**
- Article number format: 4 digits (jo) + 2 digits (jobr)
- Returns ordinance details linked to law article
- Complex response structure with nested ordinance data

---

#### 7. `lnkDep_search` - 연계 법령 소관부처별 목록 조회
**Endpoint:** `/DRF/lawSearch.do?target=lnkDep`
**Purpose:** Search law-ordinance links by ministry
**Priority:** Low
**Implementation Pattern:** Same as eflaw_search

**Key Parameters:**
- `org` (string): Ministry code (required)
- `display` (int): Results per page
- `page` (int): Page number
- `sort` (string): Sort order
- `oc` (string): User identifier
- `type` (string): Response format

**Implementation Notes:**
- Ministry code required (org parameter)
- Returns ordinances linked to ministry's laws
- Similar response structure to lnkLsOrdJo

---

#### 8. `drlaw_search` - 법령-자치법규 연계현황 조회
**Endpoint:** `/DRF/lawSearch.do?target=drlaw`
**Purpose:** Retrieve law-ordinance linkage statistics
**Priority:** Low
**Implementation Pattern:** Simple HTML-only endpoint

**Key Parameters:**
- `oc` (string): User identifier (required)
- `type` (string): Must be "HTML" (only supported format)

**Implementation Notes:**
- ⚠️ HTML output only (no XML/JSON)
- ⚠️ No response schema documented by API provider
- Statistical/dashboard view
- May return HTML table or visualization

---

### Priority 4: Delegated Laws (위임법령) - 1 Tool

#### 9. `lsDelegated_service` - 위임 법령 조회
**Endpoint:** `/DRF/lawService.do?target=lsDelegated`
**Purpose:** Retrieve laws/rules/ordinances delegated by a parent law
**Priority:** Medium
**Implementation Pattern:** Service endpoint (no search equivalent)

**Key Parameters:**
- `id` (string): Law ID (required if mst not provided)
- `mst` (string): Law master number (required if id not provided)
- `oc` (string): User identifier
- `type` (string): Response format (XML/JSON, no HTML)

**Implementation Notes:**
- ⚠️ HTML not supported (only XML/JSON)
- Complex response structure (delegated_law_*, delegated_rule_*, delegated_ordinance_*)
- Shows delegation hierarchy
- Returns multiple delegation types (법령/행정규칙/자치법규)

---

## Implementation Strategy

### Step 1: English Laws (Easy - Similar to Existing)
- Implement `elaw_search` and `elaw_service`
- Test with bilingual queries
- **Estimated Time:** 30 minutes

### Step 2: Administrative Rules (Moderate - New Response Schema)
- Implement `admrul_search` and `admrul_service`
- Handle different field names (promulgation_date, rule_seq_no, etc.)
- Test with different rule types (knd parameter)
- **Estimated Time:** 45 minutes

### Step 3: Law-Ordinance Linkage (Complex - New Domain)
- Implement `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`
- Handle nested ordinance data structures
- Test article number format validation (jo/jobr)
- **Estimated Time:** 1 hour

### Step 4: Special Cases (Tricky - Limited Documentation)
- Implement `drlaw_search` (HTML-only, no schema)
- Implement `lsDelegated_service` (complex response, no HTML)
- **Estimated Time:** 45 minutes

### Step 5: Integration & Testing
- Run E2E tests for all 15 tools
- Update documentation
- Verify all tools work with Context injection
- **Estimated Time:** 30 minutes

---

## Testing Checklist

For each new tool, verify:

- ✅ Context parameter injection works
- ✅ OC resolution (tool arg > session > env)
- ✅ Parameter mapping to upstream API
- ✅ Error handling (timeout, validation, upstream errors)
- ✅ Response passthrough (XML/HTML/JSON)
- ✅ Proper docstring with examples
- ✅ Type hints correct
- ✅ Tool registered in FastMCP server

---

## Success Criteria

**Phase 2 Complete When:**
1. All 9 tools implemented in server.py
2. All 15 tools passing E2E tests
3. API_REFERENCE.md updated with all 15 tools
4. STATUS.md updated with Phase 2 details
5. No code regressions (existing 6 tools still work)

---

## Phase 3: Case Law & Legal Research APIs 📋 PLANNED

**Timeline:** TBD
**Tools Planned:** 8/8 (100%)
**Categories:** 4 major legal research areas

### Overview

Phase 3 expands LexLink from statutory law to comprehensive legal research by adding case law, constitutional decisions, legal interpretations, and administrative appeals.

**Tool Count:** 15 → 23 (+53% increase)
**API Coverage:** 10% → 15% of law.go.kr APIs

---

### Priority 1: Court Precedents (판례) - 2 Tools

| Tool Name | Korean Name | Status | API Endpoint |
|-----------|-------------|--------|--------------|
| `prec_search` | 판례 목록 조회 | 📋 PLANNED | `/DRF/lawSearch.do?target=prec` |
| `prec_service` | 판례 본문 조회 | 📋 PLANNED | `/DRF/lawService.do?target=prec` |

**Implementation Priority:** ⭐ HIGH (Most requested by legal professionals)

#### 1. `prec_search` - 판례 목록 조회
**Endpoint:** `/DRF/lawSearch.do?target=prec`
**Purpose:** Search Korean court precedents (Supreme Court + lower courts)

**Key Parameters:**
- `query` (string): Search keyword
- `search` (int): 1=case name (default), 2=full text search
- `display` (int): Results per page (max 100)
- `org` (string): Court type code (400201=Supreme, 400202=Lower courts)
- `curt` (string): Specific court name (대법원, 서울고등법원, etc.)
- `jo` (string): Referenced law name (형법, 민법, etc.)
- `date` (int): Decision date (YYYYMMDD)
- `prnc_yd` (string): Decision date range (YYYYMMDD~YYYYMMDD)
- `nb` (string): Case number (comma-separated)
- `dat_src_nm` (string): Data source (대법원, 국세법령정보시스템, etc.)

**Response Fields:**
- `사건명` (case name), `사건번호` (case number)
- `선고일자` (decision date), `법원명` (court name)
- `판결유형` (judgment type), `선고` (decision)

#### 2. `prec_service` - 판례 본문 조회
**Endpoint:** `/DRF/lawService.do?target=prec`
**Purpose:** Retrieve full precedent text with issues, summary, and holdings

**Key Parameters:**
- `id` (string): Precedent serial number (required)
- `lm` (string): Precedent name (optional)

**Response Fields:**
- `판시사항` (issues), `판결요지` (summary)
- `참조조문` (referenced articles), `참조판례` (referenced precedents)
- `판례내용` (full precedent text)

---

### Priority 2: Constitutional Court Decisions (헌재결정례) - 2 Tools

| Tool Name | Korean Name | Status | API Endpoint |
|-----------|-------------|--------|--------------|
| `detc_search` | 헌재결정례 목록 조회 | 📋 PLANNED | `/DRF/lawSearch.do?target=detc` |
| `detc_service` | 헌재결정례 본문 조회 | 📋 PLANNED | `/DRF/lawService.do?target=detc` |

**Implementation Priority:** ⭐ HIGH (Constitutional review is critical)

#### 3. `detc_search` - 헌재결정례 목록 조회
**Endpoint:** `/DRF/lawSearch.do?target=detc`
**Purpose:** Search Constitutional Court decisions

**Key Parameters:**
- `query` (string): Search keyword
- `search` (int): 1=decision name (default), 2=full text
- `date` (int): Final date (YYYYMMDD)
- `ed_yd` (string): Final date range (YYYYMMDD~YYYYMMDD)
- `nb` (int): Case number

**Response Fields:**
- `사건명` (case name), `사건번호` (case number)
- `종국일자` (final date)

#### 4. `detc_service` - 헌재결정례 본문 조회
**Endpoint:** `/DRF/lawService.do?target=detc`
**Purpose:** Retrieve full Constitutional Court decision text

**Key Parameters:**
- `id` (string): Decision serial number (required)
- `lm` (string): Decision name (optional)

**Response Fields:**
- `판시사항` (issues), `결정요지` (decision summary)
- `전문` (full text), `참조조문` (referenced articles)
- `심판대상조문` (articles under review)
- `재판부구분코드` (bench type: 430201=full, 430202=designated)

---

### Priority 3: Legal Interpretations (법령해석례) - 2 Tools

| Tool Name | Korean Name | Status | API Endpoint |
|-----------|-------------|--------|--------------|
| `expc_search` | 법령해석례 목록 조회 | 📋 PLANNED | `/DRF/lawSearch.do?target=expc` |
| `expc_service` | 법령해석례 본문 조회 | 📋 PLANNED | `/DRF/lawService.do?target=expc` |

**Implementation Priority:** ⭐ MEDIUM (Official legal guidance)

#### 5. `expc_search` - 법령해석례 목록 조회
**Endpoint:** `/DRF/lawSearch.do?target=expc`
**Purpose:** Search official legal interpretations by Ministry of Government Legislation

**Key Parameters:**
- `query` (string): Search keyword
- `search` (int): 1=item name (default), 2=full text
- `inq` (string): Inquiry organization
- `rpl` (int): Reply organization
- `itmno` (int): Item number (안건번호, e.g., 13-0217 → 130217)
- `reg_yd` (string): Registration date range (YYYYMMDD~YYYYMMDD)
- `expl_yd` (string): Interpretation date range (YYYYMMDD~YYYYMMDD)

**Response Fields:**
- `안건명` (item name), `안건번호` (item number)
- `질의기관명` (inquiry org), `회신기관명` (reply org)
- `회신일자` (reply date)

#### 6. `expc_service` - 법령해석례 본문 조회
**Endpoint:** `/DRF/lawService.do?target=expc`
**Purpose:** Retrieve full legal interpretation text

**Key Parameters:**
- `id` (int): Interpretation serial number (required)
- `lm` (string): Interpretation name (optional)

**Response Fields:**
- `질의요지` (question summary), `회답` (answer)
- `이유` (reason/rationale)
- `해석일자` (interpretation date)

---

### Priority 4: Administrative Appeals (행정심판례) - 2 Tools

| Tool Name | Korean Name | Status | API Endpoint |
|-----------|-------------|--------|--------------|
| `decc_search` | 행정심판례 목록 조회 | 📋 PLANNED | `/DRF/lawSearch.do?target=decc` |
| `decc_service` | 행정심판례 본문 조회 | 📋 PLANNED | `/DRF/lawService.do?target=decc` |

**Implementation Priority:** ⭐ MEDIUM (Administrative law practitioners)

#### 7. `decc_search` - 행정심판례 목록 조회
**Endpoint:** `/DRF/lawSearch.do?target=decc`
**Purpose:** Search administrative appeal decisions

**Key Parameters:**
- `query` (string): Search keyword
- `search` (int): 1=case name (default), 2=full text
- `cls` (string): Decision type (재결구분코드)
- `date` (int): Resolution date (YYYYMMDD)
- `dpa_yd` (string): Disposition date range (YYYYMMDD~YYYYMMDD)
- `rsl_yd` (string): Resolution date range (YYYYMMDD~YYYYMMDD)

**Response Fields:**
- `사건명` (case name), `사건번호` (case number)
- `처분일자` (disposition date), `의결일자` (resolution date)
- `처분청` (disposition agency), `재결청` (decision agency)
- `재결구분명` (decision type name)

#### 8. `decc_service` - 행정심판례 본문 조회
**Endpoint:** `/DRF/lawService.do?target=decc`
**Purpose:** Retrieve full administrative appeal decision

**Key Parameters:**
- `id` (string): Decision serial number (required)
- `lm` (string): Decision name (optional)

**Response Fields:**
- `주문` (order), `청구취지` (claim summary)
- `이유` (reason), `재결요지` (decision summary)

---

## Phase 3 Implementation Strategy

### Step 1: Precedent Tools (Most Common Use Case)
**Timeline:** Week 1
**Tools:** `prec_search`, `prec_service`
- Add new parameters to params.py: `curt`, `nb`, `prnc_yd`, `dat_src_nm`
- Implement ranking for case name (사건명)
- Write comprehensive tests
- **Estimated Time:** 2-3 hours

### Step 2: Constitutional Court Tools
**Timeline:** Week 2
**Tools:** `detc_search`, `detc_service`
- Add new parameter: `ed_yd` (종국일자 기간)
- Handle constitutional court-specific response schema
- **Estimated Time:** 2 hours

### Step 3: Legal Interpretation Tools
**Timeline:** Week 3
**Tools:** `expc_search`, `expc_service`
- Add new parameters: `inq`, `rpl`, `itmno`, `reg_yd`, `expl_yd`
- Handle interpretation-specific fields (안건명, 질의요지, etc.)
- **Estimated Time:** 2 hours

### Step 4: Administrative Appeals Tools
**Timeline:** Week 4
**Tools:** `decc_search`, `decc_service`
- Add new parameters: `cls`, `dpa_yd`, `rsl_yd`
- Handle administrative appeal response schema
- **Estimated Time:** 2 hours

### Step 5: Integration & Documentation
**Timeline:** Week 4
- Update README.md (15 → 23 tools)
- Update API coverage analysis (10% → 15%)
- Comprehensive E2E testing
- Deploy v1.1.0
- **Estimated Time:** 2-3 hours

**Total Estimated Time:** 10-12 hours over 4 weeks

---

## Phase 3 Success Criteria

**Phase 3 Complete When:**
1. ✅ All 8 new tools implemented in server.py
2. ✅ All 23 tools passing E2E tests
3. ✅ Semantic validation: 23/23 tools returning real data
4. ✅ LLM integration tests passing for new tools
5. ✅ Documentation updated (README, DEVELOPMENT_HISTORY)
6. ✅ No regressions (existing 15 tools still work)

---

## Future Expansion Beyond Phase 3

**Additional APIs Available (60+ tools):**
- 자치법규 (Local Ordinances) - 2 tools
- 조약 (Treaties) - 2 tools
- 위원회 결정문 (Committee Decisions) - 24 tools (12 committees)
- 모바일 APIs - 14 tools
- 맞춤형 APIs - 6 tools
- 법령정보 지식베이스 - 6 tools
- 중앙부처 1차 해석 - 15 tools
- 특별행정심판 - 4 tools

**Total Future Potential:** 60+ additional tools beyond Phase 3

---

## Notes for Implementation

### Common Patterns Identified

**Search Tools (8 of 9 are search endpoints):**
```python
@server.tool()
def <tool_name>(
    query: str,
    display: int = 20,
    page: int = 1,
    oc: Optional[str] = None,
    type: str = "XML",
    # ... specific parameters
    ctx: Context = None,
) -> dict:
    config = ctx.session_config if ctx else None
    session_oc = config.oc if config else None
    resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

    params = {
        "query": query,
        "display": display,
        "page": page,
        # ... specific params
    }

    upstream_params = map_params_to_upstream(params)
    client = _get_client()
    return client.get("/DRF/lawSearch.do", upstream_params, response_type=type)
```

**Service Tools (1 of 9 is service endpoint):**
```python
@server.tool()
def <tool_name>(
    id: Optional[str] = None,
    mst: Optional[str] = None,
    oc: Optional[str] = None,
    type: str = "XML",
    # ... specific parameters
    ctx: Context = None,
) -> dict:
    if not id and not mst:
        return create_error_response(...)

    # ... similar pattern to search tools
```

### Parameter Mapping Updates Needed

The following new parameters need to be added to `params.py`:

```python
PARAM_MAP = {
    # ... existing mappings

    # English laws (elaw)
    "lm": "LM",        # Law name
    "ld": "LD",        # Announcement date
    "ln": "LN",        # Announcement number

    # Administrative rules (admrul)
    "nw": "nw",        # Current/history flag
    "prml_yd": "prmlYd",  # Promulgation date range
    "mod_yd": "modYd",    # Modification date range

    # Linkage (lnk*)
    "jobr": "JOBR",    # Article branch number

    # Delegated laws (lsDelegated)
    # No new params needed
}
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| API provider schema inconsistency | Medium | Low | Use passthrough responses, let client parse |
| HTML-only endpoints (drlaw) | Certain | Low | Document limitation, pass through HTML |
| No JSON support (documented but broken) | Known | Low | Already documented in API_REFERENCE.md |
| Complex nested responses (lsDelegated) | Certain | Medium | Pass through as-is, document structure |
| Article number validation (jo/jobr) | Low | Low | Use simple format validation |

---

**Last Updated:** 2025-11-07
**Status:** Ready to implement
**Next Step:** Implement elaw_search and elaw_service (Priority 1)
