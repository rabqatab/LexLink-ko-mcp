# Design: LexLink v2.0 Upgrade

**Date:** 2026-03-30
**Scope:** MCP upgrade + server.py refactor + 18 new API tools
**Branch:** `feature/v2-upgrade` (off main)

---

## 1. Issue #10: MCP Package Upgrade

**Problem:** LexLink pins `mcp>=1.15.0` but runs on v1.20.0 due to protocol `2025-06-18` incompatibility (v1.23.3 caused 502 errors).

**Fix:** Bump to `mcp>=1.26.0` (latest stable, Jan 2026). The protocol version issue is resolved in newer releases.

**Verification:**
- `uv sync` with updated dependency
- Start server via stdio and HTTP transports
- Confirm no 502 errors on tool calls

**Rollback:** If v1.26.0 introduces regressions, pin to highest working version < 1.26.0.

---

## 2. Phase 6: Refactor server.py

**Goal:** Reduce `server.py` from ~3,250 → ~1,800-2,200 lines (~35-45% reduction) via shared helpers in `src/lexlink/_helpers.py`.

**Constraint:** Strictly behavior-preserving. Same inputs, same outputs. Each tool keeps its own `@server.tool()` decorator and `ctx: Context = None` signature.

### 2.1 Helpers to Extract

#### `TOOL_ANNOTATIONS`
Shared constant for `ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)`. Currently duplicated across all 26 tools.

#### `resolve_oc(oc)` (no change)
Already exists in `params.py` as `resolve_oc(override_oc)`. No `ctx` parameter needed — OC resolution is ctx-independent. Not re-extracted, just re-exported from `_helpers.py` for convenience.

#### `@handle_tool_error`
Decorator wrapping the try/except + `create_error_response()` pattern. Must handle both sync and async functions (most tools are sync, `article_citation` is async). Currently ~11 lines per tool × 26 tools.

As part of extraction, standardize all tools to **raise exceptions for validation failures** instead of returning error dicts directly. Some tools currently `raise ValueError` (caught by try/except), while others `return create_error_response()` directly (bypassing any decorator). After refactoring, all validation failures raise, and `@handle_tool_error` catches uniformly. External behavior (error response structure) stays identical.

#### `stringify_id(id)`
Convert `Union[str, int, None]` to `Optional[str]`. Currently inlined in service tools.

#### `slim_response(response)`
Currently defined at module level in `server.py`. Move to `_helpers.py` for co-location with other helpers.

#### `run_search(ctx, oc, target, query, params, ...)`
Common search logic with **two ranking pipelines**:

**Pipeline A — Law-list ranking** (used by `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`):
1. Resolve OC → build client → map params
2. Over-fetch: set `upstream_params["numOfRows"] = "100"`
3. Execute request → parse XML
4. Extract via `extract_law_list(parsed_data)`
5. Rank by field `"법령명한글"` (or equivalent)
6. Call `_cache_law()` for law-target searches (populates `lexlink://laws/frequently-used` resource)
7. Trim to requested `display` count
8. Update via `update_law_list(parsed_data, ranked_list)`
9. Apply `slim_response()` → return

**Pipeline B — Items-list ranking** (used by `prec_search`, `detc_search`, `expc_search`, `decc_search`):
1. Resolve OC → build client → map params
2. Over-fetch: set `upstream_params["display"] = "100"`
3. Execute request → parse XML
4. Extract via `extract_items_list(parsed_data, category)` where category = `"prec"`, `"detc"`, etc.
5. Rank by category-specific field (`"판례명"`, `"결정명"`, etc.)
6. Trim to requested `display` count
7. Update via `update_items_list(parsed_data, ranked_list, category)`
8. Apply `slim_response()` → return

**`run_search` parameters** to handle both pipelines:
- `list_type`: `"law"` or `"items"` — selects pipeline A or B
- `item_category`: e.g. `"prec"`, `"detc"` — for items-list extraction (pipeline B only)
- `ranking_field`: e.g. `"법령명한글"`, `"판례명"` — field used for relevance ranking
- `over_fetch_key`: `"numOfRows"` (pipeline A) or `"display"` (pipeline B)
- `post_rank_hook`: optional callback, e.g. `_cache_law` for law-target searches
- `extra_params`: dict of target-specific upstream params

#### `run_service(ctx, oc, target, id, params, ...)`
Common service logic:
1. Resolve OC
2. Stringify ID
3. Build LawAPIClient
4. Map params to upstream format
5. Execute request
6. Parse XML
7. Return result

Currently ~40 lines per service tool × 11 service tools.

#### `_get_client` access pattern
`_get_client()` is currently a closure inside `create_server()`. For `_helpers.py` to use it, `run_search` and `run_service` accept a `client` argument (constructed by the tool function before calling the helper). Alternatively, `_get_client` can be extracted to a module-level factory in `client.py`. Decision deferred to implementation — either approach works.

### 2.2 Refactored Tool Shape

Before (~50 lines each):
```python
@server.tool(annotations=ToolAnnotations(...))
async def some_search(ctx: Context, query: str = "*", display: int = 20, ..., oc: str = None) -> dict:
    try:
        resolved_oc = resolve_oc(ctx, oc)  # inlined
        client = LawAPIClient(...)          # inlined
        params = map_params_to_upstream(...) # inlined
        response = await client.get(...)    # inlined
        parsed = parse_xml_response(...)    # inlined
        ranked = rank_search_results(...)   # inlined
        slimmed = slim_response(...)        # inlined
        return slimmed
    except Exception as e:
        return create_error_response(...)   # inlined
```

After (~10 lines each):
```python
@server.tool(annotations=TOOL_ANNOTATIONS)
@handle_tool_error
async def some_search(ctx: Context, query: str = "*", display: int = 20, ..., oc: str = None) -> dict:
    return await run_search(
        ctx=ctx, oc=oc, target="someTarget",
        query=query, display=display,
        extra_params={...},
    )
```

### 2.3 Non-Standard Tools

These tools don't fit the common search/service pattern and stay mostly as-is:
- `article_citation` — HTML scraping, not API call
- `aiSearch` / `aiRltLs_search` — different endpoint pattern, anti-bot handling for 404
- `drlaw_search` — returns HTML, no XML parsing

They still benefit from `TOOL_ANNOTATIONS`, `resolve_oc()`, and `@handle_tool_error`.

---

## 3. New API Categories (18 Tools)

All new tools use the refactored helpers (`run_search` / `run_service`), so each is ~10-15 lines.

### 3.1 자치법규 (Local Ordinances) — 3 tools

| Tool | target | Type |
|------|--------|------|
| `ordin_search` | `ordin` | search |
| `ordin_service` | `ordin` | service |
| `ordinLsCon_search` | `ordinLsCon` | search |

**Unique params:** `org` (지자체 도/시), `sborg` (시/군/구), `knd` (법령종류 enum), `ordinFd` (분류코드).

### 3.2 조약 (Treaties) — 2 tools

| Tool | target | Type |
|------|--------|------|
| `trty_search` | `trty` | search |
| `trty_service` | `trty` | service |

**Unique params:** `eft_yd` (발효일자), `conc_yd` (체결일자), `cls` (1=양자, 2=다자), `nat_cd` (국가코드).

### 3.3 법령정보 지식베이스 (Knowledge Base) — 7 tools

| Tool | target | Type | Description |
|------|--------|------|-------------|
| `lstrm_ai_search` | `lstrmAI` | search | 법령용어 AI 조회 |
| `dlytrm_search` | `dlytrm` | search | 일상용어 조회 |
| `lstrm_rlt_search` | `lstrmRlt` | search | 법령용어→일상용어 연계 |
| `dlytrm_rlt_search` | `dlytrmRlt` | search | 일상용어→법령용어 연계 |
| `lstrm_rlt_jo_search` | `lstrmRltJo` | search | 법령용어→조문 연계 |
| `jo_rlt_lstrm_search` | `joRltLstrm` | search | 조문→법령용어 연계 |
| `ls_rlt_search` | `lsRlt` | search | 관련법령 조회 |

### 3.4 위원회 결정문 (Committee Decisions) — 2 parametric tools

| Tool | Type | Description |
|------|------|-------------|
| `committee_search` | search | 위원회 결정문 목록 조회 |
| `committee_service` | service | 위원회 결정문 본문 조회 |

**`committee` enum parameter** (maps to target code):
| Committee | Code |
|-----------|------|
| 개인정보보호위원회 | ppc |
| 고용보험심사위원회 | eiac |
| 공정거래위원회 | ftc |
| 국민권익위원회 | acr |
| 금융위원회 | fsc |
| 노동위원회 | nlrc |
| 방송미디어통신위원회 | kcc |
| 산업재해보상보험재심사위원회 | iaciac |
| 중앙토지수용위원회 | oclt |
| 중앙환경분쟁조정위원회 | ecc |
| 증권선물위원회 | sfc |
| 국가인권위원회 | nhrck |

### 3.5 중앙부처 1차 해석 (Ministry Interpretations) — 2 parametric tools

| Tool | Type | Description |
|------|------|-------------|
| `cgm_expc_search` | search | 중앙부처 법령해석 목록 조회 |
| `cgm_expc_service` | service | 중앙부처 법령해석 본문 조회 |

**`ministry` enum parameter** (maps to target suffix):
Target pattern: `cgmExpc{MinistryCode}`

32 ministries: Moel, Molit, Moef, Mof, Mois, Me, Kcs, Nts, Moe, Msit, Mpva, Mnd, Mafra, Mcst, Moj, Mohw, Motie, Mogef, Mofa, Mss, Mou, Moleg, Mfds, Mpm, Kma, Khs, Rda, Npa, Dapa, Mma, Kfs, Nfa, Oka, Pps, Kdca, Kostat, Kipo, Kcg, Naacc.

### 3.6 특별행정심판 (Special Admin Appeals) — 2 parametric tools

| Tool | Type | Description |
|------|------|-------------|
| `special_decc_search` | search | 특별행정심판 재결례 목록 조회 |
| `special_decc_service` | service | 특별행정심판 재결례 본문 조회 |

**`tribunal` enum parameter** (maps to target prefix):
| Organization | Code |
|---|---|
| 조세심판원 | tt |
| 해양안전심판원 | kmst |
| 국민권익위원회 | acr |
| 인사혁신처 소청심사위원회 | adap |

Target pattern: `{Code}SpecialDecc`

---

## 4. New Parameter Mappings

New tool params that need adding to `PARAM_MAP` in `params.py`:

| Tool param (snake_case) | API param (upstream) | Used by |
|---|---|---|
| `eft_yd` | `eftYd` | `trty_search` |
| `conc_yd` | `concYd` | `trty_search` |
| `nat_cd` | `natCd` | `trty_search` |
| `sborg` | `sborg` | `ordin_search` (pass-through) |
| `ordin_fd` | `ordinFd` | `ordin_search` |
| `anc_yd` | `ancYd` | `ordin_search` |
| `anc_no` | `ancNo` | `ordin_search` |
| `rr_cls_cd` | `rrClsCd` | `ordin_search` |

Params already in `PARAM_MAP` or pass-through: `org`, `knd`, `cls`, `query`, `display`, `page`, `search`, `date`, `sort`, `gana`.

---

## 5. Execution Order

1. **Create branch** `feature/v2-upgrade` off main
2. **Issue #10:** Bump mcp dependency, verify
3. **Phase 6:** Extract helpers, refactor existing 26 tools one category at a time, test after each
4. **New APIs:** Add 18 new tools using helpers, test each category
5. **Update docs:** ROADMAP.md, STATUS.md, ISSUES.md, API_REFERENCE.md, CHANGELOG.md
6. **Final verification:** Full test suite + manual smoke test
7. **Merge to main** after user approval

---

## 6. Risk Mitigation

- **Separate branch**: All work on `feature/v2-upgrade`, never directly on main
- **Incremental refactoring**: Refactor one tool category at a time, test between each
- **No behavior changes**: Helpers reproduce exact existing logic
- **New tools use proven patterns**: All new tools go through the same `run_search`/`run_service` as existing tools
- **Rollback-friendly**: Each step is a separate commit
