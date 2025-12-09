# LexLink API Implementation Roadmap

**Last Updated:** 2025-11-30
**Status:** ✅ PHASE 4 COMPLETE
**Achievement:** All 24 tools implemented and validated (100%)

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

## Phase 3: Case Law & Legal Research APIs ✅ COMPLETE

**Timeline:** Completed 2025-11-14
**Tools Implemented:** 8/8 (100%)
**Semantic Validation:** 8/8 (100%) ✅
**Version:** v1.1.0

### Overview

Phase 3 expanded LexLink from statutory law to comprehensive legal research by adding case law, constitutional decisions, legal interpretations, and administrative appeals.

**Tool Count:** 15 → 23 (+53% increase) ✅
**API Coverage:** 10% → 15% of law.go.kr APIs ✅

---

### Priority 1: Court Precedents (판례) - 2 Tools ✅

| Tool Name | Korean Name | Status | API Endpoint |
|-----------|-------------|--------|--------------|
| `prec_search` | 판례 목록 조회 | ✅ LIVE | `/DRF/lawSearch.do?target=prec` |
| `prec_service` | 판례 본문 조회 | ✅ LIVE | `/DRF/lawService.do?target=prec` |

**Implementation Status:** ✅ COMPLETE

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

### Priority 2: Constitutional Court Decisions (헌재결정례) - 2 Tools ✅

| Tool Name | Korean Name | Status | API Endpoint |
|-----------|-------------|--------|--------------|
| `detc_search` | 헌재결정례 목록 조회 | ✅ LIVE | `/DRF/lawSearch.do?target=detc` |
| `detc_service` | 헌재결정례 본문 조회 | ✅ LIVE | `/DRF/lawService.do?target=detc` |

**Implementation Status:** ✅ COMPLETE

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

### Priority 3: Legal Interpretations (법령해석례) - 2 Tools ✅

| Tool Name | Korean Name | Status | API Endpoint |
|-----------|-------------|--------|--------------|
| `expc_search` | 법령해석례 목록 조회 | ✅ LIVE | `/DRF/lawSearch.do?target=expc` |
| `expc_service` | 법령해석례 본문 조회 | ✅ LIVE | `/DRF/lawService.do?target=expc` |

**Implementation Status:** ✅ COMPLETE

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

### Priority 4: Administrative Appeals (행정심판례) - 2 Tools ✅

| Tool Name | Korean Name | Status | API Endpoint |
|-----------|-------------|--------|--------------|
| `decc_search` | 행정심판례 목록 조회 | ✅ LIVE | `/DRF/lawSearch.do?target=decc` |
| `decc_service` | 행정심판례 본문 조회 | ✅ LIVE | `/DRF/lawService.do?target=decc` |

**Implementation Status:** ✅ COMPLETE

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

## Phase 3 Implementation Summary ✅

All Phase 3 tools implemented on 2025-11-14.

**Completed Tasks:**
- ✅ Added 8 new tools to server.py
- ✅ All 23 tools passing E2E tests
- ✅ Semantic validation: 23/23 tools (100%)
- ✅ LLM integration tests passing
- ✅ Documentation updated
- ✅ No regressions

**Version Released:** v1.1.0

---

## Phase 4: Article Citation API ✅ COMPLETE

**Timeline:** Completed 2025-11-30
**Tools Implemented:** 1/1 (100%)
**Semantic Validation:** 100% ✅
**Version:** v1.2.0

### Overview

Phase 4 introduced the `article_citation` tool that extracts legal citations from law articles. This enables LLMs to understand citation networks and follow legal references automatically.

**Key Innovation:** Uses HTML-based extraction from law.go.kr (not LLM), achieving 100% accuracy at zero API cost.

**Tool Count:** 23 → 24 (+1 tool) ✅
**MCP Prompts:** 3 → 5 (+2 prompts) ✅

---

### `article_citation` - 조문 인용 조회

| Aspect | Details |
|--------|---------|
| **Endpoint** | HTML parsing from `law.go.kr/LSW/lsSideInfoP.do` |
| **Purpose** | Extract citations referenced by a specific article |
| **Input** | MST (법령일련번호), article number, optional branch |
| **Output** | Structured list of citations (law name, article, paragraph, item) |

**Parameters:**
```python
article_citation(
    mst: str,              # Law MST code (required)
    article: int,          # Article number, e.g., 3 for 제3조
    article_branch: int,   # Branch number, e.g., 2 for 제37조의2 (default: 0)
    oc: Optional[str],     # User identifier
)
```

**Response Schema:**
```json
{
    "success": true,
    "law_id": "268611",
    "law_name": "자본시장과 금융투자업에 관한 법률",
    "article": "제3조",
    "citation_count": 12,
    "citations": [
        {
            "type": "external",
            "target_law_name": "신탁법",
            "target_article": 78,
            "target_paragraph": 1,
            "raw_text": "「신탁법」 제78조제1항"
        }
    ],
    "internal_count": 4,
    "external_count": 8
}
```

---

### Technical Approach

**Why HTML parsing instead of LLM?**

| Aspect | LLM (GPT-4) | HTML Parsing |
|--------|-------------|--------------|
| **Cost** | ~$0.05-0.10/article | **Free** |
| **Accuracy** | 95-98% | **100%** |
| **Speed** | 5-6 sec/article | **<100ms/article** |
| **Maintenance** | Prompt tuning | Stable HTML structure |

The law.go.kr website already provides **pre-linked citations** in article HTML:
```html
<a class="link sfon1" onclick="fncLsLawPop('123','ALLJO','')">「형법」</a>
<a class="link sfon2" onclick="fncLsLawPop('456','JO','')">제20조</a>
<a class="link sfon3" onclick="fncLsLawPop('789','JO','')">제1항</a>
```

CSS class mapping:
- `sfon1` → Law name (「법명」)
- `sfon2` → Article (제N조)
- `sfon3` → Paragraph (제N항)
- `sfon4` → Item (제N호)

---

### Implementation Plan

| Week | Tasks | Deliverables |
|------|-------|--------------|
| Week 1 | Core implementation | ID mapper, HTML fetcher, basic parser |
| Week 2 | Consolidation logic | Handle multi-part citations, edge cases |
| Week 3 | Integration & testing | E2E tests, documentation, release |

**See detailed documentation:**
- [ARTICLE_CITATION_DESIGN.md](./ARTICLE_CITATION_DESIGN.md) - Technical design
- [ARTICLE_CITATION_EVALUATION.md](./ARTICLE_CITATION_EVALUATION.md) - Testing guide

---

### Success Criteria ✅

- [x] Tool returns accurate citations for any valid law article
- [x] 100% accuracy against ground truth dataset
- [x] P95 latency < 500ms (~350ms average)
- [x] Error handling for invalid inputs
- [x] Integration with existing 23 tools

### Test Results

| Test Suite | Result |
|------------|--------|
| Citation Unit Tests | 25/25 (100%) ✅ |
| Citation Integration Tests | 15/15 (100%) ✅ |
| LLM Workflow Tests | 3/3 (100%) ✅ |

### New MCP Prompts

1. **`get-article-with-citations`** - Article + all citations in one workflow
2. **`analyze-law-citations`** - Multi-article citation network analysis

---

## Future Expansion Beyond Phase 4

**Additional APIs Available (60+ tools):**
- 자치법규 (Local Ordinances) - 2 tools
- 조약 (Treaties) - 2 tools
- 위원회 결정문 (Committee Decisions) - 24 tools (12 committees)
- 모바일 APIs - 14 tools
- 맞춤형 APIs - 6 tools
- 법령정보 지식베이스 - 6 tools
- 중앙부처 1차 해석 - 15 tools
- 특별행정심판 - 4 tools

**Total Future Potential:** 60+ additional tools beyond Phase 4

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

**Last Updated:** 2025-11-30
**Status:** ✅ All 24 tools implemented (v1.2.0)
**Next Step:** Future expansion - select from 126+ remaining APIs
