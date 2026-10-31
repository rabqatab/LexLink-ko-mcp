[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/rabqatab-lexlink-ko-mcp-badge.png)](https://mseep.ai/app/rabqatab-lexlink-ko-mcp)

<div align="center">
  <img src="assets/LexLink_logo.png" alt="LexLink Logo" width="200"/>
  <h1>LexLink - Korean National Law Information MCP Server</h1>
</div>

**Read this in other languages:** **English** | [한국어 (Korean)](README_kr.md)

[![Kakao PlayMCP 10 3rd Prize](https://img.shields.io/badge/Kakao_PlayMCP_10-3rd_Prize_🏆-CD7F32)](https://playmcp.kakao.com/)
[![smithery badge](https://smithery.ai/badge/@rabqatab/lexlink-ko-mcp)](https://smithery.ai/server/@rabqatab/lexlink-ko-mcp)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LexLink is an MCP (Model Context Protocol) server that wraps the Korean National Law Information API ([open.law.go.kr](http://open.law.go.kr)) so AI agents can search and read Korean laws, case law, interpretations and related material.

## What it provides

- **66 tools**, **9 prompts** and **2 resources** (v2.2.0, plus the Unreleased changes listed in [CHANGELOG.md](CHANGELOG.md)).
- Laws by effective date or announcement date, single articles (`jo`), English translations, administrative rules, local ordinances, treaties.
- Court precedents, Constitutional Court decisions, legal interpretations, administrative appeals, committee decisions, ministry interpretations, special tribunals.
- `law_as_of`: the version of a law (or one article) in force on a given date.
- `article_citation`: citations referenced by one article, extracted from law.go.kr HTML (no LLM). Edge cases (ranges, deleted articles) are listed under limitations in the [API reference](docs/API_REFERENCE.md#알려진-한계).
- AI/semantic search (`aiSearch`, `aiRltLs_search`) and one-call chain tools (`chain_*`).
- Per-tool TTL cache and Korean law-name abbreviation resolution (e.g. 자통법).
- JSON by default; `type="XML"` or `"HTML"` on request.
- Errors come back as `{status: "error", error_code, message, hints, request_id}`.

All tool names and arguments are in the [API reference](docs/API_REFERENCE.md#lexlink-도구-목록).

## Tool groups

| Group | Tools |
|---|---|
| Laws | `eflaw_search`, `law_search`, `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`, `law_as_of`, `elaw_search`, `elaw_service` |
| Admin rules, ordinances, linkage | `admrul_*`, `ordin_*`, `ordinLsCon_search`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`, `drlaw_search`, `lsDelegated_service` |
| Case law and decisions | `prec_*`, `detc_*`, `expc_*`, `decc_*`, `committee_*`, `cgm_expc_*`, `special_decc_*` |
| Treaties | `trty_search`, `trty_service` |
| AI search and knowledge base | `aiSearch`, `aiRltLs_search`, `lstrm_ai_search`, `dlytrm_search`, `lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`, `ls_rlt_search` |
| History, comparison, appendix, dictionary | `oldAndNew_*`, `thdCmp_*`, `lsJoHstInf_search`, `lsHstInf_search`, `delHst_search`, `lsAbrv_search`, `licbyl_search`, `lstrm_*` |
| Analysis | `article_citation`, `check_precedent_odds`, `legal_resolver`, `simplify_article`, `law_amendment_summary`, `article_amendment_diff` |
| Chains and ops | `chain_full_research`, `chain_amendment_track`, `chain_dispute_prep`, `chain_law_system`, `cache_stats` |

Which tool to start with:

| You have | Start with |
|---|---|
| A vague question in plain Korean | `legal_resolver`, `aiSearch`, `aiRltLs_search` |
| A law name and article number | `eflaw_search` (get MST) then `eflaw_josub` / `eflaw_service` with `jo` |
| "What did the law say on date D?" | `law_as_of` |
| Old/new article text of an amendment | `oldAndNew_search` then `oldAndNew_service` |
| Law, 시행령 and 시행규칙 side by side | `thdCmp_search` then `thdCmp_service` with `jo` (very large without it) |
| What a legal term means | `lstrm_search` then `lstrm_service` (dictionary); `lstrm_ai_search` only gives related-term links |
| A topic for case law | `prec_search`, `detc_search`, `chain_dispute_prep` |

For article text always pass `jo` (e.g. `35`, `"35의5"`, `"제35조의5"`, `"003505"`; normalized to 6 digits). Without it some laws return a very large body.

**Prompts:** `search-korean-law`, `get-law-article`, `get-article-with-citations`, `analyze-law-citations`, `search-admin-rules`, `tool-selection-guide`, `analyze-legal-situation`, `explain-legal-document`, `check-legal-precedent`.

**Resources:** `lexlink://laws/frequently-used` (about 20 common law names mapped to 법령ID) and the template `lexlink://law/{name}` (read it as e.g. `lexlink://law/자통법`, without braces; the name is URL-decoded, resolver aliases are applied, and one live `law_search` exact-name lookup is the fallback).

## Quick start

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/). You also need an **OC** from [open.law.go.kr](https://open.law.go.kr): the part of your registered email before the `@`. law.go.kr checks the OC together with the caller's IP, so the machine running LexLink may need its IP registered there.

```bash
uv sync

# stdio (Claude Code, Cursor, other local MCP clients)
OC=<OC> uv run stdio

# Streamable HTTP at /mcp (HTTP mode refuses to start without auth settings)
OC=<OC> LEXLINK_AUTH_TOKENS=local:<TOKEN> TRANSPORT=http uv run serve
```

The server does not read `.env` by itself. Export the variables, or run `uv run --env-file .env stdio`.

`OC` is resolved as: tool argument `oc` first, then the `OC` environment variable. **In HTTP mode the `oc` argument is ignored** and the server's `OC` is always used.

For HTTP deployment (auth, TLS proxy, rate limits, logging) see [docs/OPERATIONS.md](docs/OPERATIONS.md).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `OC` | *(required)* | law.go.kr API identifier |
| `LEXLINK_BASE_URL` | `http://www.law.go.kr` | Upstream base URL |
| `LEXLINK_TIMEOUT` | `60` | Upstream request timeout (seconds) |
| `SLIM_RESPONSE` | unset | `1`/`true`/`yes`/`on` turns on the compact mode for size-limited hosts such as PlayMCP: drops `raw_content` when `ranked_data` exists, keeps the compact caps (500-char excerpts, top-10/3 lists, 80 delegation entries) and trims any result over 20,000 bytes (`truncated`, `truncated_notes`). Unset: nothing already fetched is cut (one exception: `simplify_article` looks up at most 20 legal terms) |
| `TRANSPORT` | `sse` | HTTP server only: `http` (recommended) or `sse` |

The HTTP-only variables (`HOST`, `PORT`, `LEXLINK_AUTH_TOKENS`, rate limits, logging, ...) are in [docs/OPERATIONS.md](docs/OPERATIONS.md).

### Example

```python
eflaw_search(query="자동차관리법", display=5)
# {"status": "ok", "request_id": "...", "upstream_type": "JSON", "ranked_data": ..., "raw_content": ...}

eflaw_josub(mst="<MST from the search>", jo="제3조")
```

Error codes: `VALIDATION_ERROR`, `TIMEOUT`, `UPSTREAM_ERROR`, `INTERNAL_ERROR`, `NOT_FOUND`, `ARTICLE_NOT_FOUND`, `EMPTY_RESPONSE`, `API_NOT_SUBSCRIBED`, `UPSTREAM_HTML_ERROR`. See the [API reference](docs/API_REFERENCE.md#appendix-c-lexlink-구조화-오류-코드).

## Documentation

| Doc | For |
|---|---|
| [docs/README.md](docs/README.md) | Index |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Tool list, arguments, upstream API catalog, limitations |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | HTTP server: deploy, auth, TLS proxy, logging (Korean) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Code layout, tests, adding tools |
| [CHANGELOG.md](CHANGELOG.md) | Release history, Unreleased changes |
| [AGENTS.md](AGENTS.md) | Notes for coding agents |

## Contributing

Fork, branch, add tests, run `uv run pytest tests/`, open a pull request. Details in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## License

No LICENSE file is included in this repository.

## Acknowledgments

- **law.go.kr** - Korean National Law Information API
- **MCP** - Model Context Protocol by Anthropic
- **[korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)** - inspiration for caching, law name resolution and chain tools

## Support

- Issues: [GitHub Issues](https://github.com/rabqatab/LexLink-ko-mcp/issues)
- law.go.kr API: [open.law.go.kr](http://open.law.go.kr)
