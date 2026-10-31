# Development guide

For contributors and coding agents. Agent-specific notes are in [AGENTS.md](../AGENTS.md).

## Setup

```bash
uv sync                      # Python 3.10+, installs the dev group (pytest)
uv run pytest tests/         # offline tests, no network or OC needed
uv run pytest -m unit        # markers: unit, integration, e2e, critical, slow
OC=<OC> uv run stdio         # run the server over stdio
```

Tests mock the upstream API (fixtures in `tests/fixtures/`). There is no coverage plugin in the dev group.

## Code layout (`src/lexlink/`)

| File | Role |
|---|---|
| `server.py` | `create_server()`: all tools, prompts, resources, `SERVER_INSTRUCTIONS` |
| `tool_policy.py` | `TOOL_POLICIES`: per-tool policy metadata published as `_meta["lexlink/policy"]`, and its validator |
| `_helpers.py` | `TOOL_ANNOTATIONS`, `handle_tool_error`, `run_search`, `run_service`, the `SLIM_RESPONSE` helpers and size guard |
| `client.py` | HTTP client for law.go.kr: anti-bot redirect following, structured upstream error detection |
| `params.py` | snake_case to upstream camelCase mapping, OC resolution (`oc` argument, then `OC` env; the argument is ignored in HTTP mode) |
| `validation.py` | date and `jo` validation/normalization |
| `law_extras.py` | validation and normalization for the history/comparison/appendix/dictionary tools (oldAndNew, thdCmp, lsJoHstInf, lsHstInf, delHst, lsAbrv, licbyl, lstrm) |
| `linkage.py` | knowledge-base and ordinance-link request logic |
| `agency_codes.py` | ministry, committee and tribunal code tables and aliases |
| `as_of.py` | pure helpers for `law_as_of` (version in force on a date) |
| `article_text.py` | article text extraction (조문내용, 항/호/목 flattening) |
| `citation.py` | HTML citation extraction (BeautifulSoup) for `article_citation` |
| `parser.py`, `ranking.py` | response parsing and relevance ranking |
| `cache.py`, `resolver.py` | per-tool TTL cache; law-name abbreviation resolution |
| `errors.py` | `ErrorCode` and structured error responses |
| `stdio_server.py`, `http_server.py` | transport entry points (`uv run stdio`, `uv run serve`) |
| `http_security.py` | bearer auth, rate limit, session binding, Host/Origin validation (pure ASGI) |
| `raw_logger.py`, `log_processor.py` | HTTP traffic log writer; converter for the old log format |

Where each runtime variable is read: `grep -rn "getenv\|environ" src/`. The documented list is in [OPERATIONS.md](OPERATIONS.md).

## Conventions

- Every tool is registered with `@server.tool(annotations=TOOL_ANNOTATIONS)` (read-only, idempotent). `create_server()` wraps `server.tool` so every result passes the `SLIM_RESPONSE` size guard.
- Tool arguments are snake_case; `params.py` maps them to the upstream names. Unknown arguments are accepted and ignored (verified with `cache_stats(bogus_param=1)`).
- Default response type is `JSON`. The cache key includes the response type.
- Errors use `{status, error_code, message, hints, request_id}`. Codes are in `errors.py`.
- Article numbers are 6 digits (`000300` = 제3조, `001502` = 제15조의2). `validation.py` also accepts `3`, `"3의2"`, `"제3조의2"`, `"3-2"`.
- Dates are `YYYYMMDD`, ranges `YYYYMMDD~YYYYMMDD`.
- `ctx: Context = None` on tools for MCP logging.

## Adding a tool

1. Find the upstream endpoint and target in the [API reference](API_REFERENCE.md) or the open.law.go.kr guide, and call it once to see the real response shape.
2. Add the function in `server.py` following a neighbouring tool; reuse `run_search` / `run_service`.
3. Add an entry for the tool in `TOOL_POLICIES` in `src/lexlink/tool_policy.py` (category, evidence, size, upstream_calls, credential, short note). Decide the values from the code and a live measurement (count requests, measure the response size, check the OC is not in it), not by analogy; the rules are in the module docstring and in [API_REFERENCE.md](API_REFERENCE.md#도구-정책-메타데이터). Without an entry `create_server()` raises and `tests/test_tool_policy.py` fails.
4. Add offline tests with a fixture of the real response.
5. Update the tool list in [API_REFERENCE.md](API_REFERENCE.md) and the counts in the READMEs and AGENTS.md. Regenerate the tool list from the server instead of editing it by hand:

   ```python
   import asyncio
   from lexlink.server import create_server
   tools = asyncio.run(create_server().list_tools())
   print(len(tools), sorted(t.name for t in tools))
   ```

6. Add a line under Unreleased in [CHANGELOG.md](../CHANGELOG.md), in both the English and Korean sections.

## Docs rules

- Keep README.md and README_kr.md in sync.
- Tool counts, names and arguments come from the server, not from memory.
- Never put a real OC in docs or examples; use `<OC>`.
- Historical and plan documents go to `docs/archive/`.
- Check relative links and anchors after moving files. Anchors follow GitHub's rules (lowercase, spaces to hyphens, punctuation dropped).
