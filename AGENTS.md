# AGENTS.md

LexLink is a Model Context Protocol (MCP) server over the Korean National Law Information API (law.go.kr DRF). It exposes 55 tools, 9 prompts and 2 resources. Version: v2.2.0 plus the Unreleased section of CHANGELOG.md (`__version__` is read from package metadata and reported as MCP `serverInfo.version`).

Do not trust counts or lists in docs, including this file. Generate them from the server:

```bash
uv run python -c "import asyncio; from lexlink.server import create_server; t=asyncio.run(create_server().list_tools()); print(len(t), sorted(x.name for x in t))"
```

The full tool list with arguments is in [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Docs map

| File | Use |
|---|---|
| [README.md](README.md) / [README_kr.md](README_kr.md) | What it is, quick start (keep the two in sync) |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Tool arguments, upstream API catalog, limitations |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | HTTP server deploy, auth, logging (Korean) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Code layout, tests, adding tools |
| [docs/archive/](docs/archive/) | Historical only (roadmap, old status, issue tracker, audit) |
| [CHANGELOG.md](CHANGELOG.md) | English + Korean sections; do not edit released history |

## Code layout (`src/lexlink/`)

- `server.py`: `create_server()` with all tools, prompts, resources and `SERVER_INSTRUCTIONS`. Wraps `server.tool` so every result passes the `SLIM_RESPONSE` size guard.
- `_helpers.py`: `TOOL_ANNOTATIONS`, `handle_tool_error`, `run_search`, `run_service`, SLIM helpers.
- `client.py`: HTTP client (follows law.go.kr JS anti-bot redirects, detects empty/unsubscribed/HTML upstream bodies).
- `params.py`, `validation.py`, `linkage.py`, `agency_codes.py`, `as_of.py`, `article_text.py`, `citation.py`, `parser.py`, `ranking.py`, `cache.py`, `resolver.py`, `errors.py`.
- `stdio_server.py` (`uv run stdio`), `http_server.py` (`uv run serve`), `http_security.py` (auth, rate limit, session binding, Host/Origin), `raw_logger.py`, `log_processor.py`.

One line per module is in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Prompts and resources

Prompts (9): `search-korean-law`, `get-law-article`, `get-article-with-citations`, `analyze-law-citations`, `search-admin-rules`, `tool-selection-guide`, `analyze-legal-situation`, `explain-legal-document`, `check-legal-precedent`.

Resources (2): `lexlink://laws/frequently-used` (static, about 20 law names to 법령ID) and the template `lexlink://law/{name}` (`{name}` is a placeholder; read e.g. `lexlink://law/자통법`). The name is URL-decoded, resolver aliases are applied, and one live `law_search` exact-name lookup is the fallback. `SERVER_INSTRUCTIONS` embeds 20 common 법령ID mappings for clients without resource support.

## Behaviour to know

- **OC**: tool arg `oc`, then env `OC`. In HTTP mode `oc` is ignored and the server `OC` is always used. Never write a real OC in files; use `<OC>`. The server does not load `.env` itself.
- **Transports**: `uv run stdio`; `uv run serve` with `TRANSPORT=http` (Streamable HTTP, `/mcp`, recommended) or `sse` (default, `/sse`). HTTP mode needs `LEXLINK_AUTH_TOKENS` or `LEXLINK_ALLOW_NO_AUTH=true`, otherwise startup raises. Env table: [docs/OPERATIONS.md](docs/OPERATIONS.md).
- **JSON by default**; `XML`/`HTML` opt-in. The cache key includes the response type.
- **No truncation by default**: results keep everything already fetched. `SLIM_RESPONSE=true` (also `1`, `yes`, `on`) drops `raw_content` when `ranked_data` exists, keeps compact caps (500-char excerpts, top-10/3 lists, 80 delegation entries) and trims any result over 20,000 bytes (`truncated`, `truncated_notes`). `simplify_article` looks up at most 20 legal terms either way.
- **`jo`** accepts `35`, `"35의5"`, `"제35조의5"`, `"35-5"`, `"003505"` (normalized to 6 digits). Invalid: `VALIDATION_ERROR`; absent from response: `ARTICLE_NOT_FOUND`.
- **`ef_yd`** (service tools): selects a revision of one MST. `id` + `ef_yd` without `mst` is `VALIDATION_ERROR`; `mst` needs `ef_yd` or `id`. For "law as of date D" use `law_as_of`.
- **`law_as_of`**: `in_force` true/false/null; false reasons `BEFORE_FIRST_ENFORCEMENT`, `BEFORE_EARLIEST_AVAILABLE_VERSION`, `AFTER_REPEAL`; null is `NOT_CURRENT_UPSTREAM`. Upstream failures are errors, never "not found".
- **`simplify_article`** does not rewrite text: `simplified_text` equals `original_text`; it adds a `term_glossary` of database synonym links.
- **`check_precedent_odds`** classifies the 주문 (disposition) only; labels include 파기환송, 상고기각, 일부인용, 인용, 기각, 각하, 불명. It is a distribution, not a win rate.
- **`chain_law_system`**: `admin_rules` is `{name, id, article}` from the 위임행정규칙 entries; `linked_ordinances` comes from `lnkLsOrd`; failures go to `warnings`.
- **Zero results** return `status: ok` with `warning: "no_results"` and hints. `*_service` tools return `NOT_FOUND` for "일치하는 … 없습니다".
- **Unknown tool arguments are silently ignored** (verified).
- **Ministry interpretations** (`cgm_expc_*`): upstream target `{code}CgmExpc`, 39 ministries. 재정경제부 and 국세청 are list-only, so `cgm_expc_service` returns `VALIDATION_ERROR` for them.
- **`ordinLsCon_search`**: exactly one of `query`, `law_id`, `org`.
- **Knowledge-base linkage** tools use `lawService.do`; `display`/`page` are not upstream parameters for them.
- **Search ranking**: `run_search` over-fetches up to 100 rows to re-rank keyword queries, then returns the requested page.
- **Error shape**: `{status, error_code, message, hints, request_id}`. Codes: `VALIDATION_ERROR`, `TIMEOUT`, `UPSTREAM_ERROR`, `INTERNAL_ERROR`, `NOT_FOUND`, `ARTICLE_NOT_FOUND`, `EMPTY_RESPONSE`, `API_NOT_SUBSCRIBED`, `UPSTREAM_HTML_ERROR`.

## Testing

`uv run pytest tests/` runs the offline tests (mocked upstream, no network or OC). Fixtures are in `tests/fixtures/`. Markers: `unit`, `integration`, `e2e`, `critical`, `slow`.

## Conventions

- Tools use `@server.tool(annotations=TOOL_ANNOTATIONS)` (read-only, idempotent) and `ctx: Context = None`.
- Arguments are snake_case; `params.py` maps them to upstream camelCase.
- Article numbers are 6 digits (`000003` = 제3조). Date ranges are `YYYYMMDD~YYYYMMDD`.
- A change that touches a tool's behaviour needs a line under Unreleased in CHANGELOG.md (English and Korean) and an update of the affected doc.
