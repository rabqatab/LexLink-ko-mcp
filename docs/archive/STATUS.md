# LexLink Project Status

> **Archived 2026-10-31.** Historical record, not maintained. Counts, issue status and deployment details may be out of date. Current docs: [docs index](../README.md), [API reference](../API_REFERENCE.md), [CHANGELOG](../../CHANGELOG.md).


**Last Updated:** 2026-10-25
**Version:** v2.2.0
**Status:** Production-Ready (Phase 9 Complete)

---

## Summary

| Metric | Status |
|--------|--------|
| **Tools Implemented** | 55/55 (100%) |
| **MCP Prompts** | 9/9 (100%) |
| **MCP Resources** | 2 (1 static + 1 template) |
| **Semantic Validation** | 26/26 (Phase 1-5 tools) |
| **E2E Tests** | 5/5 (100%) |
| **LLM Integration** | 26/26 (Phase 1-5 tools) |
| **Citation Tests** | 25 unit + 15 integration (100%) |
| **Offline Tests** | 122 (`uv run pytest tests/`, `tests/` now tracked) |
| **Deployed On** | Kakao PlayMCP (GCP + nginx) |

---

## Architecture

- **OC priority:** Tool arg > Env var (set via HTTP header middleware or .env)
- **Response format:** JSON (default as of v2.0.0); XML and HTML also supported
- **Citation extraction:** HTML parsing (100% accuracy, zero API cost)
- **AI search:** law.go.kr knowledge base API for semantic queries
- **Anti-bot bypass:** Automatic JS redirect following for cloud server deployments
- **Embedded law IDs:** 20 common 법령IDs in SERVER_INSTRUCTIONS (fallback for resource-unaware clients)

## Key Files

| File | Description |
|------|-------------|
| `src/lexlink/server.py` | Main server (55 tools, 9 prompts, 2 resources) |
| `src/lexlink/_helpers.py` | Shared helpers (~380 lines): TOOL_ANNOTATIONS, handle_tool_error, run_search, run_service |
| `src/lexlink/cache.py` | Intelligent per-tool TTL caching (~183 lines) |
| `src/lexlink/resolver.py` | Korean law name/abbreviation resolution (~225 lines) |
| `src/lexlink/citation.py` | HTML citation extraction (~450 lines) |
| `src/lexlink/client.py` | HTTP client for law.go.kr (with anti-bot bypass) |
| `src/lexlink/stdio_server.py` | Stdio transport entry point |
| `src/lexlink/validation.py` | Input validation |
| `src/lexlink/params.py` | Parameter mapping |
| `src/lexlink/errors.py` | Error codes and responses (v2.2.0: `EMPTY_RESPONSE`, `API_NOT_SUBSCRIBED`, `UPSTREAM_HTML_ERROR`, `ARTICLE_NOT_FOUND`) |
| `src/lexlink/agency_codes.py` | Ministry/agency code tables (v2.2.0; 39 ministries, 재정경제부 alias) |
| `src/lexlink/linkage.py` | Knowledge-base linkage and ordinance-linkage request builders (v2.2.0) |
| `src/lexlink/article_text.py` | Full article text extraction (조문+항+호+목) for simplify/diff tools (v2.2.0, in progress) |

## Documentation

| Document | Purpose |
|----------|---------|
| `API_REFERENCE.md` | All 54 tool specs + 195 API catalog |
| `ROADMAP.md` | Phase-by-phase implementation history |
| `ISSUES.md` | Bug tracker (19 fixed, 4 open) |
| `AUDIT_CHECKLIST_2026-10-25.md` | Per-tool audit that drove the v2.2.0 fixes |
| `DEPLOYMENT_GUIDE.md` | EC2/PlayMCP deployment instructions |
| `../CHANGELOG.md` | Version history (v1.0.0 - v2.2.0) |

## Open Issues

- **#7:** Service tools exceed PlayMCP 24KB limit (planned: conditional registration)
- **#21:** Non-SLIM search tools return the 100-row ranking over-fetch in `raw_content` (display=2 still ~60KB); generalize `enforce_display` into `run_search`
- **#22:** `eflaw` 본문 API not subscribed on the deploy OC (account-level, not a code bug)
- **#23:** Unknown tool arguments are silently ignored

## Next Steps

- **Phase 6:** DONE — Refactored `server.py` with `_helpers.py` (~38% line reduction)
- **Phase 7:** DONE — Added 18 new tools (자치법규, 조약, 지식베이스, 위원회 결정문, 중앙부처 해석, 특별행정심판)
- **Phase 8:** DONE — Added 5 new tools (check_precedent_odds, legal_resolver, simplify_article, law_amendment_summary, article_amendment_diff) + 3 prompts; JSON is now default format
- **Phase 9:** DONE — Added 5 chain tools, `cache.py` (intelligent caching), `resolver.py` (law name resolution); inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)
- **Issue #10:** FIXED v2.0.0 — upgraded to mcp>=1.26.0
- **v2.2.0 (2026-10-25):** Audit-driven fixes (Issues #13-#20): cgm_expc target, special_decc ranking/display, knowledge-base linkage via `lawService.do`, `ordinLsCon_search` redesign (`lnkOrd`/`lnkLsOrd`/`lnkOrg`), `jo` normalization, structured upstream errors, `lexlink://law/{name}` resolution, cache key includes `type`. Phase 8 tools `law_amendment_summary`/`article_amendment_diff`/`simplify_article`/`chain_amendment_track` are fixed in the same release (data source `eflaw_search` filtered by 법령ID instead of `law_search`; full article text instead of heading only).
- **Upstream catalog:** guide now lists 195 API IDs (new: 감사원 사전컨설팅 의견서 `baiPvcs`, not implemented)
