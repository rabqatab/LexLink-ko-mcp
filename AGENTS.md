# AGENTS.md

LexLink is a Model Context Protocol (MCP) server over the Korean National Law Information API (law.go.kr DRF). It exposes 68 tools, 9 prompts and 2 resources. Version: v2.2.0 plus the Unreleased section of CHANGELOG.md (`__version__` is read from package metadata and reported as MCP `serverInfo.version`).

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
- `tool_policy.py`: `TOOL_POLICIES`, one entry per tool, published as `_meta["lexlink/policy"]`. A new tool needs an entry or `create_server()` fails.
- `_helpers.py`: `TOOL_ANNOTATIONS`, `handle_tool_error`, `run_search`, `run_service`, SLIM helpers.
- `client.py`: HTTP client (follows law.go.kr JS anti-bot redirects, detects empty/unsubscribed/HTML upstream bodies).
- `law_extras.py`: argument validation and payload normalization for the history/comparison/appendix/dictionary tools (oldAndNew, thdCmp, lsJoHstInf, lsHstInf, delHst, lsAbrv, licbyl, lstrm).
- `precedent_status.py` (`prec_status`), `constitutional.py` (`law_constitutional_check`): derived tools whose logic lives outside `server.py`; the server only holds a thin wrapper.
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
- **`law_as_of`**: `in_force` true/false/null; false reasons `BEFORE_FIRST_ENFORCEMENT`, `BEFORE_EARLIEST_AVAILABLE_VERSION`, `AFTER_REPEAL`; null is `NOT_CURRENT_UPSTREAM` or `ARTICLE_STAGED_DATE_UNRESOLVED`. Upstream failures are errors, never "not found".
- **`prec_status`** (has a later 전원합의체 decision overruled this case?): statuses `overruled_found` (quoted evidence + source decision), `possible_overruling_needs_review` (leads), `case_not_found` (number not in the index, e.g. a joined case's second number), `incomplete_search` (list truncated or a candidate unread), `no_overruling_found_in_searched_set` (only when everything was read; never "not overruled"; read `searched_scope`). **`law_constitutional_check`** gives 헌재 위헌/헌법불합치 leads for one article (`decision_status` adverse_decision_found / needs_review / incomplete_search / no_adverse_decision_in_searched_set; an unresolvable law name is an error) and never changes `law_as_of`'s `in_force`. `law_as_of` returns `in_force: null`, reason `ARTICLE_STAGED_DATE_UNRESOLVED` when the chosen version's own 부칙 sets the article's 시행일 in a way that cannot be computed (older amendments' uncomputable dates are caveats only).
- **`simplify_article`** does not rewrite text (`text_simplified: false`): `simplified_text` equals `original_text`, and `term_glossary` is always empty (`glossary_status: withheld`): the 법령용어 database's 동의어 links include pairs that differ in law (배우자-반려자, 위법행위-불법행위) and cannot be told from sound ones. No term lookup is made.
- **`check_precedent_odds`** classifies the 주문 (disposition) only; labels include 파기환송, 상고기각, 일부인용, 인용, 기각, 각하, 불명. It is a distribution, not a win rate. Counts describe the sampled cases in `sample` only. A case is counted only if a distinctive query word is in its 사건명/판시사항/판결요지; others are `uncounted_cases`. No comparable word (ㅋㅋㅋ) or no related case gives empty statistics and a `low_relevance:` warning; fewer than 3 counted is `small_sample`.
- **Relevance flags**: `legal_resolver` / `chain_full_research` mark each article with `matched_query_terms`, `low_relevance`, `upstream_rank`: an advisory literal word overlap (`relevance_basis: term_overlap`) that errs both ways and never reorders results or skips lookups. Precedents are searched by the situation's distinctive words first (`search_basis`), then by law name (`relevance_unverified` when no word is shared). `chain_full_research` carries `related_precedents`. `chain_dispute_prep` returns metadata rows only, deduped, with `title_matches_query`.
- **`chain_law_system`**: `admin_rules` is `{name, id, article}` from the 위임행정규칙 entries; `linked_ordinances` comes from `lnkLsOrd`; failures go to `warnings`.
- **Zero results** return `status: ok` with `warning: "no_results"` and hints. `*_service` tools return `NOT_FOUND` for "일치하는 … 없습니다".
- **Unknown tool arguments are silently ignored** (verified).
- **Ministry interpretations** (`cgm_expc_*`): upstream target `{code}CgmExpc`, 39 ministries. 재정경제부 and 국세청 are list-only, so `cgm_expc_service` returns `VALIDATION_ERROR` for them.
- **`ordinLsCon_search`**: exactly one of `query`, `law_id`, `org`.
- **Knowledge-base linkage** tools use `lawService.do`; `display`/`page` are not upstream parameters for them.
- **History/comparison tools** (`oldAndNew_*`, `thdCmp_*`, `lsJoHstInf_search`, `lsHstInf_search`, `delHst_search`, `lsAbrv_search`, `licbyl_search`, `lstrm_*`): the upstream answers bad dates, unknown codes and missing dates with a silent 0 rows, so these are validated first (`VALIDATION_ERROR`). `thdCmp_service` needs `knd` and is 90-610 KB without `jo` (filtered locally, upstream has no article parameter). `lsAbrv_search` filters and pages the upstream's 2.3 MB list itself. `lstrm_service` reads XML because the JSON form detaches 출처/용례 from their entry, and takes `trm_seqs` (the 법령용어ID) since names with spaces/slashes/parentheses are NOT_FOUND by `query`. `oldAndNew_service` is an upstream-edited table (see its `caution`). `licbyl_search` returns links only. Details: [docs/API_REFERENCE.md](docs/API_REFERENCE.md#lexlink-도구-목록).
- **Filters that must not look applied** (#45, `guards.py`): upstream ignores `date` on prec/detc/decc/special_decc (sent as `prnc_yd`/`ed_yd`/`rsl_yd` `D~D`, shown in `filters_applied`); `nb` takes one case number (comma list = 0 rows upstream, `detc` also ignores `nb` when `query` is sent); `inq` is a numeric 질의기관코드; unknown `sort`/`search`/`gana`/`cls`/`sections` are `VALIDATION_ERROR`; `display` > 100 is capped with `display_capped`; `*_service` drops `lm` when `id` is given (neutral `notes` entry `lm_not_sent`); `nb` is a prefix match (`nb_prefix_match`); prec/expc keyword rows without `sort` are re-ranked by title relevance; `aiSearch` ignores `page` (`page_ignored`); `lsDelegated_service` has `jo` (client-side, `selection`); `ordin_service` returns a `resolved` block and, with opt-in `verify_id=true`, probes `mst=id` (`id_collision`). Synchronous tool functions run in worker threads (`install_threaded_tool_calls` in `_helpers.py`), the response cache is locked.
- **Search ranking**: `run_search` over-fetches up to 100 rows to re-rank keyword queries, then returns the requested page.
- **Error shape**: `{status, error_code, message, hints, request_id}`. Codes: `VALIDATION_ERROR`, `TIMEOUT`, `UPSTREAM_ERROR`, `INTERNAL_ERROR`, `NOT_FOUND`, `ARTICLE_NOT_FOUND`, `EMPTY_RESPONSE`, `API_NOT_SUBSCRIBED`, `UPSTREAM_HTML_ERROR`.

## Testing

`uv run pytest tests/` runs the offline tests (mocked upstream, no network or OC). Fixtures are in `tests/fixtures/`. Markers: `unit`, `integration`, `e2e`, `critical`, `slow`.

## Conventions

- Tools use `@server.tool(annotations=TOOL_ANNOTATIONS)` (read-only, idempotent) and `ctx: Context = None`.
- Arguments are snake_case; `params.py` maps them to upstream camelCase.
- Article numbers are 6 digits, 4-digit article + 2-digit branch (`000300` = 제3조, not 제300조 which is `030000`; `001502` = 제15조의2). Date ranges are `YYYYMMDD~YYYYMMDD`.
- A change that touches a tool's behaviour needs a line under Unreleased in CHANGELOG.md (English and Korean) and an update of the affected doc.
