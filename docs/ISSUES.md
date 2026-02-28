# LexLink - Bugs and Issues Tracker

**Last Updated:** 2026-02-28

---

## Open Issues

### Issue #10: MCP Protocol Version 2025-06-18 Incompatibility

**Status:** KNOWN ISSUE | **Severity:** MEDIUM | **Discovered:** 2025-12-11

Newer MCP clients send `protocolVersion: "2025-06-18"` which may cause intermittent errors. This is an ecosystem-wide transitional problem, not a LexLink bug.

**Workaround:** Downgraded to `mcp 1.20.0` (from 1.23.3 which caused 502 errors).

**Fix:** Wait for `mcp` package to support protocol `2025-06-18` properly, then upgrade.

---

### Issue #7: Service Tools Exceed PlayMCP 24KB Limit

**Status:** OPEN | **Severity:** HIGH | **Discovered:** 2025-12-09

Law full-text tools (`eflaw_service`, `law_service`) always exceed PlayMCP's 24KB response limit (e.g., 형법=198KB, 민법=153KB). Even small laws like 난민법 are 36KB.

**Planned fix:** Conditional tool registration - exclude `eflaw_service`/`law_service` when `SLIM_RESPONSE=true`, directing users to `eflaw_josub`/`law_josub` instead.

Other service tools (prec, detc, expc, decc) vary in size and usually fit under 24KB.

---

## Resolved Issues

### Issue #11: Smithery Build Detects npm Instead of Python - FIXED v1.3.2 (HISTORICAL)

Smithery's build system incorrectly detected npm for this Python project. Fixed by adding explicit `startCommand` configuration to `smithery.yaml` with `uv run start`. *Note: Smithery dependency removed in v1.5.0.*

### Issue #9: article_citation Missing Dependency - FIXED v1.2.10

`beautifulsoup4` was not listed in `pyproject.toml` dependencies, causing `ModuleNotFoundError`. Added `beautifulsoup4>=4.12.0`.

### Issue #8: Linkage Search Tools Return No Data - FIXED v1.2.10

Three linkage tools (`lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`) were missing the XML parsing step, returning `ranked_data: null`. Added `parse_xml_response()` calls.

### Issue #6: Non-Law Searches Return Empty Results - FIXED v1.2.6

`slim_response()` used law-specific field names for all data types, stripping all fields from non-law results. Fixed with `essential_fields_by_type` dict mapping each data type (prec, detc, expc, decc, admrul) to its essential fields.

### Issue #5: LLM Parameter Confusion (id vs mst) - FIXED v1.2.5

Removing `법령ID` from `essential_fields` (in v1.2.4) caused LLMs to confuse `법령일련번호` (MST) with `id`. Restored `법령ID` to essential fields so LLMs can use the correct parameter.

### Issue #4: PlayMCP Response Size Limit Error - FIXED v1.2.4

All search tools exceeded PlayMCP's 24KB limit (~50KB per response). Implemented `slim_response()` that removes `raw_content` and filters `ranked_data` to essential fields only, reducing responses to ~3-5KB. Controlled by `SLIM_RESPONSE=true` env var.

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

### OC Parameter Registration Required

Users must register at [open.law.go.kr](https://open.law.go.kr) and enable specific API categories. This is an API provider requirement, not a bug.

---

## Issue Statistics

| Category | Total | Fixed | Open |
|----------|-------|-------|------|
| Critical | 5 | 4 | 1 |
| High | 3 | 3 | 0 |
| Medium | 2 | 1 | 1 |
| Low | 1 | 1 | 0 |
| **Total** | **11** | **9** | **2** |

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
