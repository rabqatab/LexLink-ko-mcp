# AGENTS.md

LexLink is a Model Context Protocol (MCP) server providing structured access to 191+ Korean law APIs from the National Law Information Center (law.go.kr). It exposes 26 tools, 6 prompts, and 2 resources for AI-powered legal research.

## Architecture

```
src/lexlink/
├── server.py        # MCP server: 26 tools + 6 prompts + 2 resources (~3,400 lines)
├── client.py        # HTTP client for law.go.kr API (with anti-bot bypass)
├── stdio_server.py  # Stdio transport entry point
├── params.py        # Parameter mapping (snake_case → upstream camelCase)
├── parser.py        # XML response parsing
├── validation.py    # Input validation (dates, article codes)
├── errors.py        # Structured error responses with hints
├── citation.py      # HTML-based citation extraction (BeautifulSoup)
├── ranking.py       # Relevance ranking for search results
├── http_server.py   # HTTP/SSE transport for PlayMCP deployment
├── raw_logger.py    # MCP traffic logging (JSONL)
└── log_processor.py # Log analysis for dashboard
```

## Tools (26 total)

| Phase | Tools | Purpose |
|-------|-------|---------|
| Phase 1 (6) | `eflaw_search`, `law_search`, `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub` | Core law search and retrieval |
| Phase 2 (9) | `elaw_search`, `elaw_service`, `admrul_search`, `admrul_service`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`, `drlaw_search`, `lsDelegated_service` | English laws, admin rules, law-ordinance linkage |
| Phase 3 (8) | `prec_search`, `prec_service`, `detc_search`, `detc_service`, `expc_search`, `expc_service`, `decc_search`, `decc_service` | Case law, constitutional court, legal interpretations, admin appeals |
| Phase 4 (1) | `article_citation` | HTML-based citation extraction (zero API cost, 100% accuracy) |
| Phase 5 (2) | `aiSearch`, `aiRltLs_search` | AI-powered semantic search |

## MCP Prompts (6 total)

1. `search-korean-law` - Search for a law by name
2. `get-law-article` - Retrieve and explain a specific article
3. `get-article-with-citations` - Article + all its citations
4. `analyze-law-citations` - Multi-article citation analysis
5. `search-admin-rules` - Search administrative rules
6. `tool-selection-guide` - Which search tool to use (vague vs specific)

## MCP Resources (2 total)

1. `lexlink://laws/frequently-used` (static) - Cached mapping of ~20 frequently-used law names to 법령ID codes
2. `lexlink://law/{name}` (template) - Look up a specific law's 법령ID by Korean name or abbreviation

## Key Patterns

- **OC parameter resolution**: Tool arg > Environment variable
- **XML-only responses**: law.go.kr JSON format is broken; all tools default to XML
- **SLIM_RESPONSE mode**: `SLIM_RESPONSE=true` env var strips raw XML for size-constrained platforms (PlayMCP 24KB limit)
- **Anti-bot bypass**: `client.py` detects and follows law.go.kr JS anti-bot redirects (2 patterns: string concat, substring slicing)
- **Auto-ranking**: Search tools auto-fetch 100 results and re-rank by relevance for keyword queries
- **Embedded law IDs**: `SERVER_INSTRUCTIONS` contains 20 common 법령ID mappings for clients that don't support MCP resources
- **Context injection**: `ctx: Context` parameter on every tool for MCP logging/progress

## Deployment

- **Kakao PlayMCP**: HTTP/SSE transport via `http_server.py`, `TRANSPORT=http`
- **Stdio**: `uv run stdio` for local MCP clients (Claude Code, Cursor, etc.)

## Testing

Run tests with `uv run pytest`. Test suites cover:
- E2E with Gemini LLM
- Citation unit tests (25) and integration tests (15)
- Semantic data quality validation across all 26 tools

## Coding Conventions

- All tool functions use `@server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))`
- Parameters use snake_case, mapped to upstream camelCase via `params.py`
- Error responses follow structured format: `{status, error_code, message, hints, request_id}`
- Article numbers use `XXXXXX` zero-padded format (e.g., article 3 = `000003`)
- Korean date ranges use `YYYYMMDD~YYYYMMDD` format
