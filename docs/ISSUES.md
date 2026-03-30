# LexLink - Bugs and Issues Tracker

**Last Updated:** 2026-03-30

---

## Open Issues

### Issue #7: Service Tools Exceed PlayMCP 24KB Limit

**Status:** OPEN | **Severity:** HIGH | **Discovered:** 2025-12-09

Law full-text tools (`eflaw_service`, `law_service`) always exceed PlayMCP's 24KB response limit. Measured sizes (v1.5.2 real-world test):

| Tool | Size | Content |
|---|---|---|
| `lsDelegated_service` | 3,122KB | Full delegation tree (건축법) |
| `law_service` | 1,153KB | Full law text (민법) |
| `eflaw_service` | 538KB | Full law text (건축법) |
| `admrul_service` | 150KB | Full admin rule text |
| `drlaw_search` | 46KB | HTML dashboard (no XML parsing) |

These tools don't set `ranked_data`, so `slim_response()` correctly preserves `raw_content` (full text is the response). Size reduction is not possible without losing content.

**Planned fix:** Conditional tool registration - exclude `eflaw_service`/`law_service` when `SLIM_RESPONSE=true`, directing users to `eflaw_josub`/`law_josub` instead.

Other service tools (prec_service, detc_service, expc_service, decc_service) vary in size and usually fit under 24KB.

---

## Resolved Issues

### Issue #10: MCP Protocol Version 2025-06-18 Incompatibility - FIXED v2.0.0

**Status:** FIXED | **Severity:** MEDIUM | **Discovered:** 2025-12-11

Newer MCP clients send `protocolVersion: "2025-06-18"` which may cause intermittent errors. This is an ecosystem-wide transitional problem, not a LexLink bug.

**Fix:** FIXED v2.0.0 — upgraded to mcp>=1.26.0

---

### Issue #12: law.go.kr Anti-Bot JS Redirects Block API Responses - FIXED v1.5.1

**Status:** FIXED | **Severity:** CRITICAL | **Discovered:** 2026-03-01

law.go.kr returns HTML pages with JavaScript redirects (`window.location.assign()`) instead of XML data when called from cloud server IPs (GCP, AWS). The anti-bot pages return HTTP 200, so the client treats them as successful responses. Combined with `SLIM_RESPONSE=true` stripping `raw_content`, tools returned empty results (only `status`, `request_id`, `upstream_type`). Note: the empty-response aspect was further addressed in v1.5.2 with a safety guard — `raw_content` is now only removed when `ranked_data` exists as replacement.

**Root cause:** Anti-bot protection on law.go.kr injects JS-based redirect pages for non-browser clients. Two JS patterns observed: string concatenation (Pattern A) and substring slicing (Pattern B).

**Fix:** Added `_follow_antibot()` and `_parse_antibot_url()` in `client.py` to detect and follow JS redirects (up to 3 hops). Enabled `follow_redirects=True` on httpx client for subsequent HTTP 302 redirects.

**Note:** Server IP must also be registered at [open.law.go.kr](https://open.law.go.kr) for API access.

### Issue #11: Smithery Build Detects npm Instead of Python - FIXED v1.3.2 (HISTORICAL)

Smithery's build system incorrectly detected npm for this Python project. Fixed by adding explicit `startCommand` configuration to `smithery.yaml` with `uv run start`. *Note: Smithery dependency removed in v1.5.0.*

### Issue #9: article_citation Missing Dependency - FIXED v1.2.10

`beautifulsoup4` was not listed in `pyproject.toml` dependencies, causing `ModuleNotFoundError`. Added `beautifulsoup4>=4.12.0`.

### Issue #8: Linkage Search Tools Return No Data - FIXED v1.2.10

Three linkage tools (`lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`) were missing the XML parsing step, returning `ranked_data: null`. Added `parse_xml_response()` calls.

### Issue #6: Non-Law Searches Return Empty Results - FIXED v1.2.6, redesigned v1.5.2

`slim_response()` used law-specific field names for all data types, stripping all fields from non-law results. Fixed in v1.2.6 with `essential_fields_by_type` dict. **Redesigned in v1.5.2:** removed all field filtering entirely — real API testing showed search tools already return slim identifier-only data from the API (no bulk text to filter). Field filtering was removing useful fields (사건종류명, 상세링크) from already-small responses.

### Issue #5: LLM Parameter Confusion (id vs mst) - FIXED v1.2.5, obsolete v1.5.2

Removing `법령ID` from `essential_fields` (in v1.2.4) caused LLMs to confuse `법령일련번호` (MST) with `id`. Restored `법령ID` to essential fields. **Obsolete in v1.5.2:** field filtering removed entirely, all fields preserved.

### Issue #4: PlayMCP Response Size Limit Error - FIXED v1.2.4, redesigned v1.5.2

All search tools exceeded PlayMCP's 24KB limit (~50KB per response). Originally fixed by implementing `slim_response()` with field filtering (v1.2.4). **Redesigned in v1.5.2:** `slim_response()` now only removes redundant `raw_content` XML when `ranked_data` exists. No field filtering or truncation — search tools already return slim data. `aiSearch` default display reduced from 20 → 7 to stay under 20KB.

### Issue #3: Parameter Type Inconsistency Across Tools - FIXED v1.0.8

`eflaw_josub`, `law_josub`, and `lnkLsOrdJo_search` had inconsistent parameter types (`str` instead of `Union[str, int]`). Fixed all `id`, `mst`, and `jo` parameters to accept both types.

### Issue #2: Type Validation Error for id/mst Parameters - FIXED v1.0.2/v1.0.8

LLMs pass numeric values from XML as integers, but tool signatures declared `Optional[str]`. Changed to `Optional[Union[str, int]]` with automatic string conversion.

### Issue #1: JSON Format Not Supported by API - FIXED v1.0.1

law.go.kr API returns HTML error pages for JSON format despite documentation claiming support. Removed JSON from all tool parameter descriptions; LLMs now default to XML.

---

## Known Limitations

### Article Citation Range References

Citations like "제88조 내지 제93조" are a single HTML link. Only the first article number is extracted (`target_article: 88`).

### Article Citation - Deleted/Amended Articles

Citations may reference articles that no longer exist in current law versions. Still extracted but may not resolve to valid targets.

### Article Citation - External Law Name Resolution

External law names are text only. To get the MST of a cited law, a separate `eflaw_search` call is needed.

### LLM Instruction Adherence Varies by Model

Not all LLMs follow `SERVER_INSTRUCTIONS` reliably. Tested 2026-03-01 across 15 models, 50 rounds each (750 total API calls). Reliable (90%+): gemini-2.5-pro (100%), gpt-4.1 (100%), gpt-5.1 (94%), gpt-4o-mini (84%). Non-adherent (0-5%): gemini-3-flash/pro (0%), gpt-5/5-mini/5-nano (0%), gemini-3.1-pro (4%). gpt-4.1-mini misapplies embedded data (passes 법령ID as MST to wrong tool, 38% of responses). Model generation does not predict adherence — GPT-5 family is worse than GPT-4.1, Gemini 3.x is worse than Gemini 2.5-pro.

### Server IP Registration Required

When deploying to cloud servers (GCP, AWS, etc.), the server's public IP must be registered at [open.law.go.kr](https://open.law.go.kr). Without IP registration, the API returns "사용자 정보 검증에 실패하였습니다" (user verification failed). Excessive requests from unregistered IPs may trigger temporary IP blocks.

### simplify_article — Partial Knowledge Base Coverage

The `simplify_article` tool relies on the law.go.kr knowledge base API (`lstrm_ai_search`) for plain-language explanations. Coverage is partial: not all law articles have knowledge base entries. When an article is not found in the knowledge base, the tool falls back to returning the raw article text without simplification.

### OC Parameter Registration Required

Users must register at [open.law.go.kr](https://open.law.go.kr) and enable specific API categories. This is an API provider requirement, not a bug.

---

## Issue Statistics

| Category | Total | Fixed | Open |
|----------|-------|-------|------|
| Critical | 6 | 5 | 1 |
| High | 3 | 3 | 0 |
| Medium | 2 | 2 | 0 |
| Low | 1 | 1 | 0 |
| **Total** | **12** | **11** | **1** |

---

## Appendix: Citation Extractor Bug Fixes

Bug fixes applied to `src/lexlink/citation.py` (2025-11-30).

**Bug 1: Internal Citations Missing `target_article`**
- Standalone paragraph citations like `제2항` had `target_article: null`
- Fix: Added `current_internal_article_idx` tracking to maintain article context

**Bug 2: Multiple Paragraphs Overwriting**
- `제21조제1항ㆍ제2항` only captured the last paragraph
- Fix: Check if `target_paragraph` already exists → create new citation instead of overwriting

**Bug 3: External Law + Article Overwrite**
- `[형법] → [제20조] → [제1조]` merged all into one citation, losing 제20조
- Fix: Check `last.target_article is None` before merging into external law citation

**Verification:** 0 mismatches across 노동조합법 (100 citations), 자본시장법 (2,237), 근로기준법 (245).

---

## Contacts

**API Provider:** 법제처 공동활용 유지보수팀 (02-2109-6446) | [open.law.go.kr](https://open.law.go.kr)
**MCP:** [modelcontextprotocol.io](https://modelcontextprotocol.io)
