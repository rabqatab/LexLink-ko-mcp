# AGENTS.md

LexLink is a Model Context Protocol (MCP) server providing structured access to 191+ Korean law APIs from the National Law Information Center (law.go.kr). It exposes 55 tools, 9 prompts, and 2 resources for AI-powered legal research.

## Architecture

```
src/lexlink/
├── server.py        # MCP server: 55 tools + 9 prompts + 2 resources
├── _helpers.py      # Shared helpers: TOOL_ANNOTATIONS, handle_tool_error, run_search, run_service
├── cache.py         # Intelligent per-tool TTL caching (~183 lines) — inspired by korean-law-mcp
├── resolver.py      # Korean law name/abbreviation resolution (~225 lines) — inspired by korean-law-mcp
├── client.py        # HTTP client for law.go.kr API (anti-bot bypass + structured upstream error detection)
├── stdio_server.py  # Stdio transport entry point
├── params.py        # Parameter mapping (snake_case → upstream camelCase)
├── parser.py        # XML response parsing
├── validation.py    # Input validation (dates, article codes, `jo` normalization)
├── agency_codes.py # Ministry/tribunal code tables + aliases (MINISTRY_CODES, MINISTRY_ALIASES, MINISTRIES_LIST_ONLY, TRIBUNAL_CODES), cgm_expc_target(), special_decc_target(), resolve_ministry(), enforce_display()
├── linkage.py       # Knowledge-base/ordinance-link pure logic: normalize_jo_code, validate_trm_rlt_cd, require_query_or_mst, select_ordin_link_mode, attach_parsed_data, TRM_RLT_CODES, ORDIN_LINK_MODES
├── article_text.py  # Article text extraction (조문내용 + 항/호/목 flattening)
├── errors.py        # Structured error responses with hints (ErrorCode)
├── citation.py      # HTML-based citation extraction (BeautifulSoup)
├── ranking.py       # Relevance ranking for search results
├── http_server.py   # HTTP/SSE transport for PlayMCP deployment
├── http_security.py # HTTP auth / rate limit / host validation (pure ASGI)
├── raw_logger.py    # MCP traffic logging (JSONL, async writer)
└── log_processor.py # Log analysis for dashboard

tests/               # 122 offline tests (tracked in git): test_cache, test_cgm_expc, test_client_errors, test_knowledge_base, test_ordin_link, test_resources, test_special_decc, test_validation_jo
```

`__version__` (`src/lexlink/__init__.py`) is read from package metadata and reported as MCP `serverInfo.version` (current release: v2.2.0).

## Tools (55 total)

| Phase | Tools | Purpose |
|-------|-------|---------|
| Phase 1 (6) | `eflaw_search`, `law_search`, `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub` | Core law search and retrieval |
| Phase 2 (9) | `elaw_search`, `elaw_service`, `admrul_search`, `admrul_service`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`, `drlaw_search`, `lsDelegated_service` | English laws, admin rules, law-ordinance linkage |
| Phase 3 (8) | `prec_search`, `prec_service`, `detc_search`, `detc_service`, `expc_search`, `expc_service`, `decc_search`, `decc_service` | Case law, constitutional court, legal interpretations, admin appeals |
| Phase 4 (1) | `article_citation` | HTML-based citation extraction (zero API cost, 100% accuracy) |
| Phase 5 (2) | `aiSearch`, `aiRltLs_search` | AI-powered semantic search |
| Phase 7 (18) | `ordin_search`, `ordin_service`, `ordinLsCon_search`, `trty_search`, `trty_service`, `lstrm_ai_search`, `dlytrm_search`, `lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`, `ls_rlt_search`, `committee_search`, `committee_service`, `cgm_expc_search`, `cgm_expc_service`, `special_decc_search`, `special_decc_service` | Local ordinances, treaties, legal terms KB, committee decisions, ministry interpretations, special appeals |
| Phase 8 (5) | `check_precedent_odds`, `legal_resolver`, `simplify_article`, `law_amendment_summary`, `article_amendment_diff` | AI-powered legal reasoning tools |
| Phase 9 (5) | `chain_full_research`, `chain_amendment_track`, `chain_dispute_prep`, `chain_law_system`, `cache_stats` | Multi-step research chain tools + cache monitoring. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp) |

## MCP Prompts (9 total)

1. `search-korean-law` - Search for a law by name
2. `get-law-article` - Retrieve and explain a specific article
3. `get-article-with-citations` - Article + all its citations
4. `analyze-law-citations` - Multi-article citation analysis
5. `search-admin-rules` - Search administrative rules
6. `tool-selection-guide` - Which search tool to use (vague vs specific)
7. `legal-reasoning-guide` - Guide for AI-powered legal reasoning tools (Phase 8)
8. `precedent-analysis` - Analyze precedent patterns for a legal question
9. `dispute-resolution` - Guide through legal dispute resolution paths

## MCP Resources (2 total)

1. `lexlink://laws/frequently-used` (static) - Cached mapping of ~20 frequently-used law names to 법령ID codes
2. `lexlink://law/{name}` (resource template; `{name}` is a placeholder, read e.g. `lexlink://law/자통법` without braces) - Look up a specific law's 법령ID by Korean name or abbreviation. The name is URL-decoded, resolver aliases are consulted (e.g. 자통법 → 자본시장과 금융투자업에 관한 법률, `010513`), and one live `law_search` exact-name lookup is the fallback

## Key Patterns

- **OC parameter resolution**: Tool arg > Environment variable
- **JSON by default**: Since v2.0.0 all tools default to `type="JSON"`; `XML`/`HTML` are opt-in. The cache key includes the response format, so a JSON body is never served to an XML request
- **SLIM_RESPONSE mode**: `SLIM_RESPONSE=true` env var removes redundant `raw_content` XML when `ranked_data` exists. Also keeps the compact caps via `compact_limit()` (500-char excerpts, top-10/3 lists, 80 delegation entries; unset = no cap). Does NOT filter fields — search tools already return slim data from API. Service tools without `ranked_data` keep `raw_content` as safety fallback
- **Anti-bot bypass**: `client.py` detects and follows law.go.kr JS anti-bot redirects (2 patterns: string concat, substring slicing)
- **Auto-ranking**: Search tools auto-fetch 100 results and re-rank by relevance for keyword queries
- **Embedded law IDs**: `SERVER_INSTRUCTIONS` contains 20 common 법령ID mappings for clients that don't support MCP resources
- **Context injection**: `ctx: Context` parameter on every tool for MCP logging/progress
- **Intelligent caching** (`cache.py`): Per-tool TTL caching integrated into `run_search` and `run_service`. TTLs: search 1hr, articles 24hr, AI search 30min. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)
- **`jo` normalization** (`validation.py`): `eflaw_josub`, `law_josub`, `eflaw_service`, `law_service` accept `35`, `"35의5"`, `"제35조의5"`, `"35-5"`, `"003505"` and normalize to the 6-digit code. Invalid → `VALIDATION_ERROR`; article absent from the response → `ARTICLE_NOT_FOUND`
- **Structured upstream error detection** (`client.py`): 0-byte body → `EMPTY_RESPONSE`; "미신청된 목록/본문에 대한 접근입니다" page → `API_NOT_SUBSCRIBED` (hint: apply for the API at open.law.go.kr; for target `eflaw` suggests `law_service`/`eflaw_josub`); other HTML/error500 pages when JSON/XML was requested → `UPSTREAM_HTML_ERROR`; auth failure → `UPSTREAM_ERROR`
- **Ministry interpretations** (`cgm_expc_*`): upstream target is `{code}CgmExpc` (e.g. `moelCgmExpc`), 39 ministries via `agency_codes.py`. 기획재정부 was renamed 재정경제부 (code `Moef`; old name, 환경부, 산업통상자원부, 여성가족부, 통계청, 특허청, 문화재청 accepted as aliases). 재정경제부 and 국세청 have a list API only: `cgm_expc_service` returns `VALIDATION_ERROR` for them
- **`display` enforcement**: `special_decc_search` honors `display` (no longer leaks the 100-row over-fetch)
- **Knowledge-base linkage** (`linkage.py`): `lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search` call `lawService.do`. Take `query` or `mst` (term serial no.), optional `trm_rlt_cd` (140301 동의어, 140302 반의어, 140303 상위어, 140304 하위어, 140305 연관어; Korean names accepted) where upstream supports it. `jo_rlt_lstrm_search` requires `jo` and takes `query` (law name) or `law_id`. `display`/`page` are not upstream params for these tools
- **Ordinance linkage** (`ordinLsCon_search`): exactly one of `query` (→ `lnkOrd`, ordinance-name search), `law_id` (→ `lnkLsOrd`, upstream `knd`), `org` (→ `lnkOrg`, local-government code); optional `sort`, `display`, `page`. The old `ordinLsCon` target never existed upstream
- **Law name resolution** (`resolver.py`): Auto-resolves Korean law abbreviations before API calls in `run_search`. 52 seed aliases + dynamic learning from API responses. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)

## Deployment

- **Kakao PlayMCP**: HTTP/SSE transport via `http_server.py`, `TRANSPORT=http`
- **Stdio**: `uv run stdio` for local MCP clients (Claude Code, Cursor, etc.)

## Testing

Run tests with `uv run pytest tests/` (122 offline tests, no network/OC needed). `tests/` is tracked in git. Files:
- `test_cache.py` - cache behavior (incl. format-aware cache key)
- `test_cgm_expc.py` - ministry codes, aliases, list-only ministries
- `test_client_errors.py` - upstream body error detection (`EMPTY_RESPONSE`, `API_NOT_SUBSCRIBED`, `UPSTREAM_HTML_ERROR`)
- `test_knowledge_base.py` - term/article linkage params (`trm_rlt_cd`, `jo`)
- `test_ordin_link.py` - `ordinLsCon_search` mode selection
- `test_resources.py` - `lexlink://law/{name}` resolution
- `test_special_decc.py` - `special_decc_search` `display` handling
- `test_validation_jo.py` - `jo` normalization

## Coding Conventions

- All tool functions use `@server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))`
- Parameters use snake_case, mapped to upstream camelCase via `params.py`
- Error responses follow structured format: `{status, error_code, message, hints, request_id}`. Codes: `VALIDATION_ERROR`, `TIMEOUT`, `UPSTREAM_ERROR`, `INTERNAL_ERROR`, `API_NOT_SUBSCRIBED`, `UPSTREAM_HTML_ERROR`, `EMPTY_RESPONSE`, `ARTICLE_NOT_FOUND`
- Article numbers use `XXXXXX` zero-padded format (e.g., article 3 = `000003`)
- Korean date ranges use `YYYYMMDD~YYYYMMDD` format
