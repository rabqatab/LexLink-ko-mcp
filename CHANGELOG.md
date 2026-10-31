# Changelog / 변경 로그

All notable changes to LexLink are documented here in both English and Korean.

---

## English

### Unreleased

#### Idle session expiry
- `LEXLINK_SESSION_IDLE_TTL_SEC` (default 3600, `0` disables): Streamable HTTP sessions with no activity for that long are terminated by the server (internal DELETE sent straight to the inner app) and their binding removed, freeing the `LEXLINK_MAX_SESSIONS` slot (also after a 503 at the cap). Sessions with a request in flight or an open GET stream are never idle. Expiry is done by a sweep task (interval min(ttl/4, 60) s, started and cancelled with the app lifespan) and lazily on a request for an idle session. The session is marked expiring first (requests get the standard unknown-session 404), the binding is removed only after the terminate succeeded (2xx/404), otherwise it is kept and retried at the next sweep. Requests for an expired id get the byte-identical unknown-session 404 for every token, so clients open a new session. Works in no-auth mode. SSE sessions end with their stream. mcp 1.26 keeps terminated transports in its session table, so the entry is dropped via one guarded `_server_instances.pop` (also on explicit owner DELETE).

#### Session binding hardening
- Every Streamable HTTP request without `mcp-session-id` (any method, any query) reserves a cap slot before the app runs (503 at the cap, no overshoot under concurrency) and any `mcp-session-id` in its response is bound and counted; a session whose creating response is not 2xx is terminated and released right away (retried by the sweeper on failure, also with TTL 0). Query `session_id` is only enforced on the SSE `/messages/` path. Requests naming several different session ids get the unknown-session 404.
- A 404 from the app no longer frees a binding or the mcp instance; only a confirmed terminate or an owner DELETE 2xx does. The Host used for the internal DELETE is only taken from requests answered other than 421/404 (default: first `LEXLINK_ALLOWED_HOSTS` entry). The SSE foreign-id 404 is byte-identical to mcp's (no content-type). Ended SSE streams are tombstoned (404 for every token). Failed terminates back off exponentially per session (sweep interval up to 15 min) with one warning line (no traceback, no session id). `mcp.server.streamable_http_manager`, `mcp.server.streamable_http` and `mcp.server.sse` loggers are raised so session ids stay out of logs.

#### Session binding
- New pure ASGI `SessionBindingMiddleware` (order Auth > Logging > RateLimit > SessionBinding > app): MCP sessions (Streamable HTTP `mcp-session-id`, SSE `session_id` from the `endpoint` event) are bound to the creating token. Another token gets the same 404 an unknown session gets and never reaches the app; owner DELETE / SSE close removes the binding. `LEXLINK_MAX_SESSIONS` (default 10000) caps bindings; at the cap new sessions get 503 rather than evicting (eviction would leave an unbound, usable session). No-auth mode shares one id, so binding is a no-op.

#### HTTP hardening follow-up
- Default logs no longer contain client-controlled strings: `tool_name` only for registered tools (else `<unknown>`), argument keys only if declared in the tool schema (others counted in `unknown_arg_keys`), `method` limited to known MCP methods. `create_app` passes tool names/schemas to `LoggingMiddleware`.
- `LEXLINK_LOG_BODIES` now drops oc/token/authorization-like keys recursively (dicts, lists, JSON inside `result` text).
- `uvicorn.run(..., proxy_headers=False)`; documented factory command uses `--no-proxy-headers` so `LEXLINK_TRUSTED_PROXIES` is the only X-Forwarded-For authority.
- `BearerAuthMiddleware` closes websocket scopes with 1008; only lifespan passes unchecked.
- `LEXLINK_ALLOWED_ORIGINS` without `LEXLINK_ALLOWED_HOSTS` raises at startup.
- Log retention runs at writer start; log files 0600, directory 0700; dropped log entries are counted and warned about at most once a minute.
- SSE transport logs a startup warning (per-request log status and concurrency cannot see results on the GET stream). Docs: DEPLOYMENT_GUIDE commands now include tokens, allowed hosts, Authorization and Host headers; OPERATIONS.md documents SSE limits, per-process oc override, http-only factory, unbound sessions, unlogged 401s, delayed 429s.

#### Security
- HTTP/SSE mode is now authenticated and fail-closed: `LEXLINK_AUTH_TOKENS="name:token,..."` (Bearer, constant-time compare, 401 + `WWW-Authenticate: Bearer`). Startup raises without tokens unless `LEXLINK_ALLOW_NO_AUTH=true` (PlayMCP no-auth registration only; loud warning). In HTTP mode the tool `oc` argument is ignored (`params.set_ignore_oc_override`); stdio is unchanged.
- New `http_security.py` (pure ASGI): per-token concurrency (`LEXLINK_MAX_CONCURRENCY`, default 8) and per-minute (`LEXLINK_RATE_LIMIT_PER_MIN`, default 60) limits with 429 + `Retry-After`; Host/Origin validation via `LEXLINK_ALLOWED_HOSTS`/`LEXLINK_ALLOWED_ORIGINS` (DNS-rebinding protection is never disabled).
- Traffic log is now privacy-preserving by default (argument key names only, no values/results/tokens; `LEXLINK_LOG_BODIES=true` opts in, OC redacted), written by a background thread, with `LEXLINK_LOG_RETENTION_DAYS` (default 30) retention. `X-Forwarded-For` is honoured only from `LEXLINK_TRUSTED_PROXIES`.

#### Changed
- Responses no longer cut content that was already fetched: `check_precedent_odds` (holding/summary excerpts, `key_factors`), `legal_resolver` (`article_text`, `citations`), `chain_full_research` (`representative_cases`), and `chain_law_system` (delegation tree entries and references) return everything by default. `compact_delegation_tree` has no entry cap unless `max_entries` is given. The one exception: `simplify_article` looks up at most 20 legal terms upstream (`extract_legal_terms` cap).
- `SLIM_RESPONSE=true` (also `1`, `yes`, `on`; case-insensitive) additionally keeps those compact caps (500 chars, top 10/3, 80 delegation entries), so PlayMCP output is unchanged. Fan-out caps and `display` limits are unaffected.
- `RawLoggingMiddleware` (BaseHTTPMiddleware that buffered whole responses, hung GET streams and dropped multi-value headers) replaced by pure ASGI `LoggingMiddleware` that forwards every message immediately. `log_mcp_call`/`log_raw` removed.
- Module-level `_server`/`_sse_app`/`app` removed; use `create_app(transport)` (single `create_server()` call; `uvicorn --factory lexlink.http_server:create_app`, single worker). `create_server(transport_security=None)` accepts FastMCP transport security settings.
- New Korean operations guide: `docs/OPERATIONS.md`.

#### Fixed
- `prec_service` / `detc_service` / `expc_service`: an upstream "일치하는 … 없습니다" answer (unknown id, or a case whose body the API does not provide, e.g. 국세법령정보시스템 precedents) now returns the new `NOT_FOUND` error instead of `status: ok`. Errors are never cached.
- `prec_service(sections="summary")` falls back to including 판례내용 (`sections: "summary_fallback"` plus a warning) when both 판시사항 and 판결요지 are empty.
- `prec_search` marks 국세법령정보시스템 items with `본문제공: "API 미제공"`; use `dat_src_nm="대법원"` to search only sources whose body is served.
- Section filtering (`sections="summary"`) no longer mutates the cached full response, which a later full call used to return stripped.
- `check_precedent_odds` skips cases without a body, moves on to the next candidate, and reports `unavailable_cases`.
- `legal_resolver` citations were always empty (coroutine run on FastMCP's already running event loop, error swallowed, and wrong citation keys read). It now runs the extraction in a worker thread, reads `target_law_name` / `type`, and reports failures in a `warnings` list (also carried by `chain_full_research`).
- `lawService.do` bodyless successes (blank body, `{}`, or only empty values) and "일치하는 법령이 없습니다" now return `NOT_FOUND` instead of `status: ok`. `article_amendment_diff` still tries the other MST when one version is missing.
- `elaw_service`, `admrul_search`, `admrul_service`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`, `lsDelegated_service` now send `type`, so the cache key includes the response format.
- `check_precedent_odds` no longer falls back to the search row number when 판례일련번호 is missing.
- Generic `NOT_FOUND` hint no longer builds a nonexistent `<target>_search` tool name.
- `article_citation` verifies `mst` / `law_name` / article with one `lawService` call (`target=law`, `MST`, `JO` incl. branch) when an OC is available: a name mismatch returns `VALIDATION_ERROR` naming both laws, a missing article returns `ARTICLE_NOT_FOUND`, upstream `NOT_FOUND` passes through (all with `success: false`). Without an OC it skips verification and adds a `warnings` entry. The lsiSeq cache is keyed by `(mst, law_name)`, no longer by `mst` alone.
- Ranked searches (over-fetch of 100 rows) returned an empty page 2+. When `page * display <= 100` the first 100 rows are fetched, ranked, and sliced for the requested page (also `elaw_search`); beyond that ranking is skipped, `page`/`display` are forwarded unchanged and `ranking_applied: false` is set.
- Zero-result searches (`run_search`, `elaw_search`) and empty `legal_resolver` / `check_precedent_odds` / `chain_dispute_prep` results keep `status: ok` but add `warning: "no_results"`, `message` and Korean `hints` (shorten query, use the formal name, `search=2` where the tool has it).
- `extract_outcome` checks specific outcomes first (일부인용, 일부기각, 파기환송 ...) and requires disposition context for 기각/각하/인용/취소, so "일부인용" is no longer "인용" and "원심판결 인용" / "인용하지" / "인용된" are `불명`. `check_precedent_odds` adds `outcome_note` (heuristic, not a citable result).
- `ordin_search` `knd` docstring: official codes are 30001 조례, 30002 규칙, 30003 훈령, 30004 예규, 30006 기타, 30010 고시, 30011 의회규칙 (source: open.law.go.kr ordinListGuide); 1/2/3 are not valid.
- `lawService.do` "일치하는 … 없습니다" is `NOT_FOUND` only when the whole body is that message (short real bodies quoting the phrase pass); query-keyed linkage targets get a "연계 정보가 없거나 검색어를 확인하세요" hint. `id_note` is dropped with `raw_content` under `SLIM_RESPONSE`. `legal_resolver` reports `success: false` citation extractions in `warnings`.
- Search cache: `ResponseCache.get`/`put` now return/store shallow copies, and `enforce_display` no longer edits its input. `cgm_expc_search` / `special_decc_search` pages 2+ were empty and a larger `display` after a smaller one still returned the smaller page.
- Paging across the 100-row ranking window: row order is the ranked first 100 upstream rows, then upstream rows 101+ in upstream order. Pages inside the window are ranked, pages beyond it fetch the covering size-100 upstream page(s) (`ranking_applied: false`), and straddling pages combine the ranked tail with the head of upstream page 2 (`ranking_applied: "partial"`, at most 2 upstream calls). No duplicate or missing rows for display 1-100, JSON and XML, `run_search` and `elaw_search`, both over-fetch keys; `ranked_data` is present on every page (also elaw beyond the window).
- `page < 1` or `display < 1` raise a validation error (was silently page 1 / odd slices); `display > 100` still clamps. `ranked_data.page` is the requested page. A page past the last result adds the hint `no_more_results`.
- `legal_resolver`, `check_precedent_odds`, `chain_dispute_prep`, `chain_full_research`: when every sub-search failed they return the upstream error code (or `UPSTREAM_ERROR` for mixed codes) with hints instead of `ok` + `no_results`; when only some failed they return `ok` with `warnings` naming the source and code and never claim `no_results`.
- `article_citation` name check also accepts the body's `법령명약칭` (or, on mismatch only, one `law_search` for the official name's `법령약칭명`), ignores `「」`, parenthetical suffixes such as `(법률)` and whitespace; 법/시행령/시행규칙 mismatches are still rejected.
- `article_citation`: only `NOT_FOUND`, `ARTICLE_NOT_FOUND` and a name mismatch block (all with `success: false`); TIMEOUT, API_NOT_SUBSCRIBED, UPSTREAM_ERROR etc. continue the scrape with a `warnings` entry naming the code.
- `extract_outcome` is position-based (earliest genuine disposition). Negations and modals (`하지 아니`, `할 수 없`, `될 수 없`, `될 것`, `되어야`, `사유가 없`) no longer count, bare 파기 needs a disposition ending, `파기하고 … 환송` within 40 characters is 파기환송, `일부를 인용/기각` is 일부인용/일부기각, and 취소 only counts as a disposition (not 취소소송 / 취소를 구하는). The unused `OUTCOME_KEYWORDS` constant was removed.
- `ordin_search` `rr_cls_cd` docstring now says 제개정 종류, matching the API reference.

#### Changed (behaviour)
- Search responses: in `ranked_data`, each row's `id` (upstream row number 1, 2, 3, not a key) is renamed to `rank`. `raw_content` is unchanged and, when kept, a new `id_note` explains that its `id` is a row number. Use 판례일련번호, 법령ID, 법령일련번호(MST) etc. for service calls.

#### Docs
- `docs/ISSUES.md` lists `*_service` tools without a size-control option; their docstrings now warn that responses can be large.

#### Security
- The OC credential is removed from upstream response bodies (e.g. `판례상세링크`), error messages, and debug/request logs (`has_oc` flag only); the `httpx` logger is limited to WARNING. The client's generic error path logs a redacted message plus traceback frames only. Encoded forms (`%3FOC%3D`, `&#38;OC=`, `\x26OC=`, `<OC>..</OC>`) are removed; redaction is linear-time and leaves legal text alone (`OC: "Office of Command"`, `"law" means`).
- OC removal is now structural (hidden `name="OC"` form fields, `OC = '...'` / `"OC":"..."` assignments) regardless of the value; short literal values are replaced only when quote/`=`/`&`-delimited. Tool error messages and logs are redacted too (no `logger.exception`).

---

### v2.2.0 (2026-10-25)

#### Fixed (P0)
- `cgm_expc_search` / `cgm_expc_service`: upstream target names were inverted (`cgmExpcMoel` → `moelCgmExpc`); all 39 ministries returned empty results.
- Knowledge-base linkage tools (`lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`) called `lawSearch.do` instead of `lawService.do` and returned nothing. They now take `query`/`mst` and an optional `trm_rlt_cd`; `jo_rlt_lstrm_search` requires `jo`.
- `ordinLsCon_search` used a nonexistent upstream target; redesigned with three modes: `query` → lnkOrd, `law_id` → lnkLsOrd, `org` → lnkOrg.

#### Fixed (P1)
- `special_decc_search` ignored `display` and returned 100 rows (~59KB).
- `jo` arguments now accept `35`, `35의5`, `제35조의5`, and `003505` (normalized to 6 digits); `ARTICLE_NOT_FOUND` is returned when the article is missing.
- Upstream HTML/empty-body responses now become structured errors (`API_NOT_SUBSCRIBED`, `EMPTY_RESPONSE`, `UPSTREAM_HTML_ERROR`) instead of `status: ok`.
- Resource `lexlink://law/{name}` now URL-decodes the name and resolves aliases (e.g. 자통법).
- `serverInfo.version` now reports LexLink's version instead of the mcp library version.
- Cache key now includes the response format (a JSON body was being served to XML requests).
- Ministry rename 기획재정부 → 재정경제부 (old name kept as alias). 재정경제부 and 국세청 have a list API only.

#### Planned in this release (being merged)
- `law_amendment_summary` builds revision history from `eflaw_search` filtered by 법령ID (previously it listed current laws from `law_search`).
- `simplify_article`, `article_amendment_diff`, `chain_amendment_track` extract full article text (항/호/목) via the new `article_text.py` instead of the heading only.
- The current (현행) version is preferred over the scheduled (시행예정) version.
- Precedent tools fall back to body-text search (`search=2`).
- The stale `date_to="20261231"` default is replaced by the computed end of the current year.

#### Infrastructure
- New modules: `agency_codes.py`, `linkage.py`, `article_text.py`.
- `tests/` is now tracked (122+ offline tests).
- Audit document: `docs/AUDIT_CHECKLIST_2026-10-25.md`.

---

### v2.1.0 (2026-03-30)

#### Added
- **Intelligent Caching** (`cache.py`): Per-tool TTL caching with semantic query normalization. Search results cached 1hr, articles 24hr, AI search 30min. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp).
- **Law Name Resolution** (`resolver.py`): Auto-resolves Korean law abbreviations (자통법→자본시장과 금융투자업에 관한 법률). 52 seed aliases + dynamic learning from API responses. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp).
- **Phase 9: Chain Tools** (5 new tools): Multi-step research workflows in one call. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp).
  - chain_full_research: Complete legal research (statutes + precedent analysis + interpretations)
  - chain_amendment_track: Revision history + article-level diff
  - chain_dispute_prep: All case law sources across 4 databases
  - chain_law_system: Full law hierarchy (delegation tree + admin rules + ordinances)
  - cache_stats: Cache and resolver performance monitoring

#### Infrastructure
- New module: `src/lexlink/cache.py` (~183 lines)
- New module: `src/lexlink/resolver.py` (~225 lines)
- Caching integrated into `run_search` and `run_service` helpers
- Law name resolution integrated into `run_search`
- Total tools: 54 (was 49)

---

### v2.0.0 - 2026-03-30

#### Added
- **Phase 7: Extended Legal Information (18 new tools)**
  - 자치법규 (Local Ordinances): ordin_search, ordin_service, ordinLsCon_search
  - 조약 (Treaties): trty_search, trty_service
  - 법령정보 지식베이스 (Knowledge Base): 7 legal term search and linkage tools (lstrm_ai_search, dlytrm_search, lstrm_rlt_search, dlytrm_rlt_search, lstrm_rlt_jo_search, jo_rlt_lstrm_search, ls_rlt_search)
  - 위원회 결정문 (Committee Decisions): committee_search/service (12 committees)
  - 중앙부처 1차 해석 (Ministry Interpretations): cgm_expc_search/service (39 ministries)
  - 특별행정심판 (Special Appeals): special_decc_search/service (4 tribunals)

#### Changed
- **Phase 6: Code Refactoring** — extracted shared helpers to `_helpers.py`, reducing server.py by ~38%
  - TOOL_ANNOTATIONS, handle_tool_error, run_search, run_service helpers
  - All 26 existing tools refactored as thin wrappers
- **Issue #10 resolved**: Upgraded mcp dependency to >=1.26.0

#### Infrastructure
- New module: `src/lexlink/_helpers.py` (~211 lines)
- New parameter mappings: eft_yd, conc_yd, nat_cd, sborg, ordin_fd
- Total tools: 44 (was 26)

---

### v1.5.2 - 2026-03-02
**Fix: slim_response() redesign — safety guard + no field stripping**

- **Bug fix (empty responses):** `slim_response()` unconditionally removed `raw_content` even when `ranked_data` was missing (ranking chain failure), leaving empty responses `{status, request_id, upstream_type}` on PlayMCP
- **Bug fix (aiSearch oversized):** `list_keys` whitelist didn't include `법령조문`, so field filtering silently skipped for `aiSearch` — responses remained ~46KB
- **Redesign:** Removed all field filtering and truncation logic. `slim_response()` now only removes `raw_content` (redundant raw XML) when `ranked_data` exists as replacement
  - **Rationale:** Real API testing showed search tools already return slim identifier-only data (~5-13KB). The old field-filtering approach was stripping useful fields (사건종류명, 상세링크, etc.) from already-small responses
  - Service tools (`_service`) don't set `ranked_data`, so `raw_content` is correctly preserved (full text is the response)
- **aiSearch default display:** Changed from 20 → 7 to stay under 20KB (조문내용 ~600 chars/item × 7 = ~15KB)
- **Verified:** All search tools under 20KB; service tools preserve full text

### v1.5.1 - 2026-03-01
**Fix: Anti-Bot Bypass & Embedded Law IDs**

- **Anti-bot bypass:**
  - law.go.kr returns HTML pages with JavaScript redirects (`window.location.assign()`) instead of API data from cloud server IPs (GCP, AWS)
  - Added `_follow_antibot()` method in `client.py` that detects and follows JS redirects (up to 3 hops)
  - Added `_parse_antibot_url()` parser handling two known JS patterns:
    - Pattern A (concat): `x={t:'...', h:'...', o:'...'}; return x.t+x.h+x.o`
    - Pattern B (substr): `x={o:'...', c:N}; z=M; return o.substr(0,c)+o.substr(c+z)`
  - Enabled `follow_redirects=True` on httpx client (anti-bot token URLs return HTTP 302)
- **Embedded law IDs in SERVER_INSTRUCTIONS:**
  - MCP resources (`lexlink://laws/frequently-used`) are not surfaced to LLMs by PlayMCP or Smithery proxy clients
  - Embedded 20 verified 법령ID mappings directly in `SERVER_INSTRUCTIONS` so LLMs can skip `eflaw_search` for common laws regardless of client resource support
  - All 20 IDs verified against live law.go.kr API (2026-03-01)
- **Impact:** API calls work through anti-bot protection; common law lookups work on all MCP clients

### v1.5.0 - 2026-02-28
**Refactor: Remove Smithery Dependency**

- **Removed:** `smithery` package dependency and 8 transitive dependencies (art, rich, typer, etc.)
- **Removed:** `config.py` (`LexLinkConfig` schema), `smithery.yaml`
- **Simplified:** OC resolution from 3-tier (tool arg > session config > env) to 2-tier (tool arg > env var)
- **Simplified:** `create_server()` no longer takes `session_config` parameter
- **Simplified:** `http_server.py` no longer unwraps `SmitheryFastMCP` wrapper
- **Added:** `stdio_server.py` entry point replacing `smithery.cli.start:main`
- **Updated:** `_get_client()` reads from `LEXLINK_BASE_URL` and `LEXLINK_TIMEOUT` env vars
- **Scripts:** Removed `dev`, `start`, `playground`; added `stdio` for stdio transport
- **Impact:** Cleaner dependency tree, simpler codebase (~80 lines removed across 26 tools)

### v1.4.0 - 2026-02-28
**Feature: MCP Resources - Law ID Cache**

- **New MCP Resources:**
  - `lexlink://laws/frequently-used` (static) - Cached list of ~20 frequently-used Korean law names mapped to stable 법령ID codes
  - `lexlink://law/{name}` (template) - Look up a specific law's 법령ID by Korean name or abbreviation
- **Implementation:**
  - In-memory cache seeded with 20 verified law entries (IDs verified against live law.go.kr API)
  - Dynamic caching: `eflaw_search` and `law_search` auto-cache top 3 ranked results after each search
  - Both full names and abbreviations are matchable (e.g., "자본시장법" → 자본시장과 금융투자업에 관한 법률)
  - Template resource returns fallback message directing to `eflaw_search` or `law_search` when law is not cached
- **LLM Preference Test (100 runs):**
  - Both Gemini 2.5 Flash and Gemini 3 Flash Preview showed 100% resource adoption (0% search tool fallback)
  - Template resource preferred over static: 92% (2.5-flash) / 70% (3-flash-preview)
- **Other Changes:**
  - Fixed `__init__.py` version: `0.1.0` → `1.3.2`
  - Updated `SERVER_INSTRUCTIONS` with resources section and MST requirement for `article_citation`
- **Impact:**
  - Eliminates redundant `eflaw_search` calls for frequently-used laws
  - LLMs can look up 법령ID directly via resources, skipping the search step

### v1.3.2 - 2026-01-13
**Fix: Smithery Build npm Detection Error**

- **Issue:** Smithery build system incorrectly detected npm as package manager, failing with "npm error path /home/repo/package.json"
- **Root Cause:** Previous `smithery.yaml` only had `runtime: python` which is insufficient for Smithery's current build system
- **Solution:**
  - Rewrote `smithery.yaml` with proper `startCommand` configuration
  - Added `type: stdio` to declare stdio-based MCP server
  - Added `configSchema` for optional `oc` parameter in Smithery UI
  - Added `commandFunction` to run `uv run start` with `OC` env var
- **Files Changed:**
  - `smithery.yaml` - Complete rewrite with `startCommand` configuration
- **Reference:**
  - [perplexity-mcp smithery.yaml](https://github.com/jsonallen/perplexity-mcp/blob/main/smithery.yaml) - Working Python MCP example

### v1.3.1 - 2025-12-25
**Feature: PlayMCP Traffic Logging**

- **New Modules:**
  - `raw_logger.py` - Dashboard-compatible MCP traffic logger
  - `log_processor.py` - Log format converter utility
- **Implementation:**
  - `RawLoggingMiddleware` in HTTP server for request/response capture
  - JSONL format with merged request/response pairs
  - Daily log rotation at `logs/playmcp/YYYY-MM-DD.jsonl`
  - SSE streaming response parsing
- **Log Schema:**
  - `request_id`, `timestamp`, `duration_ms`
  - `method`, `tool`, `arguments`, `result`
  - `status_code`, `client_ip`, `headers`
- **Impact:**
  - Enables traffic analysis for PlayMCP deployments
  - Dashboard-compatible format for monitoring

### v1.3.0 - 2025-12-24
**Feature: Phase 5 - AI-Powered Search Tools**

- **New Tools:**
  - `aiSearch` - AI-powered semantic law search (Tool 25)
  - `aiRltLs_search` - AI-powered related laws search (Tool 26)
- **Implementation:**
  - Uses law.go.kr's intelligent search system (지능형 법령검색)
  - Semantic search for natural language queries
  - Returns full article text (조문내용) for comprehensive results
  - XML parsing with ranked_data for LLM consumption
- **LLM Guidance:**
  - Added ⭐ PREFERRED TOOL hints in tool descriptions
  - Added `tool-selection-guide` MCP prompt for tool selection guidance
  - Tools marked as preferred for vague/unclear queries
- **Impact:**
  - Tool count: 24 → 26 tools
  - MCP prompts: 5 → 6 prompts
  - Better handling of natural language legal queries

### v1.2.9 - 2025-12-09
**Fix: Case-insensitive item key matching for API inconsistency**

- **Issue:** law.go.kr API uses inconsistent XML tag casing
  - `prec` search → `<prec>` (lowercase)
  - `detc` search → `<Detc>` (capitalized)
  - `expc` search → `<Expc>` (capitalized)
- **Fix:** Made `extract_items_list`, `update_items_list`, and `slim_response` case-insensitive

### v1.2.8 - 2025-12-09
**Fix: Case-sensitive item key extraction for non-law searches**

- **Issue:** `extract_items_list()` used capitalized keys ('Prec', 'Detc', 'Expc', 'Decc') but XML parser outputs lowercase ('prec', 'detc', etc.)
- **Result:** `ranked_data` never set → empty responses for all non-law searches
- **Fix:** Changed all 8 calls to use lowercase keys

### v1.2.7 - 2025-12-09
**Refactor: Pattern-based essential field detection**

- **Issue:** Manual field definitions per data type required maintenance for each new API
- **Solution:** Regex pattern matching for automatic field detection
- **Patterns:** `*일련번호` (IDs), `*명한글/*명` (names), `*일자` (dates), etc.
- **Benefit:** Works automatically for any data type without manual definitions

### v1.2.6 - 2025-12-09
**Fix: Data-type-specific essential fields for slim response**

- **Issue:** `slim_response()` used law-specific field names for all data types
  - Precedent searches (`prec_search`) returned empty results
  - Fields like `판례일련번호`, `사건명` were filtered out because they didn't match law fields
- **Solution:**
  - Implemented `essential_fields_by_type` dictionary with correct fields per data type
  - Each API type (law, prec, detc, expc, decc, admrul, elaw) now has its own essential fields

### v1.2.5 - 2025-12-09
**Fix: Add 법령ID to essential fields for correct parameter usage**

- **Issue:** LLM was confusing `법령일련번호` (MST) with `법령ID` in slimmed responses
  - Example: Calling `eflaw_service(id="235555")` when 235555 is MST, not 법령ID
  - Correct usage should be `eflaw_service(mst=235555)` or `eflaw_service(id="001624")`
- **Solution:**
  - Added `법령ID` back to `essential_fields` in `slim_response()`
  - Now LLM can see both fields and use correct parameter
- **Essential fields:** 법령명한글, 법령일련번호, **법령ID**, 현행연혁코드, 시행일자
- **Note:** If ranking not working, ensure EC2 has latest code with relevance ranking

### v1.2.4 - 2025-12-09
**Fix: Slim response mode for PlayMCP size limits**

- **Issue:** v1.2.3's truncation approach was insufficient because `ranked_data` still contained full data (~25KB per 50 results)
- **Solution:**
  - Replaced `truncate_response()` with `slim_response()` function
  - When `SLIM_RESPONSE=true`: removes `raw_content` entirely and keeps only essential fields in `ranked_data`
  - Essential fields kept: 법령명한글, 법령일련번호, 현행연혁코드, 시행일자
  - Fields removed: 법령약칭명, 공포일자, 공포번호, 제개정구분명, 소관부처코드, 소관부처명, 법령구분명, 공동부령정보, 자법타법여부, 법령상세링크
- **Configuration:**
  - Smithery: No change needed (full response)
  - PlayMCP: Set `SLIM_RESPONSE=true` in systemd service
- **Impact:**
  - Response size reduced from ~50KB to ~3-5KB for 50 results
  - PlayMCP works reliably without size errors

### v1.2.3 - 2025-12-08
**Fix: Response truncation for PlayMCP size limits**

- **Issue:** PlayMCP has response size limits (~50KB), causing "Tool call returned too large content part" errors
- **Solution:**
  - Added `truncate_response()` helper function for optional response size limiting
  - Applied truncation to all 11 search tools (eflaw_search, law_search, elaw_search, admrul_search, lnkLs_search, lnkLsOrdJo_search, lnkDep_search, prec_search, detc_search, expc_search, decc_search)
  - Added `MAX_RESPONSE_SIZE` environment variable (only truncates when set)
- **Configuration:**
  - Smithery: No change needed (no size limit)
  - PlayMCP: Set `MAX_RESPONSE_SIZE=50000` in systemd service
- **Impact:**
  - Smithery keeps full functionality (unlimited responses)
  - PlayMCP avoids size errors with truncated responses + Korean message

### v1.2.2 - 2025-12-06
**Feature: HTTP/SSE Server for Kakao PlayMCP**

- **New Feature:**
  - Added HTTP/SSE server support for Kakao PlayMCP deployment
  - New `uv run serve` command to start HTTP server
  - OCHeaderMiddleware extracts OC from HTTP headers (Key/Token auth)
  - Supports both SSE (`/sse`) and Streamable HTTP (`/mcp`) transports
- **Breaking Changes:**
  - Renamed `LAW_OC` environment variable to `OC` (matches official law.go.kr API naming)
- **Configuration Changes:**
  - Removed `base_url` from Smithery UI config (kept as internal field only)
  - Updated default timeout from 15s to 60s
  - Timeout range extended to 5-120s
- **Documentation:**
  - Added Kakao PlayMCP deployment guide (`docs/DEPLOYMENT_GUIDE.md`)
  - Updated README with PlayMCP deployment section
  - Added `http_server.py` to project structure
- **Impact:**
  - LexLink can now be deployed to Kakao PlayMCP and similar HTTP-based platforms
  - Each PlayMCP user provides their own OC via HTTP header (uses their own API quota)

### v1.2.1 - 2025-11-30
**Fix: Improve LLM guidance for specific article queries**

- **Issue:** LLMs were fetching entire laws (1MB+ for 자본시장법) instead of using `jo` parameter for specific articles like "제174조"
- **Solution:**
  - Added **IMPORTANT** notices in `eflaw_service` and `law_service` docstrings about using `jo` parameter
  - Added **BEST TOOL** guidance in `eflaw_josub` and `law_josub` docstrings
  - Added practical examples: `jo="017400"` for 제174조, `jo="000300"` for 제3조
  - Warned about large response sizes (400+ articles, 1MB+ responses)
- **Impact:**
  - LLMs now correctly use `jo` parameter for specific article queries
  - LLMs prefer `law_josub`/`eflaw_josub` for article queries
  - Faster responses and cleaner output for specific article requests

### v1.2.0 - 2025-11-30
**Feature: Phase 4 - Article Citation Extraction**

- **New Tool:**
  - `article_citation` - Extract legal citations from any law article (Tool 24)
- **Implementation:**
  - HTML parsing approach for 100% accuracy (no LLM hallucination risk)
  - CSS class-based citation type detection (sfon1-4 classes)
  - MST ↔ lsiSeq ID mapping between XML API and HTML pages
  - Zero external API costs (no LLM calls required)
  - ~350ms average extraction time
- **Features:**
  - Distinguishes internal vs external citations
  - Extracts article, paragraph, and sub-item references
  - Consolidates duplicate citations with citation counts
  - Preserves raw citation text for context
- **MCP Prompts Added:**
  - `extract-law-citations` - Extract and explain citations from a law article
  - `analyze-citation-network` - Analyze legal citation network for a law
- **Test Coverage:**
  - Unit tests: Citation module 100% coverage
  - Integration tests: End-to-end extraction validated
  - LLM workflow tests: Gemini 2.0 Flash validated
- **Known Limitations:**
  - Range references (e.g., "제88조 내지 제93조") return first article only
  - External law names require separate search for MST lookup
- **Impact:**
  - Tool count: 23 → 24 tools
  - MCP prompts: 3 → 5 prompts
  - Enables citation network analysis workflows

### v1.1.0 - 2025-11-14
**Feature: Phase 3 - Case Law & Legal Research APIs**

- **Changes:**
  - Added 8 new tools for case law and legal research (15 → 23 tools)
  - `prec_search`, `prec_service` - Court precedents (판례)
  - `detc_search`, `detc_service` - Constitutional Court decisions (헌재결정례)
  - `expc_search`, `expc_service` - Legal interpretations (법령해석례)
  - `decc_search`, `decc_service` - Administrative appeal decisions (행정심판례)
- **Implementation:**
  - Added generic parser functions (`extract_items_list`, `update_items_list`) that work with any XML tag
  - Added 13 new Phase 3 parameters: `prnc_yd`, `dat_src_nm`, `ed_yd`, `reg_yd`, `expl_yd`, `dpa_yd`, `rsl_yd`, `curt`, `inq`, `rpl`, `itmno`, `cls`
  - All ranking and validation functions compatible with Phase 3 tools
  - Zero breaking changes to existing Phase 1 & 2 tools
- **Impact:**
  - Tool count increased by 53% (15 → 23 tools)
  - API coverage increased from ~10% to ~15%
  - Legal research categories expanded by 133% (3 → 7 categories)
  - All 23 tools validated and working in production

### v1.0.8 - 2025-11-13
**Fix: Complete parameter type consistency across all tools**

- **Issue:** v1.0.2 fixed 7 tools but missed 2 additional tools (`eflaw_josub`, `law_josub`), creating inconsistency where same parameters had different types across tools
- **Root Cause:**
  - `eflaw_josub` and `law_josub` still had `id: Optional[str]` and `mst: Optional[str]` instead of `Union[str, int]`
  - `lnkLsOrdJo_search` had `jo: Optional[int]` instead of `Union[str, int]`
  - Caused validation errors when LLMs passed integers to these specific tools
- **Solution:**
  - Fixed `eflaw_josub`: `id` and `mst` now accept `Union[str, int]`
  - Fixed `law_josub`: `id` and `mst` now accept `Union[str, int]`
  - Fixed `lnkLsOrdJo_search`: `jo` now accepts `Union[str, int]`
- **Verification:**
  - All 7 tools with `id` parameter now consistently `Optional[Union[str, int]]`
  - All 6 tools with `mst` parameter now consistently `Optional[Union[str, int]]`
  - All 5 tools with `jo` parameter now consistently `Optional[Union[str, int]]`
- **Impact:**
  - 100% parameter type consistency achieved
  - No validation errors regardless of which tool LLMs choose
  - Better developer experience - same parameters work identically everywhere

### v1.0.7 - 2025-11-10
**Fix: Improve search reliability and LLM guidance**

- **Issue:** LLMs often failed to find common laws like "민법" (Civil Code) because:
  1. Ranking fetch limit (50 results) was too small for large result sets (e.g., 77 results for "민법")
  2. LLMs defaulted to small `display` values (e.g., 5), missing exact matches
  3. `jo` parameter rejected integers, causing validation errors and retry loops
- **Root Cause:**
  - v1.0.5 ranking fetched only 50 results; "민법" was beyond position 50 alphabetically
  - Tool descriptions didn't guide LLMs to use larger display values
  - Parameter type strictness caused UX friction
- **Solution:**
  - Increased ranking fetch limit from 50 to **100 results** (API maximum)
  - Updated `jo` parameter to accept `Union[str, int]` with auto-conversion
  - Added guidance in tool descriptions: **"Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found"**
- **Changes:**
  - All 4 search tools now fetch up to 100 results for ranking
  - All 4 tools with `jo` parameter (`eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`) now accept integers
  - All 7 search tool descriptions updated with display recommendations
- **Impact:**
  - LLMs now find "민법" correctly even with small initial display values
  - No more validation errors when LLMs pass article numbers as integers
  - Better guidance leads to more efficient searches

### v1.0.6 - 2025-11-10
**Enhancement: Improve MCP server quality score (Smithery.ai optimization)**

- **Changes:**
  - Set OC configuration default value to "test" for easier onboarding
  - Added tool annotations to all 15 tools (readOnlyHint=True, destructiveHint=False, idempotentHint=True)
  - Enhanced parameter descriptions in docstrings for all tools
  - Implemented 3 MCP prompts for common use cases
- **Prompts Added:**
  - `search-korean-law`: Search for a Korean law by name and provide a summary
  - `get-law-article`: Retrieve and explain a specific article from a law
  - `search-admin-rules`: Search administrative rules by keyword
- **Impact:** Expected Smithery quality score improvement from 47/100 to ~73/100 (+26 points)
  - Tool annotations: +9pts
  - Parameter descriptions: +12pts
  - MCP prompts: +5pts

### v1.0.5 - 2025-11-10
**Fix: Improve ranking by fetching more results before ranking**

- **Issue:** v1.0.4 ranking was not working properly because it only ranked the limited results returned by the API (e.g., with `display=5`, only 5 alphabetically-ordered results were fetched). If "민법" wasn't in those first 5 results, ranking couldn't help.
- **Root Cause:** Ranking logic was applied AFTER API returned limited results, so relevant matches outside the initial page were never considered.
- **Solution:**
  - When ranking is enabled and `display < 50`, automatically fetch up to 50 results from API
  - Apply ranking to the larger result set (50 results)
  - Trim back to original requested `display` amount after ranking
  - Update `numOfRows` in response to reflect actual number of results returned
- **Implementation:**
  - Updated all 4 search tools: `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`
  - Added `original_display` tracking and `ranking_enabled` flag
  - Fetch 50 results when ranking applies, then trim to requested amount
- **Examples:**
  - User requests `display=5` for query "민법"
  - System fetches 50 results (includes "민법" even if it's not in first 5 alphabetically)
  - Ranking places "민법" first
  - System returns top 5 ranked results (now "민법" appears first)
- **Impact:** Ranking now actually works - exact matches appear first regardless of alphabetical position in API results

### v1.0.4 - 2025-11-10
**Feature: Add relevance ranking to search results**

- **Issue:** law.go.kr API returns results in alphabetical order, causing irrelevant matches to appear first (e.g., searching "민법" returned "난민법" first instead of exact match "민법")
- **Solution:**
  - Added intelligent relevance ranking that prioritizes exact matches over alphabetical ordering
  - Ranking applies automatically to XML responses for keyword searches
  - Results are reordered: exact match → starts with query → contains query → other matches
- **Implementation:**
  - Added `ranking.py` module with `rank_search_results()`, `should_apply_ranking()`, and `detect_query_language()` functions
  - Added `parser.py` module for XML parsing and structured data extraction
  - Updated 4 major search tools: `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`
  - Ranking preserves raw XML while adding `ranked_data` field for LLM consumption
  - Special handling for `elaw_search`: Detects query language (Korean vs English) and ranks by matching name field
- **Examples:**
  - Query "민법" now returns: "민법" (exact) → "민법 시행령" (starts with) → "난민법" (alphabetical)
  - Query "insurance" ranks: "Insurance Act" → "Insurance Business Act" → other matches
- **Impact:** Significantly improves search relevance, reducing LLM confusion and providing better user experience

### v1.0.3 - 2025-11-10
**Fix: Clarify article number format in tool descriptions**

- **Issue:** LLMs misinterpreted the 6-digit article number format (`jo` parameter), generating "000200" for Article 20 (제20조) instead of correct "002000", resulting in wrong article retrieval
- **Root Cause:** Tool descriptions used ambiguous example "000200" for "Article 2", leading LLMs to incorrectly pattern-match Article 20 → "000200"
- **Solution:**
  - Added comprehensive article number format documentation with multiple examples
  - Added `format_article_number()` helper function in `validation.py` for future use
  - Clarified that XXXXXX format = first 4 digits (article number, zero-padded) + last 2 digits (branch article suffix)
- **Changes:**
  - Updated 4 tools: `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`
  - Updated `lnkLsOrdJo_search` which uses separate 4+2 digit format
  - Added clear examples: "000200" (Art. 2), "002000" (Art. 20), "001502" (Art. 15-2)
- **Impact:** LLMs will now correctly format article numbers, preventing queries from returning wrong articles

### v1.0.2 - 2025-11-10
**Fix: Accept both string and integer for id/mst parameters**

- **Issue:** LLMs extract numeric values from XML responses as integers (e.g., `<법령일련번호>188376</법령일련번호>` → `mst=188376`), but tools expected strings, causing Pydantic validation errors
- **Solution:** Changed parameter types to accept both strings and integers with automatic conversion
- **Changes:**
  - Updated 7 tool signatures: `id: Optional[str]` → `id: Optional[Union[str, int]]`
  - Added automatic string conversion at start of each affected tool
  - Applied to: `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`, `elaw_service`, `admrul_service`, `lsDelegated_service`
- **Impact:** LLMs can now pass numeric IDs as integers without validation errors

### v1.0.1 - 2025-11-10
**Fix: Remove JSON format option from all tools**

- **Issue:** LLMs were selecting JSON format, but law.go.kr API does not support JSON despite documentation (returns HTML error pages with "미신청된 목록/본문" message)
- **Solution:** Removed JSON as an option from all 14 tool descriptions
- **Changes:**
  - Updated `type` parameter documentation to explicitly state "JSON not supported by API"
  - Added warning in module docstring about JSON format limitation
  - Tool defaults remain XML (working format)
- **Impact:** Prevents LLMs from requesting JSON format and receiving error pages

### v1.0.0 - 2025-11-10
**Initial Release**

- 15 MCP tools for Korean law information access
- 6 core law APIs (eflaw/law search and retrieval)
- 9 extended APIs (English laws, administrative rules, law-ordinance linkage)
- Session configuration via Context injection
- 100% semantic validation
- Production-ready for Smithery deployment

---

## 한국어 (Korean)

### 미배포 (Unreleased)

#### 유휴 세션 만료
- `LEXLINK_SESSION_IDLE_TTL_SEC`(기본 3600, `0`이면 끔): Streamable HTTP 세션이 해당 시간 동안 활동이 없으면 서버가 세션을 종료(내부 앱에 직접 DELETE)하고 바인딩을 제거해 `LEXLINK_MAX_SESSIONS` 슬롯을 반환(상한 503 이후에도 새 세션 허용). 처리 중인 요청이나 열린 GET 스트림이 있는 세션은 유휴가 아님. 스윕 태스크(간격 min(ttl/4, 60)초, 앱 lifespan과 함께 시작/취소)와 유휴 세션에 요청이 올 때의 지연 만료로 처리. 먼저 `expiring`으로 표시(그동안 요청은 표준 unknown-session 404)하고, 종료가 성공(2xx/404)한 뒤에만 바인딩을 제거하며 실패하면 유지하고 다음 스윕에서 재시도. 만료된 id는 모든 토큰(소유자 포함)에게 바이트 단위로 동일한 unknown-session 404이므로 클라이언트는 새 세션을 엽니다. 인증 없음 모드에서도 동작. SSE 세션은 스트림과 함께 종료. mcp 1.26은 종료된 transport를 세션 테이블에 남기므로 보호된 `_server_instances.pop` 한 곳에서 제거(소유자 DELETE 시에도).

#### 세션 바인딩 보강
- 세션 헤더 없는 모든 Streamable HTTP 요청(메서드/쿼리 무관)은 앱 호출 전에 상한 슬롯을 예약하고(상한 시 503, 동시 요청에도 초과 없음), 응답의 `mcp-session-id`는 항상 바인딩·집계합니다. 생성 응답이 2xx가 아니면 세션을 즉시 종료·해제하며 실패 시 스위퍼가 재시도합니다(TTL 0에서도). 쿼리 `session_id`는 SSE `/messages/` 경로에서만 검사합니다. 서로 다른 세션 id를 여러 개 보내면 unknown-session 404입니다.
- 앱의 404는 더 이상 바인딩/인스턴스를 해제하지 않으며, 종료 확인 또는 소유자 DELETE 2xx 이후에만 해제합니다. 내부 DELETE의 Host는 421/404가 아닌 응답을 받은 요청에서만 저장하고 기본값은 `LEXLINK_ALLOWED_HOSTS` 첫 항목입니다. SSE 타 토큰 404는 mcp와 바이트 단위로 동일합니다(content-type 없음). 종료된 SSE 스트림 id는 모든 토큰에 404. 종료 실패는 세션별 지수 백오프(스윕 간격~15분), 경고는 한 줄(트레이스백/세션 id 없음). 세션 id를 출력하는 mcp 로거 레벨을 올렸습니다.

#### 세션 바인딩
- 순수 ASGI `SessionBindingMiddleware` 추가(순서 Auth > Logging > RateLimit > SessionBinding > app): MCP 세션(Streamable HTTP `mcp-session-id`, SSE `endpoint` 이벤트의 `session_id`)을 만든 토큰에 묶음. 다른 토큰은 존재하지 않는 세션과 같은 404를 받고 앱까지 도달하지 못하며, 소유자 DELETE/SSE 종료 시 바인딩 제거. `LEXLINK_MAX_SESSIONS`(기본 10000) 상한에서는 오래된 항목을 쫓아내지 않고(바인딩 없는 세션이 생기므로) 새 세션을 503으로 거절. 인증 없음 모드는 모든 요청이 같은 id라 효과 없음.

#### HTTP 보강
- 기본 로그에 클라이언트가 제어하는 문자열이 남지 않음: 등록된 도구만 `tool_name`, 스키마에 선언된 인자 키만 기록(나머지는 `unknown_arg_keys` 개수), 알려진 MCP 메서드만 `method`.
- `LEXLINK_LOG_BODIES`가 oc/token/authorization 계열 키를 중첩 구조와 `result` 안에서도 제거.
- `uvicorn.run(..., proxy_headers=False)`, 팩토리 명령에 `--no-proxy-headers`. 웹소켓 스코프는 1008로 종료. `LEXLINK_ALLOWED_ORIGINS`만 설정하면 기동 실패.
- 로그 보존 정리를 기록 스레드 시작 시 실행, 파일 0600/디렉터리 0700, 버려진 로그 개수 집계 및 분당 1회 경고. SSE 전송 시작 경고 및 한계 문서화. DEPLOYMENT_GUIDE 명령에 토큰/호스트/Authorization/Host 헤더 반영.

#### 보안
- HTTP/SSE 모드에 인증 추가 및 fail-closed 적용: `LEXLINK_AUTH_TOKENS="이름:토큰,..."` (Bearer, 상수 시간 비교, 401 + `WWW-Authenticate: Bearer`). 토큰이 없으면 `LEXLINK_ALLOW_NO_AUTH=true`(PlayMCP 인증 없음 등록 전용, 강한 경고 로그)가 아닌 한 기동 시 오류. HTTP 모드에서는 도구의 `oc` 인자를 무시(`params.set_ignore_oc_override`)하며 stdio는 변경 없음.
- 신규 `http_security.py`(순수 ASGI): 토큰별 동시 요청(`LEXLINK_MAX_CONCURRENCY`, 기본 8) 및 분당(`LEXLINK_RATE_LIMIT_PER_MIN`, 기본 60) 제한(429 + `Retry-After`), `LEXLINK_ALLOWED_HOSTS`/`LEXLINK_ALLOWED_ORIGINS` 기반 Host/Origin 검증(DNS 리바인딩 보호는 끄지 않음).
- 트래픽 로그는 기본적으로 개인정보 최소화(인자 키 이름만 기록, 값/결과/토큰 없음; `LEXLINK_LOG_BODIES=true`로 선택 기록, OC 마스킹), 백그라운드 스레드로 기록, `LEXLINK_LOG_RETENTION_DAYS`(기본 30) 보존 정책 적용. `X-Forwarded-For`는 `LEXLINK_TRUSTED_PROXIES`의 피어에서만 신뢰.

#### 변경
- 이미 가져온 내용을 더 이상 자르지 않음: `check_precedent_odds`(판시사항·판결요지 발췌, `key_factors`), `legal_resolver`(`article_text`, `citations`), `chain_full_research`(`representative_cases`), `chain_law_system`(위임 트리 항목·참조)이 기본적으로 전체를 반환. `compact_delegation_tree`는 `max_entries`를 지정하지 않으면 항목 상한이 없음. 예외: `simplify_article`은 업스트림 조회를 최대 20개 법률 용어로 제한(`extract_legal_terms` 상한).
- `SLIM_RESPONSE=true`는 위 압축 상한(500자, 상위 10/3건, 위임 항목 80건)도 함께 유지하므로 PlayMCP 출력은 그대로. 팬아웃 상한과 `display` 제한은 영향 없음.
- 응답 전체를 버퍼링하고 GET 스트림을 멈추게 하며 다중 값 헤더를 잃던 `RawLoggingMiddleware`(BaseHTTPMiddleware)를 모든 메시지를 즉시 전달하는 순수 ASGI `LoggingMiddleware`로 교체. `log_mcp_call`/`log_raw` 제거.
- 모듈 수준 `_server`/`_sse_app`/`app` 제거. `create_app(transport)` 사용(`create_server()` 1회 호출, `uvicorn --factory lexlink.http_server:create_app`, 워커 1개). `create_server(transport_security=None)`가 FastMCP 전송 보안 설정을 받음.
- 한국어 운영 가이드 `docs/OPERATIONS.md` 추가.

#### 수정
- `prec_service` / `detc_service` / `expc_service`: 업스트림이 "일치하는 … 없습니다"로 답하는 경우(존재하지 않는 ID, 또는 국세법령정보시스템 판례처럼 API가 본문을 제공하지 않는 경우) `status: ok` 대신 새 `NOT_FOUND` 오류를 반환. 오류는 캐시되지 않음.
- `prec_service(sections="summary")`에서 판시사항·판결요지가 모두 비어 있으면 판례내용을 포함해 반환(`sections: "summary_fallback"` 및 경고).
- `prec_search`가 국세법령정보시스템 항목에 `본문제공: "API 미제공"`을 표시. `dat_src_nm="대법원"`으로 본문 제공 출처만 검색 가능.
- `sections="summary"` 필터링이 캐시된 전체 응답을 변형하여, 이후 전체 조회가 잘린 본문을 반환하던 문제 수정.
- `check_precedent_odds`가 본문이 없는 판례를 건너뛰고 다음 후보로 넘어가며 `unavailable_cases`를 보고.
- `legal_resolver`의 인용(citations)이 항상 비어 있던 문제 수정(이미 실행 중인 FastMCP 이벤트 루프에서 코루틴 실행 실패 + 오류 은폐 + 잘못된 인용 키 사용). 이제 작업 스레드에서 실행하고 `target_law_name` / `type` 키를 읽으며, 실패 시 `warnings` 목록으로 보고(`chain_full_research`도 전달).
- `lawService.do`의 본문 없는 성공 응답(빈 본문, `{}`, 값이 모두 빈 객체)과 "일치하는 법령이 없습니다"가 `status: ok` 대신 `NOT_FOUND`를 반환. `article_amendment_diff`는 한 버전이 없어도 다른 MST를 계속 조회.
- `elaw_service`, `admrul_search`, `admrul_service`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`, `lsDelegated_service`가 `type`을 전달하여 캐시 키에 응답 형식이 포함됨.
- `check_precedent_odds`가 판례일련번호가 없을 때 검색 행 번호를 대신 쓰지 않음.
- 일반 `NOT_FOUND` 안내가 존재하지 않는 `<target>_search` 도구 이름을 만들지 않음.
- `article_citation`: OC가 있으면 `lawService` 1회 호출(`target=law`, `MST`, 가지번호 포함 `JO`)로 `mst`/`law_name`/조문을 검증. 법령명 불일치는 두 법령명을 담은 `VALIDATION_ERROR`, 조문 없음은 `ARTICLE_NOT_FOUND`, 업스트림 `NOT_FOUND`는 그대로 전달(모두 `success: false`). OC가 없으면 검증을 건너뛰고 `warnings`에 안내. lsiSeq 캐시 키를 `mst` 단독에서 `(mst, law_name)`으로 변경.
- 순위화(100건 over-fetch) 검색에서 2페이지 이상이 비어 있던 문제 수정. `page * display <= 100`이면 상위 100건을 받아 순위화한 뒤 요청 페이지를 잘라 반환(`elaw_search` 포함). 초과하면 순위화를 건너뛰고 `page`/`display`를 그대로 전달하며 `ranking_applied: false` 표시.
- 결과 0건 검색(`run_search`, `elaw_search`)과 빈 `legal_resolver` / `check_precedent_odds` / `chain_dispute_prep` 결과는 `status: ok`를 유지하되 `warning: "no_results"`, `message`, 한국어 `hints`(검색어 축소, 정식 명칭, 해당 도구는 `search=2` 본문 검색)를 추가.
- `extract_outcome`이 일부인용·일부기각·파기환송 등 구체적 결과를 먼저 확인하고 기각/각하/인용/취소는 주문 맥락을 요구. "일부인용"이 "인용"으로, "원심판결 인용"/"인용하지"/"인용된"이 인용으로 잡히지 않고 `불명` 처리. `check_precedent_odds`에 `outcome_note`(휴리스틱이며 인용 가능한 결과 아님) 추가.
- `ordin_search` `knd` docstring 정정: 공식 코드는 30001 조례, 30002 규칙, 30003 훈령, 30004 예규, 30006 기타, 30010 고시, 30011 의회규칙(출처: open.law.go.kr ordinListGuide). 1/2/3은 유효하지 않음.

#### 변경 (동작)
- 검색 응답의 `ranked_data`에서 각 행의 `id`(키가 아닌 업스트림 행 번호 1, 2, 3)를 `rank`로 이름 변경. `raw_content`는 그대로이며, 유지되는 경우 새 `id_note`가 `id`가 행 번호임을 안내. service 호출에는 판례일련번호·법령ID·법령일련번호(MST) 등을 사용.

#### 문서
- `docs/ISSUES.md`에 크기 제어 옵션이 없는 `*_service` 도구를 정리하고, 해당 도구 docstring에 응답이 클 수 있다는 경고를 추가.

#### 보안
- 업스트림 응답 본문(`판례상세링크` 등), 오류 메시지, 디버그/요청 로그에서 OC 인증값을 제거(로그에는 `has_oc` 플래그만 기록). `httpx` 로거는 WARNING 이상으로 제한.
- OC 제거를 값과 무관한 구조 기반으로 확장(숨김 `name="OC"` 폼 필드, `OC = '...'` / `"OC":"..."` 할당). 짧은 값은 따옴표/`=`/`&`로 구분된 경우만 치환. 도구 오류 메시지와 로그도 마스킹(`logger.exception` 제거).

---

### v2.2.0 (2026-10-25)

#### 수정 (P0)
- `cgm_expc_search` / `cgm_expc_service`: 업스트림 target 이름이 뒤집혀 있었음(`cgmExpcMoel` → `moelCgmExpc`). 39개 부처 전부 빈 결과를 반환하던 문제 수정.
- 지식베이스 연계 도구(`lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`)가 `lawService.do`가 아닌 `lawSearch.do`를 호출해 결과가 없던 문제 수정. 이제 `query`/`mst`와 선택 인자 `trm_rlt_cd`를 받으며, `jo_rlt_lstrm_search`는 `jo`가 필수.
- `ordinLsCon_search`가 존재하지 않는 target을 사용하던 문제 수정. `query`→lnkOrd, `law_id`→lnkLsOrd, `org`→lnkOrg 세 가지 모드로 재설계.

#### 수정 (P1)
- `special_decc_search`가 `display`를 무시하고 100건(약 59KB)을 반환하던 문제 수정.
- `jo` 인자가 `35`, `35의5`, `제35조의5`, `003505`를 모두 받아 6자리로 정규화. 조문이 없으면 `ARTICLE_NOT_FOUND` 반환.
- 업스트림 HTML/빈 본문 응답을 `status: ok`로 통과시키지 않고 구조화 오류(`API_NOT_SUBSCRIBED`, `EMPTY_RESPONSE`, `UPSTREAM_HTML_ERROR`)로 반환.
- 리소스 `lexlink://law/{name}`이 URL 디코딩과 약칭(자통법 등) 해석을 수행.
- `serverInfo.version`이 mcp 라이브러리 버전 대신 LexLink 버전을 표시.
- 캐시 키에 응답 형식을 포함(JSON 본문이 XML 요청에 반환되던 문제 수정).
- 부처명 기획재정부 → 재정경제부 변경(기존 이름은 별칭으로 유지). 재정경제부·국세청은 목록 API만 제공.

#### 이번 릴리스에 포함 예정 (병합 중)
- `law_amendment_summary`가 `law_search`의 현행 법령 목록 대신 법령ID로 필터링한 `eflaw_search` 결과로 개정 이력을 구성.
- `simplify_article`, `article_amendment_diff`, `chain_amendment_track`이 제목만이 아니라 신규 `article_text.py`로 항/호/목을 포함한 조문 전문을 추출.
- 시행예정 버전보다 현행 버전을 우선 선택.
- 판례 도구가 본문 검색(`search=2`)으로 폴백.
- 고정된 `date_to="20261231"` 기본값을 현재 연도 말일 계산값으로 교체.

#### 인프라
- 신규 모듈: `agency_codes.py`, `linkage.py`, `article_text.py`
- `tests/` 디렉터리 추적 시작(오프라인 테스트 122개 이상)
- 점검 문서: `docs/AUDIT_CHECKLIST_2026-10-25.md`

---

### v2.1.0 (2026-03-30)

#### 추가
- **지능형 캐싱** (`cache.py`): 의미론적 쿼리 정규화를 포함한 도구별 TTL 캐싱. 검색 결과 1시간, 조문 24시간, AI 검색 30분 캐싱. [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)에서 영감.
- **법령약칭 해석** (`resolver.py`): 한국 법령 약칭 자동 해석 (자통법→자본시장과 금융투자업에 관한 법률). 52개 기본 별칭 + API 응답으로부터 동적 학습. [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)에서 영감.
- **Phase 9: 체인 도구** (5개 신규 도구): 한 번의 호출로 다단계 조사 워크플로 실행. [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)에서 영감.
  - chain_full_research: 완전한 법령 조사 (법령 + 판례 분석 + 해석례)
  - chain_amendment_track: 개정 이력 + 조문별 개정 비교
  - chain_dispute_prep: 4개 데이터베이스에서 모든 판례 조회
  - chain_law_system: 전체 법령 체계 (위임 체계 + 행정규칙 + 자치법규)
  - cache_stats: 캐시 및 법령약칭 해석기 성능 모니터링

#### 인프라
- 신규 모듈: `src/lexlink/cache.py` (~183줄)
- 신규 모듈: `src/lexlink/resolver.py` (~225줄)
- `run_search` 및 `run_service` 헬퍼에 캐싱 통합
- `run_search`에 법령약칭 해석 통합
- 총 도구 수: 54개 (기존 49개)

---

### v2.0.0 - 2026-03-30
**주요 릴리스: Phase 7 도구, JSON 기본 형식, sections 파라미터**

- 18개의 Phase 7 도구 추가 (자치법규, 조약, 법령정보 지식베이스, 위원회 결정문, 중앙부처 해석, 특별행정심판)
- JSON이 기본 응답 형식으로 변경 (기존: XML)
- 판례 서비스 도구에 `sections="summary"` 파라미터 추가
- 공통 로직을 `_helpers.py`로 리팩토링
- 총 도구 수: 44개 (기존 26개)

---

### v1.5.2 - 2026-03-02
**수정: slim_response() 재설계 — 안전 가드 + 필드 제거 폐지**

- **버그 수정 (빈 응답):** `slim_response()`가 `ranked_data` 없이도 `raw_content`를 무조건 제거하여, 랭킹 체인 실패 시 PlayMCP에서 빈 응답 `{status, request_id, upstream_type}` 반환
- **버그 수정 (aiSearch 과대):** `list_keys` 화이트리스트에 `법령조문` 누락, `aiSearch` 필드 필터링이 무시되어 응답 ~46KB 유지
- **재설계:** 모든 필드 필터링 및 트렁케이션 로직 제거. `slim_response()`는 이제 `ranked_data`가 존재할 때만 `raw_content`(중복 raw XML)를 제거
  - **근거:** 실제 API 테스트 결과 검색 도구는 이미 식별자 위주의 소형 데이터 반환 (~5-13KB). 기존 필드 필터링은 이미 작은 응답에서 유용한 필드(사건종류명, 상세링크 등)를 제거하고 있었음
  - 서비스 도구(`_service`)는 `ranked_data`를 설정하지 않으므로 `raw_content` 올바르게 보존 (본문 자체가 응답)
- **aiSearch 기본 display:** 20 → 7로 변경하여 20KB 이내 유지 (조문내용 ~600자/항목 × 7 = ~15KB)
- **검증:** 모든 검색 도구 20KB 미만; 서비스 도구는 전체 텍스트 보존

### v1.5.1 - 2026-03-01
**수정: 안티봇 우회 및 법령ID 내장**

- **안티봇 우회:**
  - law.go.kr가 클라우드 서버 IP(GCP, AWS 등)에서 API 데이터 대신 JavaScript 리다이렉트(`window.location.assign()`) HTML 페이지를 반환하는 문제
  - `client.py`에 JS 리다이렉트를 감지하고 따라가는 `_follow_antibot()` 메서드 추가 (최대 3홉)
  - 두 가지 알려진 JS 패턴을 처리하는 `_parse_antibot_url()` 파서 추가:
    - 패턴 A (문자열 결합): `x={t:'...', h:'...', o:'...'}; return x.t+x.h+x.o`
    - 패턴 B (부분 문자열): `x={o:'...', c:N}; z=M; return o.substr(0,c)+o.substr(c+z)`
  - httpx 클라이언트에 `follow_redirects=True` 활성화 (안티봇 토큰 URL이 HTTP 302 반환)
- **SERVER_INSTRUCTIONS에 법령ID 내장:**
  - MCP 리소스(`lexlink://laws/frequently-used`)가 PlayMCP, Smithery 프록시 클라이언트에서 LLM에 전달되지 않는 문제
  - 20개 검증된 법령ID 매핑을 `SERVER_INSTRUCTIONS`에 직접 내장하여 클라이언트 리소스 지원 여부와 무관하게 LLM이 주요 법령의 검색 단계를 건너뛸 수 있도록 함
  - 모든 20개 ID를 law.go.kr 실시간 API로 검증 (2026-03-01)
- **영향:** 안티봇 보호를 통과하여 API 호출 가능; 모든 MCP 클라이언트에서 주요 법령 조회 지원

### v1.5.0 - 2026-02-28
**리팩토링: Smithery 의존성 제거**

- **제거:** `smithery` 패키지 의존성 및 8개 전이 의존성 (art, rich, typer 등)
- **제거:** `config.py` (`LexLinkConfig` 스키마), `smithery.yaml`
- **단순화:** OC 해석 3단계 (도구 인자 > 세션 설정 > 환경변수) → 2단계 (도구 인자 > 환경변수)
- **단순화:** `create_server()`에서 `session_config` 매개변수 제거
- **단순화:** `http_server.py`에서 `SmitheryFastMCP` 래퍼 해제 불필요
- **추가:** `stdio_server.py` 진입점 (`smithery.cli.start:main` 대체)
- **업데이트:** `_get_client()`가 `LEXLINK_BASE_URL`, `LEXLINK_TIMEOUT` 환경변수 사용
- **스크립트:** `dev`, `start`, `playground` 제거; stdio 전송용 `stdio` 추가
- **영향:** 의존성 트리 정리, 코드베이스 단순화 (26개 도구에서 ~80줄 제거)

### v1.4.0 - 2026-02-28
**기능: MCP 리소스 - 법령 ID 캐시**

- **신규 MCP 리소스:**
  - `lexlink://laws/frequently-used` (정적) - 자주 사용되는 ~20개 한국 법령명과 안정적인 법령ID 매핑 캐시
  - `lexlink://law/{name}` (템플릿) - 한글 법령명 또는 약칭으로 특정 법령의 법령ID 조회
- **구현:**
  - 20개 검증된 법령 항목으로 시드된 인메모리 캐시 (실제 law.go.kr API로 ID 검증)
  - 동적 캐싱: `eflaw_search`와 `law_search`가 검색 후 상위 3개 결과를 자동 캐시
  - 정식명칭과 약칭 모두 검색 가능 (예: "자본시장법" → 자본시장과 금융투자업에 관한 법률)
  - 캐시에 없는 법령은 `eflaw_search` 또는 `law_search` 사용 안내 메시지 반환
- **LLM 선호도 테스트 (100회):**
  - Gemini 2.5 Flash와 Gemini 3 Flash Preview 모두 100% 리소스 채택 (검색 도구 폴백 0%)
  - 템플릿 리소스 선호: 92% (2.5-flash) / 70% (3-flash-preview)
- **기타 변경:**
  - `__init__.py` 버전 수정: `0.1.0` → `1.3.2`
  - `SERVER_INSTRUCTIONS`에 리소스 섹션 및 `article_citation`의 MST 요구사항 추가
- **영향:**
  - 자주 사용되는 법령에 대한 불필요한 `eflaw_search` 호출 제거
  - LLM이 리소스를 통해 법령ID를 직접 조회하여 검색 단계 생략 가능

### v1.3.2 - 2026-01-13
**수정: Smithery 빌드 npm 감지 오류**

- **문제:** Smithery 빌드 시스템이 npm을 패키지 매니저로 잘못 감지하여 "npm error path /home/repo/package.json" 오류 발생
- **원인:** 기존 `smithery.yaml`에 `runtime: python`만 있어 현재 Smithery 빌드 시스템에 부족함
- **해결책:**
  - `smithery.yaml`을 적절한 `startCommand` 설정으로 재작성
  - stdio 기반 MCP 서버 선언을 위해 `type: stdio` 추가
  - Smithery UI에서 선택적 `oc` 파라미터를 위한 `configSchema` 추가
  - `OC` 환경변수와 함께 `uv run start`를 실행하는 `commandFunction` 추가
- **변경된 파일:**
  - `smithery.yaml` - `startCommand` 설정으로 전면 재작성
- **참조:**
  - [perplexity-mcp smithery.yaml](https://github.com/jsonallen/perplexity-mcp/blob/main/smithery.yaml) - 작동하는 Python MCP 예시

### v1.3.1 - 2025-12-25
**기능: PlayMCP 트래픽 로깅**

- **신규 모듈:**
  - `raw_logger.py` - 대시보드 호환 MCP 트래픽 로거
  - `log_processor.py` - 로그 형식 변환 유틸리티
- **구현:**
  - HTTP 서버에 `RawLoggingMiddleware` 추가로 요청/응답 캡처
  - 요청/응답 쌍이 병합된 JSONL 형식
  - `logs/playmcp/YYYY-MM-DD.jsonl` 일별 로그 로테이션
  - SSE 스트리밍 응답 파싱
- **로그 스키마:**
  - `request_id`, `timestamp`, `duration_ms`
  - `method`, `tool`, `arguments`, `result`
  - `status_code`, `client_ip`, `headers`
- **영향:**
  - PlayMCP 배포 환경의 트래픽 분석 가능
  - 모니터링을 위한 대시보드 호환 형식

### v1.3.0 - 2025-12-24
**기능: Phase 5 - AI 기반 검색 도구**

- **신규 도구:**
  - `aiSearch` - AI 기반 의미론적 법령 검색 (도구 25)
  - `aiRltLs_search` - AI 기반 연관법령 검색 (도구 26)
- **구현:**
  - law.go.kr의 지능형 법령검색 시스템 활용
  - 자연어 쿼리를 위한 의미론적 검색
  - 포괄적인 결과를 위한 전체 조문 텍스트(조문내용) 반환
  - LLM 소비를 위한 ranked_data가 포함된 XML 파싱
- **LLM 가이드:**
  - 도구 설명에 ⭐ 우선 사용 도구 힌트 추가
  - 도구 선택 안내를 위한 `tool-selection-guide` MCP 프롬프트 추가
  - 모호하거나 불명확한 쿼리에 우선 사용 도구로 표시
- **영향:**
  - 도구 개수: 24 → 26개
  - MCP 프롬프트: 5 → 6개
  - 자연어 법령 쿼리 처리 개선

### v1.2.9 - 2025-12-09
**수정: API 대소문자 불일치 대응 - 대소문자 무관 키 매칭**

- **문제:** law.go.kr API의 XML 태그 대소문자 불일치
  - `prec` 검색 → `<prec>` (소문자)
  - `detc` 검색 → `<Detc>` (대문자)
  - `expc` 검색 → `<Expc>` (대문자)
- **수정:** `extract_items_list`, `update_items_list`, `slim_response` 대소문자 무관 처리

### v1.2.8 - 2025-12-09
**수정: 비법령 검색의 대소문자 구분 키 추출 오류**

- **문제:** `extract_items_list()`가 대문자 키('Prec', 'Detc', 'Expc', 'Decc') 사용하나 XML 파서는 소문자('prec', 'detc' 등) 출력
- **결과:** `ranked_data` 미설정 → 모든 비법령 검색 빈 응답
- **수정:** 8개 호출 모두 소문자 키로 변경

### v1.2.7 - 2025-12-09
**리팩토링: 패턴 기반 필수 필드 자동 감지**

- **문제:** 데이터 유형별 필드 수동 정의는 새 API 추가 시 유지보수 필요
- **해결책:** 정규식 패턴 매칭으로 필수 필드 자동 감지
- **패턴:** `*일련번호` (ID), `*명한글/*명` (이름), `*일자` (날짜) 등
- **장점:** 새 데이터 유형도 수동 정의 없이 자동 작동

### v1.2.6 - 2025-12-09
**수정: 데이터 유형별 필수 필드 분리**

- **문제:** `slim_response()`가 모든 데이터 유형에 법령 전용 필드명 사용
  - 판례 검색(`prec_search`)이 빈 결과 반환
  - `판례일련번호`, `사건명` 등 필드가 법령 필드와 맞지 않아 필터링됨
- **해결책:**
  - `essential_fields_by_type` 딕셔너리로 데이터 유형별 필드 정의
  - 각 API 유형(law, prec, detc, expc, decc, admrul, elaw)별 필수 필드 지정

### v1.2.5 - 2025-12-09
**수정: 올바른 파라미터 사용을 위한 법령ID 필드 추가**

- **문제:** LLM이 슬림 응답에서 `법령일련번호` (MST)와 `법령ID`를 혼동
  - 예시: MST인 235555를 `eflaw_service(id="235555")`로 호출 (잘못된 사용)
  - 올바른 사용: `eflaw_service(mst=235555)` 또는 `eflaw_service(id="001624")`
- **해결책:**
  - `slim_response()`의 `essential_fields`에 `법령ID` 추가
  - LLM이 두 필드를 모두 확인하고 올바른 파라미터 사용 가능
- **필수 필드:** 법령명한글, 법령일련번호, **법령ID**, 현행연혁코드, 시행일자
- **참고:** 랭킹이 작동하지 않으면 EC2에 최신 코드 배포 필요

### v1.2.4 - 2025-12-09
**수정: PlayMCP용 슬림 응답 모드**

- **문제:** v1.2.3의 트렁케이션 방식은 `ranked_data`에 여전히 전체 데이터가 포함되어 있어 부족함 (50개 결과당 ~25KB)
- **해결책:**
  - `truncate_response()`를 `slim_response()` 함수로 대체
  - `SLIM_RESPONSE=true` 설정 시: `raw_content` 완전 제거 및 `ranked_data`에서 필수 필드만 유지
  - 유지 필드: 법령명한글, 법령일련번호, 현행연혁코드, 시행일자
  - 제거 필드: 법령약칭명, 공포일자, 공포번호, 제개정구분명, 소관부처코드, 소관부처명, 법령구분명, 공동부령정보, 자법타법여부, 법령상세링크
- **설정:**
  - Smithery: 변경 불필요 (전체 응답)
  - PlayMCP: systemd 서비스에 `SLIM_RESPONSE=true` 설정
- **영향:**
  - 응답 크기 50개 결과 기준 ~50KB에서 ~3-5KB로 감소
  - PlayMCP에서 크기 오류 없이 안정적으로 작동

### v1.2.3 - 2025-12-08
**수정: PlayMCP 응답 크기 제한 대응**

- **문제:** PlayMCP가 응답 크기 제한(~50KB)이 있어 "Tool call returned too large content part" 오류 발생
- **해결책:**
  - 선택적 응답 크기 제한을 위한 `truncate_response()` 헬퍼 함수 추가
  - 11개 검색 도구 모두에 트렁케이션 적용 (eflaw_search, law_search, elaw_search, admrul_search, lnkLs_search, lnkLsOrdJo_search, lnkDep_search, prec_search, detc_search, expc_search, decc_search)
  - `MAX_RESPONSE_SIZE` 환경 변수 추가 (설정 시에만 트렁케이션 적용)
- **설정:**
  - Smithery: 변경 불필요 (크기 제한 없음)
  - PlayMCP: systemd 서비스에 `MAX_RESPONSE_SIZE=50000` 설정
- **영향:**
  - Smithery는 전체 기능 유지 (무제한 응답)
  - PlayMCP는 한글 안내 메시지와 함께 트렁케이션된 응답으로 크기 오류 방지

### v1.2.2 - 2025-12-06
**기능: Kakao PlayMCP용 HTTP/SSE 서버**

- **신규 기능:**
  - Kakao PlayMCP 배포를 위한 HTTP/SSE 서버 지원 추가
  - HTTP 서버 시작을 위한 `uv run serve` 명령어 추가
  - HTTP 헤더에서 OC를 추출하는 OCHeaderMiddleware (Key/Token 인증)
  - SSE (`/sse`) 및 Streamable HTTP (`/mcp`) 전송 방식 지원
- **주요 변경사항:**
  - `LAW_OC` 환경 변수를 `OC`로 변경 (공식 law.go.kr API 명명과 일치)
- **설정 변경:**
  - Smithery UI 설정에서 `base_url` 제거 (내부 필드로만 유지)
  - 기본 타임아웃을 15초에서 60초로 변경
  - 타임아웃 범위를 5-120초로 확장
- **문서:**
  - Kakao PlayMCP 배포 가이드 추가 (`docs/DEPLOYMENT_GUIDE.md`)
  - README에 PlayMCP 배포 섹션 추가
  - 프로젝트 구조에 `http_server.py` 추가
- **영향:**
  - LexLink를 Kakao PlayMCP 및 유사한 HTTP 기반 플랫폼에 배포 가능
  - 각 PlayMCP 사용자가 HTTP 헤더를 통해 자신의 OC를 제공 (자체 API 할당량 사용)

### v1.2.1 - 2025-11-30
**수정: 특정 조문 조회를 위한 LLM 가이드 개선**

- **문제:** LLM이 "제174조" 같은 특정 조문 요청 시 `jo` 매개변수를 사용하지 않고 전체 법령(자본시장법의 경우 1MB 이상)을 가져옴
- **해결책:**
  - `eflaw_service`와 `law_service` 문서에 `jo` 매개변수 사용에 대한 **중요** 안내 추가
  - `eflaw_josub`와 `law_josub` 문서에 **최적화된 도구** 안내 추가
  - 실용적인 예시 추가: 제174조는 `jo="017400"`, 제3조는 `jo="000300"`
  - 큰 응답 크기(400개 이상 조문, 1MB 이상)에 대한 경고 추가
- **영향:**
  - LLM이 이제 특정 조문 조회 시 `jo` 매개변수를 올바르게 사용
  - LLM이 조문 조회 시 `law_josub`/`eflaw_josub`를 선호
  - 특정 조문 요청에 대해 더 빠른 응답과 깔끔한 출력

### v1.2.0 - 2025-11-30
**기능: Phase 4 - 조문 인용 추출**

- **신규 도구:**
  - `article_citation` - 법령 조문에서 인용된 법률 추출 (도구 24)
- **구현:**
  - HTML 파싱 방식으로 100% 정확도 (LLM 환각 위험 없음)
  - CSS 클래스 기반 인용 유형 감지 (sfon1-4 클래스)
  - XML API와 HTML 페이지 간 MST ↔ lsiSeq ID 매핑
  - 외부 API 비용 없음 (LLM 호출 불필요)
  - 평균 추출 시간 ~350ms
- **기능:**
  - 내부 인용과 외부 인용 구분
  - 조문, 항, 호목 참조 추출
  - 중복 인용 통합 및 인용 횟수 집계
  - 맥락 파악을 위한 원문 인용 텍스트 보존
- **MCP 프롬프트 추가:**
  - `extract-law-citations` - 법령 조문에서 인용 추출 및 설명
  - `analyze-citation-network` - 법령의 인용 네트워크 분석
- **테스트 커버리지:**
  - 단위 테스트: 인용 모듈 100% 커버리지
  - 통합 테스트: 엔드투엔드 추출 검증
  - LLM 워크플로우 테스트: Gemini 2.0 Flash 검증
- **알려진 제한사항:**
  - 범위 참조(예: "제88조 내지 제93조")는 첫 번째 조문만 반환
  - 외부 법령명은 MST 조회를 위해 별도 검색 필요
- **영향:**
  - 도구 개수: 23 → 24개
  - MCP 프롬프트: 3 → 5개
  - 인용 네트워크 분석 워크플로우 지원

### v1.1.0 - 2025-11-14
**기능: Phase 3 - 판례 및 법령연구 API**

- **변경사항:**
  - 판례 및 법령연구를 위한 8개 신규 도구 추가 (15 → 23 도구)
  - `prec_search`, `prec_service` - 법원 판례 (판례)
  - `detc_search`, `detc_service` - 헌법재판소 결정례 (헌재결정례)
  - `expc_search`, `expc_service` - 법령해석례 (법령해석례)
  - `decc_search`, `decc_service` - 행정심판 재결례 (행정심판례)
- **구현:**
  - 모든 XML 태그와 호환되는 범용 파서 함수 추가 (`extract_items_list`, `update_items_list`)
  - 13개 Phase 3 매개변수 추가: `prnc_yd`, `dat_src_nm`, `ed_yd`, `reg_yd`, `expl_yd`, `dpa_yd`, `rsl_yd`, `curt`, `inq`, `rpl`, `itmno`, `cls`
  - 모든 순위 지정 및 검증 함수가 Phase 3 도구와 호환
  - 기존 Phase 1 & 2 도구에 대한 하위 호환성 완벽 유지
- **영향:**
  - 도구 개수 53% 증가 (15 → 23 도구)
  - API 커버리지 ~10%에서 ~15%로 증가
  - 법령연구 카테고리 133% 확장 (3 → 7 카테고리)
  - 모든 23개 도구 검증 완료 및 프로덕션 준비 완료

### v1.0.8 - 2025-11-13
**수정: 모든 도구에서 매개변수 타입 일관성 완성**

- **문제:** v1.0.2에서 7개 도구를 수정했지만 2개 추가 도구(`eflaw_josub`, `law_josub`)를 누락하여 동일한 매개변수가 도구마다 다른 타입을 가지는 불일치 발생
- **해결책:**
  - `eflaw_josub`, `law_josub`, `lnkLsOrdJo_search` 수정으로 `Union[str, int]` 허용
- **영향:** 100% 매개변수 타입 일관성 달성

### v1.0.7 - 2025-11-10
**수정: 검색 안정성 및 LLM 가이드 개선**

- 순위 지정 가져오기 제한을 50에서 100개로 증가
- `jo` 매개변수가 `Union[str, int]` 허용으로 자동 변환
- 도구 설명에 display 권장 사항 추가

### v1.0.6 - 2025-11-10
**개선: MCP 서버 품질 점수 향상 (Smithery.ai 최적화)**

- OC 설정 기본값을 "test"로 설정
- 모든 15개 도구에 도구 주석 추가
- 3개 MCP 프롬프트 구현: `search-korean-law`, `get-law-article`, `search-admin-rules`
- Smithery 품질 점수 47/100 → ~73/100 예상

### v1.0.5 - 2025-11-10
**수정: 순위 지정 전 더 많은 결과 가져오기로 순위 개선**

- 순위 활성화 시 `display < 50`이면 API에서 최대 50개 자동 가져오기
- 4개 검색 도구 모두 업데이트

### v1.0.4 - 2025-11-10
**기능: 검색 결과에 관련성 순위 추가**

- `ranking.py`, `parser.py` 모듈 추가
- 결과 재정렬: 정확한 일치 → 시작 일치 → 포함 → 기타

### v1.0.3 - 2025-11-10
**수정: 도구 설명에서 조문 번호 형식 명확화**

- XXXXXX = 앞 4자리(조문 번호) + 뒤 2자리(가지조문)
- 예시: "000200" (제2조), "002000" (제20조), "001502" (제15조의2)

### v1.0.2 - 2025-11-10
**수정: id/mst 매개변수에 문자열과 정수 모두 허용**

- 7개 도구 서명을 `Optional[Union[str, int]]`로 업데이트

### v1.0.1 - 2025-11-10
**수정: 모든 도구에서 JSON 형식 옵션 제거**

- law.go.kr API가 JSON을 지원하지 않음 (문서와 다름)
- 14개 도구 설명에서 JSON 옵션 제거

### v1.0.0 - 2025-11-10
**최초 릴리스**

- 한국 법령 정보 접근을 위한 15개 MCP 도구
- 6개 핵심 법령 API + 9개 확장 API
- Context 주입을 통한 세션 설정
- 100% 의미론적 검증
- Smithery 배포 준비 완료
