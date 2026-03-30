# LexLink API Implementation Roadmap

**Last Updated:** 2026-03-30
**Status:** All 49 tools + 2 resources + 9 prompts implemented (v2.0.0)

---

## Phase 1: Core Law APIs - COMPLETE

**Completed:** 2025-11-07 | **Tools:** 6/6 | **Validation:** 100%

| Tool | Korean Name | Endpoint |
|------|-------------|----------|
| `eflaw_search` | 현행법령(시행일) 목록 조회 | `lawSearch.do?target=eflaw` |
| `eflaw_service` | 현행법령(시행일) 본문 조회 | `lawService.do?target=eflaw` |
| `law_search` | 현행법령(공포일) 목록 조회 | `lawSearch.do?target=law` |
| `law_service` | 현행법령(공포일) 본문 조회 | `lawService.do?target=law` |
| `eflaw_josub` | 현행법령(시행일) 조항호목 조회 | `lawService.do?target=eflaw` |
| `law_josub` | 현행법령(공포일) 조항호목 조회 | `lawService.do?target=law` |

---

## Phase 2: Extended APIs - COMPLETE

**Completed:** 2025-11-07 | **Tools:** 9/9 | **Validation:** 100%

| Tool | Korean Name | Endpoint |
|------|-------------|----------|
| `elaw_search` | 영문법령 목록 조회 | `lawSearch.do?target=elaw` |
| `elaw_service` | 영문법령 본문 조회 | `lawService.do?target=elaw` |
| `admrul_search` | 행정규칙 목록 조회 | `lawSearch.do?target=admrul` |
| `admrul_service` | 행정규칙 본문 조회 | `lawService.do?target=admrul` |
| `lnkLs_search` | 법령-자치법규 연계 목록 조회 | `lawSearch.do?target=lnkLs` |
| `lnkLsOrdJo_search` | 연계 법령별 조례 조문 목록 조회 | `lawSearch.do?target=lnkLsOrdJo` |
| `lnkDep_search` | 연계 법령 소관부처별 목록 조회 | `lawSearch.do?target=lnkDep` |
| `drlaw_search` | 법령-자치법규 연계현황 조회 | `lawSearch.do?target=drlaw` |
| `lsDelegated_service` | 위임 법령 조회 | `lawService.do?target=lsDelegated` |

For detailed parameter specs, see `API_REFERENCE.md`.

---

## Phase 3: Case Law & Legal Research - COMPLETE

**Completed:** 2025-11-14 | **Tools:** 8/8 | **Validation:** 100% | **Version:** v1.1.0

| Tool | Korean Name | Endpoint |
|------|-------------|----------|
| `prec_search` | 판례 목록 조회 | `lawSearch.do?target=prec` |
| `prec_service` | 판례 본문 조회 | `lawService.do?target=prec` |
| `detc_search` | 헌재결정례 목록 조회 | `lawSearch.do?target=detc` |
| `detc_service` | 헌재결정례 본문 조회 | `lawService.do?target=detc` |
| `expc_search` | 법령해석례 목록 조회 | `lawSearch.do?target=expc` |
| `expc_service` | 법령해석례 본문 조회 | `lawService.do?target=expc` |
| `decc_search` | 행정심판례 목록 조회 | `lawSearch.do?target=decc` |
| `decc_service` | 행정심판례 본문 조회 | `lawService.do?target=decc` |

---

## Phase 4: Article Citation Extraction - COMPLETE

**Completed:** 2025-11-30 | **Tools:** 1/1 | **Validation:** 100% | **Version:** v1.2.0

| Tool | Korean Name | Method |
|------|-------------|--------|
| `article_citation` | 조문 인용 조회 | HTML parsing from `law.go.kr/LSW/lsSideInfoP.do` |

**Key Innovation:** HTML-based extraction from law.go.kr (not LLM). 100% accuracy, zero API cost, ~350ms per article.

**MCP Prompts Added:** `get-article-with-citations`, `analyze-law-citations`

**Bug fixes:** See `ISSUES.md` appendix.

---

## Phase 5: AI-Powered Search - COMPLETE

**Completed:** 2025-12-09 | **Tools:** 2/2 | **Version:** v1.3.0

| Tool | Korean Name | Endpoint |
|------|-------------|----------|
| `aiSearch` | 지능형 법령검색 | `lawSearch.do?target=aiSearch` |
| `aiRltLs_search` | 연관법령 검색 | `lawSearch.do?target=aiRltLs` |

**Key Innovation:** Uses law.go.kr's built-in AI search API for semantic/vague queries, complementing keyword-based tools.

**MCP Prompt Added:** `tool-selection-guide`

**MCP Resources Added:** `frequently-used-laws` (static list of ~20 law→ID mappings), `law-code-lookup` (template lookup by name). Search tools dynamically cache results for future resource lookups.

---

## Phase 6: Code Refactoring - COMPLETE

**Completed:** 2026-03-30 | **Version:** v2.0.0

**Objective:** Reduce `server.py` from ~3,300 to ~1,100 lines (65% reduction) via shared helpers.

**Approach:** Created `src/lexlink/_helpers.py` (~211 lines) extracting repeated patterns:
- Shared `TOOL_ANNOTATIONS` constant
- `handle_tool_error` helper
- `run_search` and `run_service` helpers
- All 26 existing tools refactored as thin wrappers

Explicit `@server.tool()` decorators and `ctx: Context = None` signatures remain on each tool for MCP compatibility.

---

## Phase 7: Extended Legal Information - COMPLETE

**Completed:** 2026-03-30 | **Tools:** 18/18 | **Version:** v2.0.0

| Category | Tools | Description |
|----------|-------|-------------|
| 자치법규 (Local Ordinances) | `ordin_search`, `ordin_service`, `ordinLsCon_search` | Local ordinance search, retrieval & law linkage |
| 조약 (Treaties) | `trty_search`, `trty_service` | International treaty search & retrieval |
| 법령정보 지식베이스 (Knowledge Base) | `lstrm_ai_search`, `dlytrm_search`, `lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`, `ls_rlt_search` | Legal term AI search, everyday terms, cross-references & linkage |
| 위원회 결정문 (Committee Decisions) | `committee_search`, `committee_service` | Decisions from 12 government committees (parametric) |
| 중앙부처 1차 해석 (Ministry Interpretations) | `cgm_expc_search`, `cgm_expc_service` | First-instance interpretations from 39 ministries (parametric) |
| 특별행정심판 (Special Appeals) | `special_decc_search`, `special_decc_service` | Decisions from 4 special tribunals (parametric) |

---

## Phase 8: AI-Powered Legal Reasoning Tools - COMPLETE

**Completed:** 2026-03-30 | **Tools:** 5/5 | **Version:** v2.0.0

| Tool | Korean Name | Description |
|------|-------------|-------------|
| `check_precedent_odds` | 판례 승소 가능성 분석 | Analyzes precedent patterns to estimate case odds |
| `legal_resolver` | 법률 분쟁 해결 가이드 | Guides users through legal dispute resolution paths |
| `simplify_article` | 법령 조문 쉬운 설명 | Explains law articles in plain language using knowledge base |
| `law_amendment_summary` | 법령 개정 요약 | Summarizes law amendment history |
| `article_amendment_diff` | 조문 개정 비교 | Shows diff between article versions across amendments |

**MCP Prompts Added:** 3 prompts for legal reasoning guidance

**Note:** JSON is now the default response format as of v2.0.0 (was XML in previous versions).

---

## Future Expansion

**Additional APIs available (remaining):**
- 모바일 APIs - 14 tools (duplicate of existing, low priority)
- 맞춤형 APIs - 6 tools
- 별표·서식 (Tables & Forms) - 3 tools
- 학칙·공단·공공기관 - 2 tools

**Note:** Local ordinances, treaties, committee decisions, ministry interpretations, special appeals, and knowledge base tools are implemented in Phase 7. AI-powered legal reasoning tools are implemented in Phase 8.

See `API_REFERENCE.md` for the full 191-API catalog.
