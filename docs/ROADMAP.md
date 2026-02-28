# LexLink API Implementation Roadmap

**Last Updated:** 2026-02-28
**Status:** All 26 tools + 2 resources implemented (v1.5.0)

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

## Phase 6: Code Refactoring - PLANNED

**Objective:** Reduce `server.py` from ~3,300 to ~1,100 lines (65% reduction) via shared helpers.

**Approach:** Create `src/lexlink/_helpers.py` (~250 lines) extracting 6 repeated patterns:
- Shared `ToolAnnotations` constant (120 lines saved)
- OC resolution helper (72 lines saved)
- Error handling decorator (288 lines saved)
- ID stringification (48 lines saved)
- Common search logic (320 lines saved)
- Common service logic (300 lines saved)

Explicit `@server.tool()` decorators and `ctx: Context = None` signatures remain on each tool for MCP compatibility.

---

## Future Expansion

**Additional APIs available (165+ remaining):**
- 자치법규 (Local Ordinances) - 2 tools
- 조약 (Treaties) - 2 tools
- 위원회 결정문 (Committee Decisions) - 24 tools
- 모바일 APIs - 14 tools
- 맞춤형 APIs - 6 tools
- 법령정보 지식베이스 - 6 tools
- 중앙부처 1차 해석 - 15 tools
- 특별행정심판 - 4 tools

See `API_REFERENCE.md` for the full 191-API catalog.
