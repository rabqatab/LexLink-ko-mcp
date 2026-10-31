"""
LexLink MCP Server - Korean National Law Information API.

This server exposes the law.go.kr Open API through MCP tools,
enabling AI agents to search and retrieve Korean legal information.

All tools default to JSON format. XML and HTML are also supported.
"""

import asyncio
import datetime
import json
import logging
import os
import re
from typing import Annotated, Optional, Union
from urllib.parse import unquote

from mcp.server.fastmcp import FastMCP, Context
from pydantic import Field

from . import __version__
from .client import LawAPIClient, redact_oc
from .errors import ErrorCode, create_error_response
from .params import map_params_to_upstream, resolve_oc
from .validation import (
    validate_date_range, normalize_jo, JoFormatError, describe_jo,
    response_has_article, extract_law_name, format_article_number,
)
from .parser import parse_xml_response, extract_law_list, update_law_list
from .ranking import detect_query_language, should_apply_ranking, rank_search_results
from .resolver import get_resolver
from ._helpers import (
    TOOL_ANNOTATIONS, stringify_id, handle_tool_error, ToolValidationError,
    slim_response, run_search, run_service, annotate_prec_body_availability,
    extract_order, classify_order, extract_key_factors, extract_legal_terms, compute_text_diff, run_coroutine_sync,
    compact_limit, slim_limited, slim_enabled, mark_slim_cut, low_relevance_warning,
    rename_row_ids_to_rank, run_ranked_paging, validate_paging, OVER_FETCH_WINDOW,
    add_no_more_results_hint, add_no_results_guidance, body_is_all_null,
    trim_raw_to_ranked,
    NO_RESULTS_MESSAGE, NO_RESULTS_HINTS, NO_RESULTS_BODY_HINT, OUTCOME_NOTE,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)



def _today() -> str:
    """Today as YYYYMMDD (module-level so tests can patch it)."""
    return datetime.date.today().strftime("%Y%m%d")


def create_server(transport_security=None) -> FastMCP:
    """
    Create and configure the LexLink MCP server.

    Returns:
        Configured FastMCP server instance with registered tools
    """
    # Server instructions - automatically provided to all LLM clients
    SERVER_INSTRUCTIONS = """
You are using LexLink, a Korean legal information API.

## IMPORTANT: Citation Extraction Rule

When a user asks about a specific law article (e.g., "건축법 제3조", "자본시장법 제11조"):

1. **Search**: Use `eflaw_search` to find the law
   - Extract: 법령일련번호 (MST) and 법령명한글

2. **Citations**: ALWAYS use `article_citation` to get referenced laws
   - Parameters: mst, law_name, article number
   - Parsed from the official law.go.kr hyperlinks (not LLM-based); "같은 법" is resolved heuristically, so verify against the article text when it matters

3. **Response**: Include citation summary
   - Total count, external vs internal
   - Key cited laws with article references

## Available Tools by Category

**Law Search & Content:**
- eflaw_search, law_search: Search laws
- eflaw_service, law_service: Get full law text
- article_citation: Extract citations from articles

**Case Law & Legal Research:**
- prec_search/service: Court precedents
- detc_search/service: Constitutional Court decisions
- expc_search/service: Legal interpretations
- decc_search/service: Administrative appeals

**⚠️ Search row number is not a key:**
Rows in a search result's raw_content carry `id` = row number (1, 2, 3...), and ranked_data
renames it to `rank`. Never pass it to a *_service call. Use the real key per family:
법령=법령ID/법령일련번호(MST), 판례=판례일련번호, 헌재=헌재결정례일련번호,
법령해석=법령해석례일련번호, 행정심판=행정심판재결례일련번호, 행정규칙=행정규칙일련번호,
자치법규=자치법규ID, 조약=조약일련번호.

**⚠️ Response Size — sections parameter:**
For case law full text (prec_service, detc_service, expc_service, decc_service),
use `sections="summary"` to get key sections only (판시사항, 판결요지, etc.)
without the verbose full text (판례내용/전문/이유). This keeps responses under 20KB.
Use `sections="full"` only when the complete judgment text is specifically needed.

**Knowledge Base (AI-powered search):**
- aiSearch: Semantic search for law articles - returns FULL article text
- aiRltLs_search: Find semantically related laws

**Local Ordinances (자치법규):**
- ordin_search/service: Local ordinance search & retrieval
- ordinLsCon_search: Ordinance-to-law linkage

**Treaties (조약):**
- trty_search/service: International treaty search & retrieval

**Legal Knowledge Base (법령정보 지식베이스):**
- lstrm_ai_search: Legal term AI search
- dlytrm_search: Everyday term search
- lstrm_rlt_search, dlytrm_rlt_search: Term cross-references
- lstrm_rlt_jo_search, jo_rlt_lstrm_search: Term-article linkage
- ls_rlt_search: Related law search

**Committee Decisions (위원회 결정문):**
- committee_search/service: Decisions from 12 government committees

**Ministry Interpretations (중앙부처 해석):**
- cgm_expc_search/service: First-instance interpretations from 39 ministries
  (ministry names follow the current 정부조직: 재정경제부 (formerly 기획재정부), 기후에너지환경부, 산업통상부,
  성평등가족부, 국가데이터처, 지식재산처, 국가유산청. 재정경제부 and 국세청 provide the list API only —
  no full text via cgm_expc_service; use the item's 법령해석상세링크 instead)

**Special Administrative Appeals (특별행정심판):**
- special_decc_search/service: Decisions from 4 special tribunals

**Public Legal Assistance:**
- legal_resolver: Given a situation, find all applicable laws, precedents, and interpretations in one call
- simplify_article: Get a law article with a glossary of database synonym links for its legal terms (text is not rewritten)
- check_precedent_odds: Find precedent statistics and key outcome factors for a legal question
- law_amendment_summary: See all revisions of a law in a date range
- law_as_of: The law (or one article) as in force on a given date D, with MST/시행일/공포일 (사건일 기준 적용 법령)
- article_amendment_diff: Compare how a specific article changed between two versions

**Guided Workflows (Prompts):**
- analyze-legal-situation: Describe your situation in plain Korean → get applicable laws, rights, and action steps
- explain-legal-document: Paste a legal document → get plain Korean explanation
- check-legal-precedent: Ask a yes/no legal question → get precedent-backed answer (outcome distribution, not a win rate)

## Tool Selection for Casual Users

When a user describes a personal legal situation (not a specific law query):
→ Use analyze-legal-situation prompt or legal_resolver tool FIRST
→ Do NOT start with eflaw_search unless the user mentions a specific law name

When a user pastes legal text and asks "이게 무슨 뜻이야?":
→ Use explain-legal-document prompt

When a user asks "~할 수 있나요?" or "~되나요?" style questions:
→ Use check-legal-precedent prompt

When a user asks about law changes over time:
→ Use law_amendment_summary first, then article_amendment_diff for details

When a user asks what a law/article said (or which version applied) on a specific date:
→ Use law_as_of(law_name, as_of, article). Do NOT pass the date as ef_yd to eflaw_search/eflaw_service:
  there ef_yd is a 시행일 range filter / revision selector, not "in force on D"

**Chain Research Tools (one-call workflows):**
- chain_full_research: Complete legal research — statutes + precedent analysis + interpretations + citations
- chain_amendment_track: Law revision history + article-level diff
- chain_dispute_prep: All case law sources — precedents + appeals + constitutional + tribunal
- chain_law_system: Full law hierarchy — delegation tree + admin rules + linked ordinances
- cache_stats: View cache performance statistics

**Smart Features (automatic):**
- Law name resolution: abbreviations auto-resolved (자통법 → 자본시장과 금융투자업에 관한 법률)
- Response caching: repeated queries served from cache (1hr search, 24hr articles)

## Common Law 법령IDs (verified, stable across amendments)
Use these IDs directly with eflaw_service(id=...), law_service(id=...), etc. to SKIP the search step.
| Law | 법령ID |
|-----|--------|
| 민법 | 001706 |
| 형법 | 001692 |
| 상법 | 001702 |
| 대한민국헌법 | 001444 |
| 민사소송법 | 001700 |
| 형사소송법 | 001671 |
| 행정소송법 | 001218 |
| 행정절차법 | 001362 |
| 국세기본법 | 001586 |
| 소득세법 | 001565 |
| 법인세법 | 001563 |
| 근로기준법 | 001872 |
| 건축법 | 001823 |
| 자본시장법 (자본시장과 금융투자업에 관한 법률) | 010513 |
| 국토계획법 (국토의 계획 및 이용에 관한 법률) | 009294 |
| 도로교통법 | 001638 |
| 개인정보 보호법 | 011357 |
| 부동산공시법 (부동산 가격공시에 관한 법률) | 001827 |
| 민사집행법 | 009290 |
| 특정범죄가중법 (특정범죄 가중처벌 등에 관한 법률) | 001676 |

For laws NOT in this table, use eflaw_search first.
For article_citation: you MUST first call eflaw_search to get the current MST (법령일련번호), as MST changes on law revision.

## Quick Reference
- 법령ID: Stable law identifier (use with id= parameter) — listed above for common laws
- MST (법령일련번호): Version-specific identifier from search results (changes on revision)
- Article format: "000300" = 제3조, "001102" = 제11조의2
"""

    server = FastMCP(
        "LexLink - Korean Law API",
        instructions=SERVER_INSTRUCTIONS,
        transport_security=transport_security,
    )
    # FastMCP has no version argument; set it on the low-level server so that
    # `initialize` reports LexLink's own version instead of the mcp library's.
    server._mcp_server.version = __version__

    # Central SLIM_RESPONSE size guard: every tool result goes through it.
    _register_tool = server.tool

    def _guarded_tool(*args, **kwargs):
        decorate = _register_tool(*args, **kwargs)
        return lambda fn: decorate(slim_limited(fn))

    server.tool = _guarded_tool

    def _get_client() -> LawAPIClient:
        """Create HTTP client from environment variables or defaults."""
        return LawAPIClient(
            base_url=os.getenv("LEXLINK_BASE_URL", "http://www.law.go.kr"),
            timeout=int(os.getenv("LEXLINK_TIMEOUT", "60")),
        )

    def _normalize_jo_arg(jo: Optional[Union[str, int]]) -> Optional[str]:
        """Normalize a user-supplied jo (35 / '35의5' / '제35조의5' / '003505') to the
        6-digit upstream code. Raises ToolValidationError (→ VALIDATION_ERROR + hints)."""
        try:
            return normalize_jo(jo)
        except JoFormatError as e:
            raise ToolValidationError(str(e), hints=e.hints) from e

    NO_OC_CITATION_WARNING = "OC 없음: mst/법령명 일치와 조문 존재를 확인하지 못했습니다"

    # Only these block article_citation; any other upstream failure (TIMEOUT,
    # API_NOT_SUBSCRIBED, UPSTREAM_ERROR ...) must not stop the OC-free scrape.
    HARD_VERIFY_ERRORS = {ErrorCode.NOT_FOUND, ErrorCode.ARTICLE_NOT_FOUND}

    def _norm_law_name(v: str) -> str:
        """Compare key: drop 「」『』, parenthetical suffixes like (법률), and whitespace."""
        v = re.sub(r"[「」『』]", "", v or "")
        v = re.sub(r"[(（][^)）]*[)）]", "", v)
        return re.sub(r"\s+", "", v)

    def _body_abbrev(raw: str) -> str:
        m = re.search(r'"법령명약칭"\s*:\s*"([^"]*)"', raw or "")
        return m.group(1).strip() if m else ""

    def _lookup_official_abbrev(upstream_name: str, resolved_oc: str) -> str:
        """One law_search by the official name for its 법령약칭명 ("" when none/failed)."""
        try:
            res = run_search(
                get_client=_get_client, target="law", query=upstream_name,
                snake_params={"oc": resolved_oc, "target": "law", "type": "JSON",
                              "query": upstream_name, "display": 20, "page": 1},
                response_type="JSON", display=20,
            )
        except Exception:
            return ""
        if not isinstance(res, dict) or res.get("status") != "ok":
            return ""
        want = _norm_law_name(upstream_name)
        for row in law_rows(res):
            if _norm_law_name(row.get("법령명한글", "")) == want:
                return (row.get("법령약칭명") or "").strip()
        return ""

    def _verify_citation_target(
        mst: str, law_name: str, article: int, article_branch: int, resolved_oc: str,
    ) -> tuple[Optional[dict], list[str]]:
        """One lawService call (target=law, MST+JO) to check that mst belongs to
        law_name and that the article exists.

        Returns ``(error_response | None, warnings)``. Only NOT_FOUND,
        ARTICLE_NOT_FOUND and a name mismatch are errors; other upstream
        failures become warnings and the caller continues.
        """
        jo_code = format_article_number(article, article_branch)
        params = {"oc": resolved_oc, "target": "law", "type": "JSON", "mst": mst, "jo": jo_code}
        response = run_service(
            get_client=_get_client, target="law",
            snake_params=params, response_type="JSON",
        )
        if response.get("status") != "ok":
            code = response.get("error_code") or ErrorCode.UPSTREAM_ERROR
            if code in HARD_VERIFY_ERRORS:
                response = dict(response)
                response["success"] = False
                return response, []
            return None, [
                f"검증 생략: 법령 본문 조회 실패 ({code}); mst/법령명 일치와 조문 존재를 확인하지 못했습니다"
            ]
        raw = response.get("raw_content", "")
        upstream_name = extract_law_name(raw, "JSON")
        if upstream_name:
            wanted = {_norm_law_name(law_name), _norm_law_name(get_resolver().resolve(law_name))}
            known = {_norm_law_name(upstream_name)}
            abbrev = _body_abbrev(raw)
            if abbrev:
                known.add(_norm_law_name(abbrev))
            if not (wanted & known):
                # Not the official name or the body's abbreviation: ask the search
                # index once for the official 법령약칭명.
                official_abbrev = _lookup_official_abbrev(upstream_name, resolved_oc)
                if official_abbrev:
                    known.add(_norm_law_name(official_abbrev))
            if not (wanted & known):
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=f"mst={mst}의 법령명은 '{upstream_name}'이며 law_name='{law_name}'과 일치하지 않습니다. "
                            f"mst {mst} belongs to '{upstream_name}', not '{law_name}'.",
                    hints=[
                        "eflaw_search/law_search 결과의 법령일련번호(MST)와 법령명한글을 함께 사용하세요",
                        "Use the MST and 법령명한글 from the same search result row",
                    ],
                    request_id=response.get("request_id"),
                    success=False,
                    mst=mst, law_name=law_name, upstream_law_name=upstream_name,
                ), []
        if not response_has_article(raw, "JSON"):
            err = _check_article_present(response, jo_code, "JSON")
            err["success"] = False
            err["mst"] = mst
            err["hints"] = (err.get("hints") or []) + [
                f"mst={mst}({upstream_name or law_name}) 버전에 해당 조문이 없습니다. "
                "다른 시행일 버전의 MST를 확인하거나 article/article_branch를 점검하세요"
            ]
            return err, []
        return None, []

    def _no_results_fields(body_search: bool = False) -> dict:
        """warning/message/hints for composite tools that found nothing."""
        return {
            "warning": "no_results",
            "message": NO_RESULTS_MESSAGE,
            "hints": list(NO_RESULTS_HINTS) + ([NO_RESULTS_BODY_HINT] if body_search else []),
        }

    def _check_article_present(response: dict, jo_code: Optional[str], response_type: str) -> dict:
        """After a lawService call with a jo filter, turn an article-less 'ok' body
        (law.go.kr returns only 기본정보 or {} for a non-existent JO) into
        a structured ARTICLE_NOT_FOUND error."""
        if not jo_code or response.get("status") != "ok":
            return response
        raw = response.get("raw_content", "")
        if response_has_article(raw, response_type):
            return response
        law_name = extract_law_name(raw, response_type)
        return create_error_response(
            error_code=ErrorCode.ARTICLE_NOT_FOUND,
            message=f"{describe_jo(jo_code)}(jo={jo_code}) 조문을 찾을 수 없습니다"
                    + (f" — 법령: {law_name}" if law_name else "")
                    + f". Article {describe_jo(jo_code)} not found in the upstream response.",
            hints=[
                "jo는 6자리 코드(앞 4자리 조번호 + 뒤 2자리 가지번호)입니다. 예: 제35조 → 003500, 제35조의5 → 003505",
                "해당 조문이 이 법령(또는 이 MST의 시행일 버전)에 존재하지 않을 수 있습니다. 삭제·신설 조문이면 다른 버전(MST)을 확인하세요",
                "law_service/eflaw_service를 jo 없이 호출하면 전체 조문 목록을 확인할 수 있습니다 (응답이 클 수 있음)",
                "Check the 6-digit jo format; the article may not exist in this law/version",
            ],
            request_id=response.get("request_id"),
            jo=jo_code,
            law_name=law_name,
        )

    # ==================== MCP Resources: Law ID Cache ====================

    # In-memory cache: law_name -> {id, full_name, abbrev, type}
    _law_cache: dict[str, dict] = {}

    def _seed_cache() -> None:
        """Populate cache with frequently-referenced Korean laws."""
        # Verified against live law.go.kr API (2026-02-28)
        seed = [
            {"id": "001706", "full_name": "민법", "abbrev": None, "type": "법률"},
            {"id": "001692", "full_name": "형법", "abbrev": None, "type": "법률"},
            {"id": "001702", "full_name": "상법", "abbrev": None, "type": "법률"},
            {"id": "001444", "full_name": "대한민국헌법", "abbrev": "헌법", "type": "헌법"},
            {"id": "001700", "full_name": "민사소송법", "abbrev": None, "type": "법률"},
            {"id": "001671", "full_name": "형사소송법", "abbrev": None, "type": "법률"},
            {"id": "001218", "full_name": "행정소송법", "abbrev": None, "type": "법률"},
            {"id": "001362", "full_name": "행정절차법", "abbrev": None, "type": "법률"},
            {"id": "001586", "full_name": "국세기본법", "abbrev": None, "type": "법률"},
            {"id": "001565", "full_name": "소득세법", "abbrev": None, "type": "법률"},
            {"id": "001563", "full_name": "법인세법", "abbrev": None, "type": "법률"},
            {"id": "001872", "full_name": "근로기준법", "abbrev": None, "type": "법률"},
            {"id": "001823", "full_name": "건축법", "abbrev": None, "type": "법률"},
            {"id": "010513", "full_name": "자본시장과 금융투자업에 관한 법률", "abbrev": "자본시장법", "type": "법률"},
            {"id": "009294", "full_name": "국토의 계획 및 이용에 관한 법률", "abbrev": "국토계획법", "type": "법률"},
            {"id": "001638", "full_name": "도로교통법", "abbrev": None, "type": "법률"},
            {"id": "011357", "full_name": "개인정보 보호법", "abbrev": None, "type": "법률"},
            {"id": "001827", "full_name": "부동산 가격공시에 관한 법률", "abbrev": "부동산공시법", "type": "법률"},
            {"id": "009290", "full_name": "민사집행법", "abbrev": None, "type": "법률"},
            {"id": "001676", "full_name": "특정범죄 가중처벌 등에 관한 법률", "abbrev": "특정범죄가중법", "type": "법률"},
        ]
        for entry in seed:
            _law_cache[entry["full_name"]] = entry
            if entry["abbrev"]:
                _law_cache[entry["abbrev"]] = entry

    _seed_cache()

    def _cache_law(full_name: str, law_id: str, abbrev: str | None, law_type: str) -> None:
        """Add a law to the cache (called after search results are ranked)."""
        if not full_name or not law_id:
            return
        entry = {
            "id": str(law_id),
            "full_name": full_name,
            "abbrev": abbrev or None,
            "type": law_type,
        }
        _law_cache[full_name] = entry
        if entry["abbrev"]:
            _law_cache[entry["abbrev"]] = entry

    @server.resource(
        "lexlink://laws/frequently-used",
        name="frequently-used-laws",
        description="Cached mapping of frequently-used Korean law names to their stable 법령ID codes. Use these IDs directly with eflaw_service, law_service, etc. to skip the search step.",
        mime_type="application/json",
    )
    def get_frequently_used_laws() -> str:
        """Return deduplicated list of all cached law entries as JSON."""
        import json
        # Deduplicate by id (abbrev keys point to same entry)
        seen_ids: set[str] = set()
        unique: list[dict] = []
        for entry in _law_cache.values():
            if entry["id"] not in seen_ids:
                seen_ids.add(entry["id"])
                unique.append(entry)
        return json.dumps(unique, ensure_ascii=False, indent=2)

    @server.resource(
        "lexlink://law/{name}",
        name="law-code-lookup",
        description="Look up a specific Korean law's stable 법령ID by name (Korean). Replace {name} with the plain name, no braces (e.g. lexlink://law/자통법). Returns the law's ID, full name, abbreviation, and type. If not found, use eflaw_search or law_search tool instead.",
        mime_type="application/json",
    )
    def get_law_by_name(name: str) -> str:
        """Look up a law by name or abbreviation.

        Resolution order:
          1. URL-decode the template value (clients send percent-encoded Korean)
          2. Frequently-used cache (full names + abbreviations, plus names learned
             from eflaw_search/law_search results)
          3. resolver.py seed/learned aliases (자통법 → 자본시장과 금융투자업에 관한 법률)
          4. Live law_search lookup (1 upstream call) when OC is configured
        """
        import json
        raw_name = name
        name = unquote(name or "").strip()
        if not name:
            return json.dumps(
                {"error": "invalid_name", "message": "Law name is empty. Use lexlink://law/{한글 법령명 또는 약칭}."},
                ensure_ascii=False,
            )

        def _found(entry: dict, resolved_from: Optional[str] = None) -> str:
            out = dict(entry)
            out["query"] = name
            if resolved_from and resolved_from != name:
                out["resolved_from"] = resolved_from
            return json.dumps(out, ensure_ascii=False, indent=2)

        # 2) direct cache hit (full name or abbreviation)
        if entry := _law_cache.get(name):
            return _found(entry)

        # 3) alias resolution (seed + learned) → cache / learned IDs
        resolver = get_resolver()
        resolved = resolver.resolve(name)
        if resolved != name and (entry := _law_cache.get(resolved)):
            return _found(entry, resolved_from=resolved)
        for candidate in dict.fromkeys((resolved, name)):
            if law_id := resolver.get_law_id(candidate):
                _cache_law(candidate, law_id, None, "")
                return _found(_law_cache[candidate], resolved_from=resolved)

        # 4) live lookup via law_search (공포일 기준 현행법령 목록), exact-name match only
        lookup_error: Optional[str] = None
        try:
            resolved_oc = resolve_oc(override_oc=None)
            snake_params = {
                "oc": resolved_oc, "target": "law", "type": "JSON",
                "query": resolved, "display": 20, "page": 1,
            }
            result = run_search(
                get_client=_get_client, target="law", query=resolved,
                snake_params=snake_params, response_type="JSON", display=20,
                ranking_field="법령명한글", list_type="law",
                over_fetch_key="numOfRows", over_fetch=False,
            )
            if result.get("status") == "ok":
                data = result.get("ranked_data")
                if data is None and result.get("raw_content"):
                    try:
                        parsed = json.loads(result["raw_content"])
                        data = list(parsed.values())[0] if parsed else None
                    except (ValueError, IndexError):
                        data = None
                laws = extract_law_list(data) if isinstance(data, dict) else []
                wanted = {resolved.replace(" ", ""), name.replace(" ", "")}
                for law in laws:
                    full = (law.get("법령명한글") or "").strip()
                    abbrev = (law.get("법령약칭명") or "").strip()
                    if full.replace(" ", "") in wanted or (abbrev and abbrev.replace(" ", "") in wanted):
                        _cache_law(full, law.get("법령ID", ""), abbrev or None, law.get("법령구분명", ""))
                        if full in _law_cache:
                            return _found(_law_cache[full], resolved_from=resolved)
            else:
                lookup_error = result.get("message") or result.get("error_code")
        except Exception as e:  # OC missing, network error, ... → fall through to not_found
            lookup_error = str(e)
            logger.info(f"Resource lookup for '{name}' fell back to not_found: {e}")

        payload = {
            "error": "not_found",
            "query": name,
            "message": f"'{name}' not found in cache, aliases, or law_search exact-name match. "
                       "Use eflaw_search or law_search tool with a broader query.",
        }
        if resolved != name:
            payload["resolved_as"] = resolved
        if raw_name != name:
            payload["decoded_from"] = raw_name
        if lookup_error:
            payload["lookup_error"] = lookup_error
        return json.dumps(payload, ensure_ascii=False, indent=2)

    # ==================== TOOL 1: eflaw_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def eflaw_search(
        query: str,
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        sort: Optional[str] = None,
        ef_yd: Annotated[Optional[str], Field(description="시행일자(YYYYMMDD) 범위 필터 'YYYYMMDD~YYYYMMDD'. 시행일자가 이 범위에 드는 법령 행만 나열한다 (단일 날짜는 거부). '그 날 시행 중인 법령'이 아니다 → 기준일 시점 조회는 law_as_of. Range filter on 시행일자, NOT 'in force on D'.")] = None,
        org: Optional[str] = None,
        knd: Optional[str] = None,
        nw: Annotated[Optional[str], Field(description="상태 필터(쉼표 구분): 1=연혁(과거), 2=현행, 3=시행예정. 예: '1,2,3'. 생략하면 현행 행만. Version status filter; omit = 현행 only.")] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search laws listed by 시행일 (시행일 기준 법령 목록 검색). ef_yd is a 시행일 RANGE filter (YYYYMMDD~YYYYMMDD), NOT "in force on D": for the law/article text as of a date D use law_as_of.

        Lists 현행 rows by default; pass nw="1,2,3" to include 연혁 (past) and 시행예정 (scheduled) versions.

        Args:
            query: Search keyword (law name or content)
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"|"efasc"|"efdes"
            ef_yd: RANGE FILTER on each law row's 시행일자 (YYYYMMDD~YYYYMMDD, e.g., "20240101~20241231");
                a single date is rejected. Lists laws whose enforcement date falls inside the range; it is NOT
                "the version in force on a day" (for that use law_as_of). Only 현행-status rows are searched.
            org: Ministry/department code filter
            knd: Law type filter
            nw: Status filter, comma separated: 1=연혁, 2=현행, 3=시행예정 (e.g. "1,2,3"; default 현행 only)

        Returns:
            Search results with law list or error

        Examples:
            Search for "자동차관리법":
            >>> eflaw_search(query="자동차관리법", display=10, type="JSON")

            Search with date range:
            >>> eflaw_search(
            ...     query="자동차",
            ...     ef_yd="20240101~20241231",
            ...     type="JSON"
            ... )
        """
        resolved_oc = resolve_oc(override_oc=oc)
        if ef_yd:
            validate_date_range(ef_yd, "ef_yd")
        if nw is not None and nw != "" and not re.fullmatch(r"[123](,[123])*", str(nw).replace(" ", "")):
            raise ValueError("nw must be a comma separated subset of 1,2,3 (1=연혁, 2=현행, 3=시행예정), e.g. '1,2,3'")
        snake_params = {
            "oc": resolved_oc, "target": "eflaw", "type": type,
            "query": query, "display": display, "page": page,
        }
        if nw: snake_params["nw"] = str(nw).replace(" ", "")
        if sort: snake_params["sort"] = sort
        if ef_yd: snake_params["ef_yd"] = ef_yd
        if org: snake_params["org"] = org
        if knd: snake_params["knd"] = knd

        def cache_top_results(ranked_laws):
            for law in ranked_laws[:3]:
                _cache_law(
                    full_name=law.get("법령명한글", ""),
                    law_id=law.get("법령ID", ""),
                    abbrev=law.get("법령약칭명") or None,
                    law_type=law.get("법령구분명", ""),
                )

        return run_search(
            get_client=_get_client, target="eflaw", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="법령명한글", list_type="law",
            over_fetch_key="numOfRows", post_rank_hook=cache_top_results,
        )

    # ==================== TOOL 2: law_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def law_search(
        query: str,
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        sort: Optional[str] = None,
        date: Optional[int] = None,
        org: Optional[str] = None,
        knd: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search current laws by announcement date (공포일 기준 현행법령 검색).

        This tool searches Korean laws organized by announcement (publication) date.

        Args:
            query: Search keyword (law name or content)
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            sort: Sort order
            date: Announcement date (YYYYMMDD)
            org: Ministry/department code filter
            knd: Law type filter

        Returns:
            Search results with law list or error
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "law", "type": type,
            "query": query, "display": display, "page": page,
        }
        if sort: snake_params["sort"] = sort
        if date: snake_params["date"] = date
        if org: snake_params["org"] = org
        if knd: snake_params["knd"] = knd

        def cache_top_results(ranked_laws):
            for law in ranked_laws[:3]:
                _cache_law(
                    full_name=law.get("법령명한글", ""),
                    law_id=law.get("법령ID", ""),
                    abbrev=law.get("법령약칭명") or None,
                    law_type=law.get("법령구분명", ""),
                )

        return run_search(
            get_client=_get_client, target="law", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="법령명한글", list_type="law",
            over_fetch_key="numOfRows", post_rank_hook=cache_top_results,
        )

    # ==================== TOOL 3: eflaw_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def eflaw_service(
        id: Annotated[Optional[Union[str, int]], Field(description="법령ID. id만 주면 항상 '현재' 시행본이며 시행일을 고를 수 없다. 특정 날짜 시점 본문은 law_as_of 사용. Law ID: returns the CURRENT revision only.")] = None,
        mst: Annotated[Optional[Union[str, int]], Field(description="법령일련번호(MST; eflaw_search / law_amendment_summary / law_as_of 결과의 mst). 특정 개정본을 지정한다. Revision serial number.")] = None,
        ef_yd: Annotated[Optional[Union[str, int]], Field(description="시행일자 YYYYMMDD. 사건일/기준일이 아니다. 반드시 mst와 함께 쓰고 그 MST 자신의 시행일자 중 하나와 정확히 일치해야 한다(불일치 시 오류). id와 함께 주면 upstream이 무시하거나 빈 응답을 주므로 이 도구는 VALIDATION_ERROR를 돌려준다. 'D일 당시 본문'은 law_as_of(law_name, as_of=D). NOT the incident date; must equal the MST's own 시행일.")] = None,
        jo: Optional[Union[str, int]] = None,
        chr_cls_cd: Optional[str] = None,
        lm: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve ONE revision's law text (시행일 기준 법령 본문 조회). ef_yd must be that mst's own 시행일, NOT the incident date; for the text in force on a date D use law_as_of.

        Retrieves the complete text of the revision identified by mst + ef_yd (id alone = the current revision).

        **IMPORTANT: For specific article queries (e.g., "제174조"), ALWAYS use the `jo` parameter.
        Some laws (e.g., 자본시장법) have 400+ articles and the full response can exceed 1MB.
        Using `jo` returns only the requested article, which is much faster and cleaner.**

        Args:
            id: Law ID (either id, mst or lm is required)
            mst: Law serial number (MST/lsi_seq)
            ef_yd: 시행일자 (YYYYMMDD) that SELECTS one revision of the given MST; it must equal one of that
                MST's own 시행일자 (see law_as_of / law_amendment_summary), otherwise upstream returns an error
                page. It is NOT "in force on this date": an incident date here gives an error or the wrong
                revision. For "as of date D" use law_as_of. Accepts int or str.
            lm: Law name (alternative to id/mst)
            jo: **REQUIRED for specific articles.** Article number. Accepts 35, "35", "35의5",
                "제35조의5", "35-5" or the 6-digit code "003505" (all normalized to XXXXXX:
                first 4 digits = article number zero-padded, last 2 digits = branch suffix, 00=main).
                Examples: "017400" (제174조), "000300" (제3조), "001502" (제15조의2), "15의2" (제15조의2)
                If the article does not exist, a structured ARTICLE_NOT_FOUND error is returned.
            chr_cls_cd: Language code - "010202" (Korean, default) or "010201" (Original)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Full law content or specific article content

        Examples:
            Retrieve specific article (RECOMMENDED):
            >>> eflaw_service(mst="279823", jo="017400", type="XML")  # 자본시장법 제174조

            Retrieve full law (WARNING: large response for some laws):
            >>> eflaw_service(id="1747", type="XML")
        """
        (id, mst, jo) = stringify_id(id, mst, jo)
        resolved_oc = resolve_oc(override_oc=oc)
        if not id and not mst and not lm:
            raise ValueError("One of 'id', 'mst' or 'lm' parameter is required")
        if mst and not id and not ef_yd:
            # Upstream answers MST-only eflaw requests with the misleading
            # "미신청" page; ef_yd is what it actually needs.
            raise ValueError(
                "'ef_yd' (effective date, YYYYMMDD) is required when using 'mst' without 'id'. "
                "Take it from eflaw_search (시행일자) or pass 'id' instead."
            )
        if ef_yd and not mst and not lm:
            raise ToolValidationError(
                "ef_yd는 mst와 함께만 유효합니다. id와 함께 주면 upstream이 ef_yd를 무시하거나 빈 응답을 돌려줍니다.",
                hints=["특정 날짜(D) 시점의 본문/조문은 law_as_of(law_name, as_of=D, article=...)를 사용하세요.",
                       "특정 개정본은 mst와 그 MST 자신의 시행일자를 ef_yd로 함께 지정하세요 (law_amendment_summary / law_as_of 결과)."],
            )
        jo = _normalize_jo_arg(jo)
        snake_params = {"oc": resolved_oc, "target": "eflaw", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if lm: snake_params["lm"] = lm
        if ef_yd: snake_params["ef_yd"] = ef_yd
        if jo: snake_params["jo"] = jo
        if chr_cls_cd: snake_params["chr_cls_cd"] = chr_cls_cd
        response = run_service(get_client=_get_client, target="eflaw",
                               snake_params=snake_params, response_type=type)
        return _check_article_present(response, jo, type)

    # ==================== TOOL 4: law_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def law_service(
        id: Annotated[Optional[Union[str, int]], Field(description="법령ID. id만 주면 항상 '현재' 시행본이며 시행일을 고를 수 없다. 특정 날짜 시점 본문은 law_as_of 사용. Law ID: returns the CURRENT revision only.")] = None,
        mst: Annotated[Optional[Union[str, int]], Field(description="법령일련번호(MST; eflaw_search / law_amendment_summary / law_as_of 결과의 mst). 특정 개정본을 지정한다. Revision serial number.")] = None,
        lm: Annotated[Optional[str], Field(description="법령명 보조 파라미터(거의 불필요). Law-name helper; not a date selector.")] = None,
        ld: Annotated[Optional[int], Field(description="공포일자 YYYYMMDD(ln과 함께). 날짜 시점 선택용이 아니며 id와 함께 쓰면 upstream이 무시한다(현재본 반환). 'D일 당시 본문'은 law_as_of. NOT an as-of-date selector.")] = None,
        ln: Annotated[Optional[int], Field(description="공포번호(ld와 함께). 날짜 시점 선택용이 아님. Announcement number, not a date selector.")] = None,
        jo: Optional[Union[str, int]] = None,
        lang: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve full law text (공포일 기준 법령 본문 조회): id = current revision, mst = that revision. It cannot select by date; for the law/article in force on a date D use law_as_of.

        Retrieves the complete text of a law (current revision via id, a specific revision via mst).

        **IMPORTANT: For specific article queries (e.g., "제174조"), ALWAYS use the `jo` parameter.
        Some laws (e.g., 자본시장법) have 400+ articles and the full response can exceed 1MB.
        Using `jo` returns only the requested article, which is much faster and cleaner.**

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            lm: Law modification parameter
            ld: Law date parameter (YYYYMMDD)
            ln: Law number parameter
            jo: **REQUIRED for specific articles.** Article number. Accepts 35, "35", "35의5",
                "제35조의5", "35-5" or the 6-digit code "003505" (all normalized to XXXXXX:
                first 4 digits = article number zero-padded, last 2 digits = branch suffix, 00=main).
                Examples: "017400" (제174조), "000300" (제3조), "001502" (제15조의2), "15의2" (제15조의2)
                If the article does not exist, a structured ARTICLE_NOT_FOUND error is returned.
            lang: Language - "KO" (Korean) or "ORI" (Original)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Full law content or specific article content

        Examples:
            Retrieve specific article (RECOMMENDED):
            >>> law_service(mst="279823", jo="017400", type="XML")  # 자본시장법 제174조

            Retrieve full law (WARNING: large response for some laws):
            >>> law_service(id="009682", type="XML")
        """
        (id, mst, jo) = stringify_id(id, mst, jo)
        resolved_oc = resolve_oc(override_oc=oc)
        if not id and not mst and not lm:
            raise ValueError("One of 'id', 'mst' or 'lm' parameter is required")
        jo = _normalize_jo_arg(jo)
        snake_params = {"oc": resolved_oc, "target": "law", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if lm: snake_params["lm"] = lm
        if ld: snake_params["ld"] = ld
        if ln: snake_params["ln"] = ln
        if jo: snake_params["jo"] = jo
        if lang: snake_params["lang"] = lang
        response = run_service(get_client=_get_client, target="law",
                               snake_params=snake_params, response_type=type)
        return _check_article_present(response, jo, type)

    # ==================== TOOL 5: eflaw_josub ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def eflaw_josub(
        id: Annotated[Optional[Union[str, int]], Field(description="법령ID. id만 주면 항상 '현재' 시행본이며 시행일을 고를 수 없다. 특정 날짜 시점 본문은 law_as_of 사용. Law ID: returns the CURRENT revision only.")] = None,
        mst: Annotated[Optional[Union[str, int]], Field(description="법령일련번호(MST; eflaw_search / law_amendment_summary / law_as_of 결과의 mst). 특정 개정본을 지정한다. Revision serial number.")] = None,
        ef_yd: Annotated[Optional[Union[str, int]], Field(description="시행일자 YYYYMMDD. 사건일/기준일이 아니다. 반드시 mst와 함께 쓰고 그 MST 자신의 시행일자 중 하나와 정확히 일치해야 한다(불일치 시 오류). id와 함께 주면 upstream이 무시하거나 빈 응답을 주므로 이 도구는 VALIDATION_ERROR를 돌려준다. 'D일 당시 본문'은 law_as_of(law_name, as_of=D). NOT the incident date; must equal the MST's own 시행일.")] = None,
        jo: Optional[Union[str, int]] = None,
        hang: Optional[str] = None,
        ho: Optional[str] = None,
        mok: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Query one article/paragraph of ONE revision (시행일 기준 조·항·호·목 조회). ef_yd must be that mst's own 시행일, NOT the incident date; for the article in force on a date D use law_as_of.

        **BEST TOOL for querying specific articles like "제174조", "제3조" etc.**
        This returns only the requested article/paragraph, avoiding large full-law responses.

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            ef_yd: 시행일자 (YYYYMMDD) that SELECTS one revision of the given MST; it must equal one of that
                MST's own 시행일자 (see law_as_of / law_amendment_summary), otherwise upstream returns an error
                page. It is NOT "in force on this date": an incident date here gives an error or the wrong
                revision. For "as of date D" use law_as_of. Accepts int or str.
            jo: Article number. Accepts 35, "35", "35의5", "제35조의5", "35-5" or the 6-digit
                code "003505" (all normalized to XXXXXX: first 4 digits = article number zero-padded,
                last 2 digits = branch suffix, 00=main).
                Examples: "017400" (제174조), "000300" (제3조), "001502" (제15조의2), "15의2" (제15조의2)
                If the article does not exist, a structured ARTICLE_NOT_FOUND error is returned.
            hang: Paragraph number (6 digits, e.g., "000100" for 제1항)
            ho: Item number (6 digits, e.g., "000200" for 제2호)
            mok: Subitem (UTF-8 encoded, e.g., "다" for 다목)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Specific law section content

        Examples:
            Query 자본시장법 제174조:
            >>> eflaw_josub(mst="279823", jo="017400", type="XML")

            Query 건축법 제3조 제1항:
            >>> eflaw_josub(mst="276925", jo="000300", hang="000100", type="XML")
        """
        (id, mst, jo) = stringify_id(id, mst, jo)
        resolved_oc = resolve_oc(override_oc=oc)
        if not id and not mst:
            raise ValueError("Either 'id' or 'mst' parameter is required")
        if ef_yd and not mst:
            raise ToolValidationError(
                "ef_yd는 mst와 함께만 유효합니다. id와 함께 주면 upstream이 ef_yd를 무시하거나 빈 응답을 돌려줍니다.",
                hints=["특정 날짜(D) 시점의 본문/조문은 law_as_of(law_name, as_of=D, article=...)를 사용하세요.",
                       "특정 개정본은 mst와 그 MST 자신의 시행일자를 ef_yd로 함께 지정하세요 (law_amendment_summary / law_as_of 결과)."],
            )
        jo = _normalize_jo_arg(jo)
        snake_params = {"oc": resolved_oc, "target": "eflawjosub", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if ef_yd: snake_params["ef_yd"] = ef_yd
        if jo: snake_params["jo"] = jo
        if hang: snake_params["hang"] = hang
        if ho: snake_params["ho"] = ho
        if mok: snake_params["mok"] = mok
        response = run_service(get_client=_get_client, target="eflawjosub",
                               snake_params=snake_params, response_type=type)
        return _check_article_present(response, jo, type)

    # ==================== TOOL 6: law_josub ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def law_josub(
        id: Annotated[Optional[Union[str, int]], Field(description="법령ID. id만 주면 항상 '현재' 시행본이며 시행일을 고를 수 없다. 특정 날짜 시점 본문은 law_as_of 사용. Law ID: returns the CURRENT revision only.")] = None,
        mst: Annotated[Optional[Union[str, int]], Field(description="법령일련번호(MST; eflaw_search / law_amendment_summary / law_as_of 결과의 mst). 특정 개정본을 지정한다. Revision serial number.")] = None,
        jo: Optional[Union[str, int]] = None,
        hang: Optional[str] = None,
        ho: Optional[str] = None,
        mok: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Query one article/paragraph (공포일 기준 조·항·호·목 조회): id = current revision, mst = that revision. It cannot select by date; for the article in force on a date D use law_as_of.

        **BEST TOOL for querying specific articles like "제174조", "제3조" etc.**
        This returns only the requested article/paragraph, avoiding large full-law responses.

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            jo: Article number. Accepts 35, "35", "35의5", "제35조의5", "35-5" or the 6-digit
                code "003505" (all normalized to XXXXXX: first 4 digits = article number zero-padded,
                last 2 digits = branch suffix, 00=main).
                Examples: "017400" (제174조), "000300" (제3조), "001502" (제15조의2), "15의2" (제15조의2)
                If the article does not exist, a structured ARTICLE_NOT_FOUND error is returned.
            hang: Paragraph number (6 digits, e.g., "000100" for 제1항)
            ho: Item number (6 digits, e.g., "000200" for 제2호)
            mok: Subitem (UTF-8 encoded, e.g., "다" for 다목)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Specific law section content

        Examples:
            Query 자본시장법 제174조:
            >>> law_josub(mst="279823", jo="017400", type="XML")

            Query 건축법 제3조 제1항:
            >>> law_josub(mst="276925", jo="000300", hang="000100", type="XML")
        """
        (id, mst, jo) = stringify_id(id, mst, jo)
        resolved_oc = resolve_oc(override_oc=oc)
        if not id and not mst:
            raise ValueError("Either 'id' or 'mst' parameter is required")
        jo = _normalize_jo_arg(jo)
        snake_params = {"oc": resolved_oc, "target": "lawjosub", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if jo: snake_params["jo"] = jo
        if hang: snake_params["hang"] = hang
        if ho: snake_params["ho"] = ho
        if mok: snake_params["mok"] = mok
        response = run_service(get_client=_get_client, target="lawjosub",
                               snake_params=snake_params, response_type=type)
        return _check_article_present(response, jo, type)

    # ==================== TOOL 7: elaw_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def elaw_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        sort: Optional[str] = None,
        ef_yd: Optional[str] = None,
        org: Optional[str] = None,
        knd: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search English-translated Korean laws (영문법령 목록 조회).

        This tool searches Korean laws that have been translated to English.
        Useful for international users or bilingual legal research.

        Args:
            query: Search keyword (Korean or English, default "*")
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"|"efasc"|"efdes"
            ef_yd: Effective date range (YYYYMMDD~YYYYMMDD)
            org: Ministry/department code filter
            knd: Law type filter
            ctx: MCP context (injected automatically)

        Returns:
            Search results with English law list or error

        Examples:
            Search for "insurance":
            >>> elaw_search(query="insurance", display=10, type="XML")

            Search for "가정폭력방지":
            >>> elaw_search(query="가정폭력방지", type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)

        # Validate date range if provided
        if ef_yd:
            validate_date_range(ef_yd, "ef_yd")

        # Build parameters
        params = {
            "oc": resolved_oc,
            "target": "elaw",
            "query": query,
            "display": display,
            "page": page,
        }

        # Add optional parameters
        if sort:
            params["sort"] = sort
        if ef_yd:
            params["ef_yd"] = ef_yd
        if org:
            params["org"] = org
        if knd:
            params["knd"] = knd

        page, display = validate_paging(page, display)
        params["page"], params["display"] = page, display

        # Map to upstream format
        upstream_params = map_params_to_upstream(params)

        original_display = display
        ranking_enabled = (type in ("XML", "JSON") and should_apply_ranking(query))
        use_paging = ranking_enabled and display < OVER_FETCH_WINDOW
        applied = None

        def _fetch(p: dict) -> dict:
            return _get_client().get("/DRF/lawSearch.do", p, response_type=type)

        def _load(resp: dict):
            raw_content = resp.get("raw_content", "")
            if not raw_content:
                return None
            if type == "JSON":
                import json as _json
                try:
                    _jd = _json.loads(raw_content)
                    parsed = list(_jd.values())[0] if _jd else None
                except (ValueError, IndexError):
                    parsed = None
            else:
                parsed = parse_xml_response(raw_content)
            if not parsed:
                return None
            laws = extract_law_list(parsed)
            # Upstream wraps matched keywords, e.g. NURSING <strong class="tbl_tx_type">ACT</strong>
            from .article_text import strip_html
            for law in laws:
                for key, value in law.items():
                    if isinstance(value, str) and "<" in value:
                        law[key] = strip_html(value)
            return parsed, laws

        def _rank(laws: list) -> list:
            # elaw target accepts both Korean and English queries, so detect language
            # Korean query "가정폭력방지" -> rank by 법령명한글; English -> 법령명영문
            name_field = "법령명영문" if detect_query_language(query) == "english" else "법령명한글"
            if laws and name_field not in laws[0]:
                name_field = "법령명한글" if name_field == "법령명영문" else "법령명영문"
            return rank_search_results(laws, query, name_field)

        if use_paging:
            response, parsed_data, rows, applied = run_ranked_paging(
                fetch=_fetch, upstream_params=upstream_params, page=page, display=display,
                over_fetch_key="numOfRows", response_type=type, load=_load, rank=_rank,
            )
            if parsed_data is not None:
                parsed_data = update_law_list(parsed_data, rows)
                parsed_data["numOfRows"] = str(original_display)
                parsed_data["page"] = str(page)
                response["ranked_data"] = parsed_data
        else:
            response = _fetch(upstream_params)
            if response.get("status") == "ok" and ranking_enabled:
                loaded = _load(response)
                if loaded and loaded[1]:
                    parsed_data = update_law_list(loaded[0], _rank(loaded[1])[:original_display])
                    parsed_data["numOfRows"] = str(original_display)
                    parsed_data["page"] = str(page)
                    response["ranked_data"] = parsed_data
                elif loaded:
                    response["ranked_data"] = loaded[0]  # empty page: still expose it

        if applied is not None:
            response["ranking_applied"] = applied
        add_no_more_results_hint(response, page, display)
        add_no_results_guidance(response)
        if ranking_enabled:
            trim_raw_to_ranked(response, type)
        rename_row_ids_to_rank(response)
        return slim_response(response)

    # ==================== TOOL 8: elaw_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def elaw_service(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        lm: Optional[str] = None,
        ld: Optional[int] = None,
        ln: Optional[int] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve English law full text (영문법령 본문 조회).

        This tool retrieves the complete text of Korean laws translated to English.
        Useful for international legal research and cross-border understanding.

        ⚠️ 응답이 클 수 있고 크기 제어 옵션 없음.

        Args:
            id: Law ID (required if mst not provided)
            mst: Law master number (required if id not provided)
            lm: Korean law name (exact; English names do not match). Alone it is enough
                (alternative to id/mst).
            ld: Announcement date (YYYYMMDD)
            ln: Announcement number
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full English law text with articles or error

        Examples:
            Retrieve by ID:
            >>> elaw_service(id="000744", type="XML")

            Retrieve by MST:
            >>> elaw_service(mst="127280", type="XML")
        """
        (id, mst) = stringify_id(id, mst)
        if not id and not mst and not lm:
            raise ValueError("One of 'id', 'mst' or 'lm' parameter is required")
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "elaw", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if lm: snake_params["lm"] = lm
        if ld: snake_params["ld"] = ld
        if ln: snake_params["ln"] = ln
        return run_service(get_client=_get_client, target="elaw",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 9: admrul_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def admrul_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        nw: int = 1,
        search: int = 1,
        org: Optional[str] = None,
        knd: Optional[str] = None,
        date: Optional[int] = None,
        prml_yd: Optional[str] = None,
        mod_yd: Optional[str] = None,
        sort: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search administrative rules (행정규칙 목록 조회).

        This tool searches Korean administrative rules including 훈령, 예규, 고시, 공고, 지침, etc.
        Administrative rules are detailed regulations issued by government agencies.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            nw: 1=현행 (current), 2=연혁 (historical), default 1
            search: 1=규칙명 (rule name), 2=본문검색 (full text), default 1
            org: Ministry/department code filter
            knd: Rule type - 1=훈령, 2=예규, 3=고시, 4=공고, 5=지침, 6=기타
            date: Promulgation date (YYYYMMDD)
            prml_yd: Promulgation date range (YYYYMMDD~YYYYMMDD)
            mod_yd: Modification date range (YYYYMMDD~YYYYMMDD)
            sort: Sort order
            ctx: MCP context (injected automatically)

        Returns:
            Search results with administrative rules list or error

        Examples:
            Search for "학교":
            >>> admrul_search(query="학교", display=10, type="XML")

            Search by date:
            >>> admrul_search(date=20250501, type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        if prml_yd:
            validate_date_range(prml_yd, "prml_yd")
        if mod_yd:
            validate_date_range(mod_yd, "mod_yd")
        snake_params = {
            "oc": resolved_oc, "target": "admrul", "query": query,
            "display": display, "page": page, "nw": nw, "search": search,
            "type": type,
        }
        if org: snake_params["org"] = org
        if knd: snake_params["knd"] = knd
        if date: snake_params["date"] = date
        if prml_yd: snake_params["prml_yd"] = prml_yd
        if mod_yd: snake_params["mod_yd"] = mod_yd
        if sort: snake_params["sort"] = sort
        return run_search(
            get_client=_get_client, target="admrul", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="행정규칙명", list_type="admrul",
            over_fetch_key="numOfRows",
        )

    # ==================== TOOL 10: admrul_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def admrul_service(
        id: Optional[Union[str, int]] = None,
        lid: Optional[Union[str, int]] = None,
        lm: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve administrative rule full text (행정규칙 본문 조회).

        This tool retrieves the complete text of Korean administrative rules.
        Includes rule content, addenda, and annexes (forms/attachments).

        ⚠️ 응답이 클 수 있고 크기 제어 옵션 없음.

        Args:
            id: Rule sequence number (행정규칙일련번호; required if lid/lm not provided)
            lid: Rule ID (alternative to id)
            lm: Rule name (exact match search)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full administrative rule text with content and annexes or error

        Examples:
            Retrieve by ID:
            >>> admrul_service(id="62505", type="XML")

            Retrieve by LID:
            >>> admrul_service(lid="10000005747", type="XML")
        """
        (id, lid) = stringify_id(id, lid)
        if not id and not lid and not lm:
            raise ValueError("At least one of 'id', 'lid', or 'lm' is required")
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "admrul", "type": type}
        if id: snake_params["id"] = id
        if lid: snake_params["lid"] = lid
        if lm: snake_params["lm"] = lm
        return run_service(get_client=_get_client, target="admrul",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 11: lnkLs_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lnkLs_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        sort: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search laws linked to local ordinances (법령-자치법규 연계 목록 조회).

        This tool searches Korean laws that have linkages to local ordinances.
        Useful for understanding how national laws relate to local regulations.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"
            ctx: MCP context (injected automatically)

        Returns:
            Search results with linked laws list or error

        Examples:
            Search for "자동차관리법":
            >>> lnkLs_search(query="자동차관리법", type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "lnkLs", "query": query,
            "display": display, "page": page,
            "type": type,
        }
        if sort: snake_params["sort"] = sort
        return run_search(
            get_client=_get_client, target="lnkLs", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="법령명한글", list_type="law",
            over_fetch_key="numOfRows", over_fetch=False,
        )

    # ==================== TOOL 12: lnkLsOrdJo_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lnkLsOrdJo_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        knd: Optional[str] = None,
        jo: Optional[Union[str, int]] = None,
        jobr: Optional[int] = None,
        sort: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search ordinance articles linked to law articles (연계 법령별 조례 조문 목록 조회).

        This tool searches local ordinance articles that are linked to specific
        national law articles. Shows which local ordinances implement or relate
        to specific law provisions.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            knd: Law type code (to filter by specific law)
            jo: Article number (4 digits, zero-padded). Examples: "0002" (Article 2), "0020" (Article 20), "0100" (Article 100)
            jobr: Branch article suffix (2 digits, zero-padded). Examples: "00" (main article), "02" (Article X-2)
            sort: Sort order
            ctx: MCP context (injected automatically)

        Returns:
            Search results with linked ordinance articles or error

        Examples:
            Search ordinances linked to 건축법 시행령:
            >>> lnkLsOrdJo_search(knd="002118", type="XML")

            Search specific article (제20조):
            >>> lnkLsOrdJo_search(knd="002118", jo=20, type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "lnkLsOrdJo", "query": query,
            "display": display, "page": page,
            "type": type,
        }
        if knd: snake_params["knd"] = knd
        if jo is not None:
            # Convert string to int if needed (LLMs may pass "0020" as string)
            jo_val = int(jo) if isinstance(jo, str) else jo
            snake_params["jo"] = jo_val
        if jobr is not None: snake_params["jobr"] = jobr
        if sort: snake_params["sort"] = sort
        return run_search(
            get_client=_get_client, target="lnkLsOrdJo", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 13: lnkDep_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lnkDep_search(
        org: str,
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        sort: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search law-ordinance links by ministry (연계 법령 소관부처별 목록 조회).

        This tool searches local ordinances linked to laws managed by a specific
        government ministry or department.

        Args:
            org: Ministry/department code (required, e.g., "1400000")
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            sort: Sort order
            ctx: MCP context (injected automatically)

        Returns:
            Search results with ministry's linked ordinances or error

        Examples:
            Search ordinances linked to ministry 1400000:
            >>> lnkDep_search(org="1400000", type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "lnkDep", "org": org,
            "display": display, "page": page,
            "type": type,
        }
        if sort: snake_params["sort"] = sort
        return run_search(
            get_client=_get_client, target="lnkDep", query=org,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 14: drlaw_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def drlaw_search(
        oc: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve law-ordinance linkage statistics (법령-자치법규 연계현황 조회).

        This tool retrieves statistical information about how national laws
        are linked to local ordinances. Returns HTML visualization/dashboard.

        ⚠️ Note: This API only supports HTML output format (no XML/JSON).
        Response schema is not documented by the API provider.

        Args:
            oc: Optional OC override (defaults to env var)
            ctx: MCP context (injected automatically)

        Returns:
            HTML response with linkage statistics or error

        Examples:
            Get linkage statistics:
            >>> drlaw_search()
        """
        resolved_oc = resolve_oc(override_oc=oc)
        params = {"oc": resolved_oc, "target": "drlaw"}
        upstream_params = map_params_to_upstream(params)
        client = _get_client()
        response = client.get("/DRF/lawSearch.do", upstream_params, response_type="HTML")
        if response.get("status") == "ok" and isinstance(response.get("raw_content"), str):
            from .linkage import parse_drlaw_html
            parsed = parse_drlaw_html(response["raw_content"])
            if parsed is not None:
                # The ~36KB HTML page is a rendered dashboard, not data: return the table instead.
                response = {k: v for k, v in response.items() if k != "raw_content"}
                response["parsed_data"] = parsed
                response["content_note"] = (
                    "원본 HTML 대시보드를 표로 파싱했습니다 (첫 페이지 기준: rows는 업스트림이 돌려준 "
                    f"{len(parsed['rows'])}건, total은 전체 건수). 조문별 자치법규수는 지자체별 건수입니다."
                )
        return response

    # ==================== TOOL 15: lsDelegated_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lsDelegated_service(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve delegated laws/rules/ordinances (위임 법령 조회).

        This tool retrieves information about laws, administrative rules, and
        local ordinances that are delegated by a parent law. Shows the delegation
        hierarchy and which specific articles delegate authority.

        ⚠️ Note: This API does NOT support HTML format (only XML/JSON).

        ⚠️ 응답이 클 수 있고 크기 제어 옵션 없음.

        Args:
            id: Law ID (required if mst not provided)
            mst: Law master number (required if id not provided)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default) or "XML" (HTML not available for this endpoint)
            ctx: MCP context (injected automatically)

        Returns:
            Delegation hierarchy with delegated laws/rules/ordinances or error

        Examples:
            Retrieve delegations for 초·중등교육법:
            >>> lsDelegated_service(id="000900", type="XML")
        """
        (id, mst) = stringify_id(id, mst)
        if not id and not mst:
            raise ValueError("Either 'id' or 'mst' parameter is required")
        if type.upper() == "HTML":
            logger.warning("lsDelegated_service does not support HTML format, using XML")
            type = "XML"
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "lsDelegated", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        response = run_service(get_client=_get_client, target="lsDelegated",
                               snake_params=snake_params, response_type=type)
        if slim_enabled() and response.get("status") == "ok" and response.get("raw_content"):
            # the raw payload is ~486KB; return the compact tree instead (size guard trims the rest)
            response = dict(response)
            response["delegation_tree"] = compact_delegation_tree(response.pop("raw_content"), type)
        return response

    # ==================== PHASE 3: CASE LAW & LEGAL RESEARCH ====================

    # ==================== TOOL 16: prec_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def prec_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        search: Optional[int] = None,
        sort: Optional[str] = None,
        org: Optional[str] = None,
        curt: Optional[str] = None,
        jo: Optional[str] = None,
        gana: Optional[str] = None,
        date: Optional[int] = None,
        prnc_yd: Optional[str] = None,
        nb: Optional[str] = None,
        dat_src_nm: Optional[str] = None,
        pop_yn: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search court precedents (판례 목록 조회).

        Search Korean court precedents from Supreme Court and lower courts.

        Args:
            query: Search keyword (default "*" for all)
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            search: Search type (1=case name, 2=full text, default 1)
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"
            org: Court type code (400201=Supreme Court, 400202=lower courts)
            curt: Court name (대법원, 서울고등법원, etc.)
            jo: Referenced law name (형법, 민법, etc.)
            gana: Dictionary search (ga, na, da, ...)
            date: Decision date (YYYYMMDD)
            prnc_yd: Decision date range (YYYYMMDD~YYYYMMDD)
            nb: Case number (comma-separated for multiple)
            dat_src_nm: Data source name (국세법령정보시스템, 근로복지공단산재판례, 대법원)
            pop_yn: Popup flag ("Y" or "N")

        Returns:
            Search results with precedent list or error.
            국세법령정보시스템 항목은 본문제공="API 미제공"; dat_src_nm 으로 출처 필터 가능.

        Examples:
            Search for precedents mentioning "담보권":
            >>> prec_search(query="담보권", display=10)

            Search Supreme Court precedents:
            >>> prec_search(query="담보권", curt="대법원")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "prec", "type": type,
            "query": query, "display": display, "page": page,
        }
        if search: snake_params["search"] = search
        if sort: snake_params["sort"] = sort
        if org: snake_params["org"] = org
        if curt: snake_params["curt"] = curt
        if jo: snake_params["jo"] = jo
        if gana: snake_params["gana"] = gana
        if date: snake_params["date"] = date
        if prnc_yd:
            validate_date_range(prnc_yd, "prnc_yd")
            snake_params["prnc_yd"] = prnc_yd
        if nb: snake_params["nb"] = nb
        if dat_src_nm: snake_params["dat_src_nm"] = dat_src_nm
        if pop_yn: snake_params["pop_yn"] = pop_yn
        return annotate_prec_body_availability(run_search(
            get_client=_get_client, target="prec", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="판례명", list_type="items", item_category="prec",
            over_fetch_key="display",
        ))

    # ==================== TOOL 17: prec_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def prec_service(
        id: Union[str, int],
        lm: Optional[str] = None,
        sections: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve court precedent full text (판례 본문 조회).

        Args:
            id: Precedent sequence number (판례일련번호, not the search row number)
            lm: Precedent name; must be the exact title and is only used without id
                (ignored when id is given, since a mismatch makes upstream report no match)
            sections: Response detail level:
                - "summary": Returns 판시사항, 판결요지, 참조조문, 참조판례 only (~5KB).
                  Excludes 판례내용 (full judgment text, often 15-25KB).
                  **Recommended for PlayMCP** to stay under 20KB limit.
                - "full" or None: Returns everything including 판례내용 (default).
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Full precedent text with details or error. Error NOT_FOUND when the
            body is unavailable (unknown id or source not served by the API).
            sections="summary" falls back to including 판례내용 when both 판시사항
            and 판결요지 are empty (sections="summary_fallback").

        Examples:
            >>> prec_service(id="228541")
            >>> prec_service(id="228541", sections="summary")  # PlayMCP-safe
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "prec",
            "id": str(id), "type": type,
        }
        if lm and not id: snake_params["lm"] = lm
        return run_service(get_client=_get_client, target="prec",
                          snake_params=snake_params, response_type=type,
                          sections=sections,
                          full_text_fields=["판례내용"],
                          summary_required_fields=["판시사항", "판결요지"])

    # ==================== TOOL 18: detc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def detc_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        search: Optional[int] = None,
        gana: Optional[str] = None,
        sort: Optional[str] = None,
        date: Optional[int] = None,
        ed_yd: Optional[str] = None,
        nb: Optional[int] = None,
        pop_yn: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search Constitutional Court decisions (헌재결정례 목록 조회).

        Search Korean Constitutional Court decisions.

        Args:
            query: Search keyword (default "*" for all)
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            search: Search type (1=decision name, 2=full text, default 1)
            gana: Dictionary search (ga, na, da, ...)
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"|"efasc"|"efdes"
            date: Final date (YYYYMMDD)
            ed_yd: Final date range (YYYYMMDD~YYYYMMDD)
            nb: Case number
            pop_yn: Popup flag ("Y" or "N")

        Returns:
            Search results with Constitutional Court decision list or error

        Examples:
            Search for decisions mentioning "벌금":
            >>> detc_search(query="벌금", display=10)

            Search by date:
            >>> detc_search(date=20150210)
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "detc", "type": type,
            "query": query, "display": display, "page": page,
        }
        if search: snake_params["search"] = search
        if gana: snake_params["gana"] = gana
        if sort: snake_params["sort"] = sort
        if date: snake_params["date"] = date
        if ed_yd:
            validate_date_range(ed_yd, "ed_yd")
            snake_params["ed_yd"] = ed_yd
        if nb: snake_params["nb"] = nb
        if pop_yn: snake_params["pop_yn"] = pop_yn
        return run_search(
            get_client=_get_client, target="detc", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="사건명", list_type="items", item_category="detc",
            over_fetch_key="display",
        )

    # ==================== TOOL 19: detc_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def detc_service(
        id: Union[str, int],
        lm: Optional[str] = None,
        sections: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve Constitutional Court decision full text (헌재결정례 본문 조회).

        Args:
            id: Constitutional Court decision sequence number (헌재결정례일련번호, not the search row number)
            lm: Decision name; must be the exact title and is only used without id
                (ignored when id is given, since a mismatch makes upstream report no match)
            sections: "summary" to exclude 전문 (full text), or "full"/None for everything.
                **Recommended: "summary" for PlayMCP** to stay under 20KB.
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Full Constitutional Court decision text or error

        Examples:
            >>> detc_service(id="58386")
            >>> detc_service(id="58386", sections="summary")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "detc",
            "id": str(id), "type": type,
        }
        if lm and not id: snake_params["lm"] = lm
        return run_service(get_client=_get_client, target="detc",
                          snake_params=snake_params, response_type=type,
                          sections=sections,
                          full_text_fields=["전문"])

    # ==================== TOOL 20: expc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def expc_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        search: int = 1,
        inq: Optional[str] = None,
        rpl: Optional[int] = None,
        gana: Optional[str] = None,
        itmno: Optional[int] = None,
        reg_yd: Optional[str] = None,
        expl_yd: Optional[str] = None,
        sort: Optional[str] = None,
        pop_yn: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search legal interpretations (법령해석례 목록 조회).

        This tool searches Korean legal interpretation precedents issued by government
        agencies in response to inquiries about how to interpret specific laws.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for searches to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            search: 1=법령해석례명 (interpretation name, default), 2=본문검색 (full text)
            inq: Inquiry organization name
            rpl: Reply organization code
            gana: Dictionary-style search (ga, na, da, ...)
            itmno: Item number (e.g., 13-0217 → 130217)
            reg_yd: Registration date range (YYYYMMDD~YYYYMMDD)
            expl_yd: Interpretation date range (YYYYMMDD~YYYYMMDD)
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"
            pop_yn: Popup mode - "Y" or "N"
            ctx: MCP context (injected automatically)

        Returns:
            Search results with legal interpretations list or error

        Examples:
            Search for "임차":
            >>> expc_search(query="임차", display=10, type="XML")

            Search by date range:
            >>> expc_search(query="자동차", expl_yd="20240101~20241231", type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        if reg_yd:
            validate_date_range(reg_yd, "reg_yd")
        if expl_yd:
            validate_date_range(expl_yd, "expl_yd")
        snake_params = {
            "oc": resolved_oc, "target": "expc", "type": type,
            "query": query, "display": display, "page": page,
            "search": search,
        }
        if inq: snake_params["inq"] = inq
        if rpl is not None: snake_params["rpl"] = rpl
        if gana: snake_params["gana"] = gana
        if itmno is not None: snake_params["itmno"] = itmno
        if reg_yd: snake_params["reg_yd"] = reg_yd
        if expl_yd: snake_params["expl_yd"] = expl_yd
        if sort: snake_params["sort"] = sort
        if pop_yn: snake_params["pop_yn"] = pop_yn
        return run_search(
            get_client=_get_client, target="expc", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="사건명", list_type="items", item_category="expc",
            over_fetch_key="display",
        )

    # ==================== TOOL 17: expc_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def expc_service(
        id: Union[str, int],
        lm: Optional[str] = None,
        sections: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve legal interpretation full text (법령해석례 본문 조회).

        This tool retrieves the complete text of a legal interpretation precedent,
        including the question summary, answer, and reasoning.

        Args:
            id: Legal interpretation sequence number (법령해석례일련번호, required; not the search row number)
            lm: Legal interpretation name (optional)
            sections: "summary" to exclude 이유 (detailed reasoning), or "full"/None for everything.
                Returns 안건명, 질의요지, 회답 in summary mode (~2KB vs ~5KB full).
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full legal interpretation text with question, answer, and reasoning or error

        Examples:
            Retrieve by ID:
            >>> expc_service(id="334617", type="XML")

            Retrieve with name:
            >>> expc_service(id="315191", lm="여성가족부 - 건강가정기본법 제35조 제2항 관련", type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "expc",
            "id": str(id), "type": type,
        }
        if lm: snake_params["lm"] = lm
        return run_service(get_client=_get_client, target="expc",
                          snake_params=snake_params, response_type=type,
                          sections=sections,
                          full_text_fields=["이유"])

    # ==================== TOOL 18: decc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def decc_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        search: int = 1,
        cls: Optional[str] = None,
        gana: Optional[str] = None,
        date: Optional[int] = None,
        dpa_yd: Optional[str] = None,
        rsl_yd: Optional[str] = None,
        sort: Optional[str] = None,
        pop_yn: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search administrative appeal decisions (행정심판례 목록 조회).

        This tool searches Korean administrative appeal decisions.
        Administrative appeals are decisions made by administrative tribunals
        on appeals against government agency dispositions.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            search: 1=사건명 (case name, default), 2=본문검색 (full text)
            cls: Decision type filter (재결구분코드)
            gana: Dictionary search (ga, na, da, ...)
            date: Decision date (YYYYMMDD)
            dpa_yd: Disposition date range (YYYYMMDD~YYYYMMDD)
            rsl_yd: Decision date range (YYYYMMDD~YYYYMMDD)
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"
            pop_yn: Popup flag - "Y" or "N"
            ctx: MCP context (injected automatically)

        Returns:
            Search results with administrative appeal decisions list or error

        Examples:
            Search for all decisions:
            >>> decc_search(type="XML")

            Search by keyword:
            >>> decc_search(query="과징금", display=10, type="XML")

            Search by date range:
            >>> decc_search(rsl_yd="20200101~20201231", type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        if dpa_yd:
            validate_date_range(dpa_yd, "dpa_yd")
        if rsl_yd:
            validate_date_range(rsl_yd, "rsl_yd")
        snake_params = {
            "oc": resolved_oc, "target": "decc", "type": type,
            "query": query, "display": display, "page": page,
            "search": search,
        }
        if cls: snake_params["cls"] = cls
        if gana: snake_params["gana"] = gana
        if date: snake_params["date"] = date
        if dpa_yd: snake_params["dpa_yd"] = dpa_yd
        if rsl_yd: snake_params["rsl_yd"] = rsl_yd
        if sort: snake_params["sort"] = sort
        if pop_yn: snake_params["pop_yn"] = pop_yn
        return run_search(
            get_client=_get_client, target="decc", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="사건명", list_type="items", item_category="decc",
            over_fetch_key="display",
        )

    # ==================== TOOL 19: decc_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def decc_service(
        id: Union[str, int],
        lm: Optional[str] = None,
        sections: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve administrative appeal decision full text (행정심판례 본문 조회).

        This tool retrieves the complete text of Korean administrative appeal decisions.
        Includes case details, disposition information, decision summary, and reasoning.

        Args:
            id: Administrative appeal decision sequence number (행정심판재결례일련번호, required; not the search row number)
            lm: Decision name (optional)
            sections: "summary" to exclude 이유 (detailed reasoning), or "full"/None for everything.
                Returns 사건명, 청구취지, 재결요지, 주문 in summary mode.
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full administrative appeal decision text with details or error

        Examples:
            Retrieve by ID:
            >>> decc_service(id="243263", type="XML")

            Retrieve with case name:
            >>> decc_service(id="245011", lm="과징금 부과처분 취소청구", type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "decc",
            "id": str(id), "type": type,
        }
        if lm: snake_params["lm"] = lm
        return run_service(get_client=_get_client, target="decc",
                          snake_params=snake_params, response_type=type,
                          sections=sections,
                          full_text_fields=["이유"])

    # ==================== PHASE 4: ARTICLE CITATION ====================

    # ==================== TOOL 24: article_citation ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    async def article_citation(
        mst: str,
        law_name: str,
        article: int,
        article_branch: int = 0,
        oc: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Extract citations from a law article (조문 인용 조회).

        This tool extracts all legal citations referenced by a specific law article.
        It parses the official hyperlinked citations from law.go.kr HTML pages,
        with zero API cost. "같은 법" and article lists are resolved heuristically
        (not guaranteed), so verify against the article text when it matters.

        The tool identifies:
        - External citations (references to other laws)
        - Internal citations (references within the same law)
        - Article, paragraph, and item level references

        Args:
            mst: Law MST code (법령일련번호) - get this from eflaw_search or law_search results
            law_name: Law name in Korean (e.g., "자본시장과 금융투자업에 관한 법률")
            article: Article number (조번호, e.g., 3 for 제3조)
            article_branch: Article branch number (조가지번호, e.g., 2 for 제37조의2, default 0)
            oc: Optional OC override (defaults to env var). With an OC, mst/law_name/article
                are verified against lawService first (mismatch -> VALIDATION_ERROR, missing
                article -> ARTICLE_NOT_FOUND); without one, verification is skipped and a
                warning is returned.

        Returns:
            Citation extraction result with:
            - success: Whether extraction succeeded
            - law_id: MST code
            - law_name: Law name
            - article: Article display (e.g., "제3조" or "제37조의2")
            - citation_count: Total number of citations found
            - citations: List of citation objects with target law, article, paragraph, item
            - internal_count: Number of same-law citations
            - external_count: Number of other-law citations

        Examples:
            Get citations from 자본시장법 제3조:
            >>> article_citation(
            ...     mst="268611",
            ...     law_name="자본시장과 금융투자업에 관한 법률",
            ...     article=3
            ... )

            Get citations from 건축법 제37조의2:
            >>> article_citation(
            ...     mst="270986",
            ...     law_name="건축법",
            ...     article=37,
            ...     article_branch=2
            ... )

        Workflow:
            1. First use eflaw_search(query="법명") to find the law and get MST
            2. Then use article_citation(mst=..., law_name=..., article=...) to get citations
            3. Optionally use eflaw_service to get the full article text
        """
        # Import citation extractor
        from .citation import extract_article_citations

        # Validate required parameters
        if not mst:
            raise ValueError("mst (법령일련번호) is required")
        if not law_name:
            raise ValueError("law_name (법령명) is required")
        if article <= 0:
            raise ValueError("article must be a positive integer")

        # Citation extraction scrapes HTML (no OC needed), but the mst/law_name/article
        # triple is only verifiable upstream with an OC (lawService MST+JO).
        warnings: list[str] = []
        try:
            resolved_oc = resolve_oc(override_oc=oc)
        except ValueError:
            resolved_oc = None
        if resolved_oc:
            error, verify_warnings = await asyncio.to_thread(
                _verify_citation_target, str(mst), law_name, article, article_branch, resolved_oc,
            )
            if error:
                return error
            warnings.extend(verify_warnings)
        else:
            warnings.append(NO_OC_CITATION_WARNING)

        # Extract citations
        result = await extract_article_citations(
            mst=str(mst),
            law_name=law_name,
            article=article,
            article_branch=article_branch
        )
        if warnings:
            result["warnings"] = warnings

        return result

    # ==================== TOOL 25: aiSearch ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def aiSearch(
        query: str,
        search: int = 0,
        display: int = 7,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        ⭐ PREFERRED TOOL for vague or natural language queries.
        Use this FIRST when user's intent is unclear or conversational.

        지능형 법령검색 시스템 검색 API (AI-powered semantic law search).

        Uses intelligent/semantic search to find relevant law articles.
        Returns FULL ARTICLE TEXT (조문내용) - more comprehensive than eflaw_search.

        Best for: Natural language queries like "뺑소니 처벌", "음주운전 벌금"

        Args:
            query: Search query (natural language supported, e.g., "뺑소니 처벌")
            search: Search scope:
                - 0: 법령조문 (law articles, default)
                - 1: 법령 별표·서식 (law appendix/forms)
                - 2: 행정규칙 조문 (administrative rule articles)
                - 3: 행정규칙 별표·서식 (administrative rule appendix/forms)
            display: Results per page (default 20)
            page: Page number (default 1)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            AI search results with full article text (법령조문 items with 조문내용)

        Example:
            >>> aiSearch(query="뺑소니 처벌", search=0)
            # Returns: 특정범죄 가중처벌 등에 관한 법률 제5조의3 (도주차량 운전자의 가중처벌)
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "aiSearch", "type": type,
            "query": query, "search": search, "display": display, "page": page,
        }
        result = run_search(
            get_client=_get_client, target="aiSearch", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )
        if result.get("status") == "ok":
            rows = next((v for v in (result.get("ranked_data") or {}).values()
                         if isinstance(v, list)), [])
            low = low_relevance_warning(query, rows)
            if low:
                result["warnings"] = list(result.get("warnings") or []) + [low]
        return result

    # ==================== TOOL 26: aiRltLs_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def aiRltLs_search(
        query: str,
        search: int = 0,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        ⭐ PREFERRED TOOL for discovering related laws from vague topics.
        Use this when user wants to explore laws around a general subject.

        지능형 법령검색 시스템 연관법령 API (AI-powered related laws search).

        Finds laws semantically related to a given law name or keyword.

        Best for: Finding related laws like "민법" → 상법, 의료법, 소송촉진법

        Args:
            query: Law name or keyword to find related laws (e.g., "민법", "형법")
            search: Search scope:
                - 0: 법령조문 (law articles, default)
                - 1: 행정규칙조문 (administrative rule articles)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            List of semantically related law articles (법령조문 items)

        Example:
            >>> aiRltLs_search(query="민법")
            # Returns: 상법 제54조 (상사법정이율), 의료법 제50조 (「민법」의 준용), etc.
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "aiRltLs", "type": type,
            "query": query, "search": search,
        }
        return run_search(
            get_client=_get_client, target="aiRltLs", query=query,
            snake_params=snake_params, response_type=type, display=20,
        )

    # ==================== PHASE 7: EXTENDED LEGAL INFORMATION ====================

    # ==================== TOOL 27: ordin_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def ordin_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        nw: int = 1,
        search: int = 1,
        sort: Optional[str] = None,
        date: Optional[int] = None,
        ef_yd: Optional[str] = None,
        anc_yd: Optional[str] = None,
        anc_no: Optional[str] = None,
        org: Optional[str] = None,
        sborg: Optional[str] = None,
        knd: Optional[str] = None,
        rr_cls_cd: Optional[str] = None,
        ordin_fd: Optional[int] = None,
        gana: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search local ordinances (자치법규 목록 조회).

        This tool searches Korean local ordinances (자치법규) including 조례, 규칙, and
        other local government regulations.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            nw: 1=현행 (current), 2=연혁 (historical), default 1
            search: 1=자치법규명 (ordinance name), 2=본문검색 (full text), default 1
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"
            date: Announcement date (YYYYMMDD)
            ef_yd: Effective date range (YYYYMMDD~YYYYMMDD)
            anc_yd: Announcement date range (YYYYMMDD~YYYYMMDD)
            anc_no: Announcement number
            org: Local government code filter (e.g., "6110000" for Seoul)
            sborg: Sub-organization code filter
            knd: Ordinance type code, passed to upstream as-is. Per the official guide
                (https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinListGuide):
                30001=조례, 30002=규칙, 30003=훈령, 30004=예규, 30006=기타, 30010=고시,
                30011=의회규칙. Values 1/2/3 are NOT valid (live audit returned 0 rows);
                omit knd if unsure.
            rr_cls_cd: Revision type code, 제개정 종류 (rrClsCd; e.g. 300201 제정, per API reference)
            ordin_fd: Ordinance field code
            gana: Dictionary search (ga, na, da, ...)
            ctx: MCP context (injected automatically)

        Returns:
            Search results with local ordinance list or error

        Examples:
            Search for "서울시 건축 조례":
            >>> ordin_search(query="건축", org="6110000", knd="30001")

            Search current ordinances:
            >>> ordin_search(query="주차장", display=20, type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        if ef_yd:
            validate_date_range(ef_yd, "ef_yd")
        if anc_yd:
            validate_date_range(anc_yd, "anc_yd")
        snake_params = {
            "oc": resolved_oc, "target": "ordin", "type": type,
            "query": query, "display": display, "page": page,
            "nw": nw, "search": search,
        }
        if sort: snake_params["sort"] = sort
        if date: snake_params["date"] = date
        if ef_yd: snake_params["ef_yd"] = ef_yd
        if anc_yd: snake_params["anc_yd"] = anc_yd
        if anc_no: snake_params["anc_no"] = anc_no
        if org: snake_params["org"] = org
        if sborg: snake_params["sborg"] = sborg
        if knd: snake_params["knd"] = knd
        if rr_cls_cd: snake_params["rr_cls_cd"] = rr_cls_cd
        if ordin_fd is not None: snake_params["ordin_fd"] = ordin_fd
        if gana: snake_params["gana"] = gana
        return run_search(
            get_client=_get_client, target="ordin", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="자치법규명", list_type="law",
            over_fetch_key="numOfRows",
        )

    # ==================== TOOL 28: ordin_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def ordin_service(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve local ordinance full text (자치법규 본문 조회).

        This tool retrieves the complete text of a Korean local ordinance.

        ⚠️ 응답이 클 수 있고 크기 제어 옵션 없음.

        Args:
            id: 자치법규ID (either id or mst is required). NOT the 자치법규일련번호 -
                a 일련번호 passed as id returns NOT_FOUND.
            mst: 자치법규일련번호 (ordinance master/serial number; either id or mst is required)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full ordinance text or error

        Examples:
            Retrieve by ID:
            >>> ordin_service(id="000001", type="XML")

            Retrieve by MST:
            >>> ordin_service(mst="123456", type="XML")
        """
        (id, mst) = stringify_id(id, mst)
        if not id and not mst:
            raise ValueError("Either 'id' or 'mst' parameter is required")
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "ordin", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        return run_service(get_client=_get_client, target="ordin",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 29: ordinLsCon_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def ordinLsCon_search(
        query: Optional[str] = None,
        law_id: Optional[Union[str, int]] = None,
        org: Optional[Union[str, int]] = None,
        display: int = 20,
        page: int = 1,
        sort: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Search ordinances linked to national laws (자치법규 기준 법령 연계 목록 조회).

        One tool, three modes — pass EXACTLY ONE of query / law_id / org:
          - query  → lawSearch.do?target=lnkOrd   : linked ordinances whose name
                     matches the keyword (e.g. "주차장")
          - law_id → lawSearch.do?target=lnkLsOrd : ordinances that implement /
                     reference the statute with that 법령ID (e.g. "001823")
          - org    → lawSearch.do?target=lnkOrg   : ordinances of a local
                     government (지자체 code, e.g. "3270000" 부산 동구); each item
                     also carries the linked 법령ID / 법령명한글

        Results use root OrdinSearch (lnkOrgSearch for org mode) with list key
        `law`; items hold 자치법규ID, 자치법규일련번호, 자치법규명, 자치법규종류,
        공포일자, 공포번호, 시행일자, 제개정구분명. Use ordin_service(id=자치법규ID)
        for the full ordinance text.

        Args:
            query: Ordinance name keyword (mode lnkOrd)
            law_id: 법령ID of a statute (mode lnkLsOrd, upstream param knd)
            org: Local-government code (mode lnkOrg, upstream param org)
            display: Number of results (max 100, default 20)
            page: Page number (1-based, default 1)
            sort: lasc/ldes (name), dasc/ddes (공포일자), nasc/ndes (공포번호),
                  efasc/efdes (시행일자) — documented for lnkOrd
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Search results (ranked_data) with the ordinance list, or a
            VALIDATION_ERROR when zero or more than one mode argument is given.

        Examples:
            >>> ordinLsCon_search(query="주차장", display=2)
            >>> ordinLsCon_search(law_id="001823", display=2)
            >>> ordinLsCon_search(org="3270000", display=2)
        """
        from .linkage import select_ordin_link_mode

        (law_id, org) = stringify_id(law_id, org)
        target, mode_params, ranking_query = select_ordin_link_mode(query, law_id, org)
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target, "type": type,
            "display": display, "page": page, **mode_params,
        }
        if sort: snake_params["sort"] = sort
        # Only lnkOrd has a keyword to rank by; "*" disables ranking for the
        # knd/org modes so upstream `display` is passed through untouched.
        return run_search(
            get_client=_get_client, target=target, query=ranking_query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="자치법규명", list_type="law",
            over_fetch_key="display",
        )

    # ==================== TOOL 30: trty_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def trty_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        search: Optional[int] = None,
        sort: Optional[str] = None,
        gana: Optional[str] = None,
        eft_yd: Optional[str] = None,
        conc_yd: Optional[str] = None,
        cls: Optional[int] = None,
        nat_cd: Optional[int] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search international treaties (조약 목록 조회).

        This tool searches Korean international treaties concluded and
        in effect with foreign countries and international organizations.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            search: Search type (1=조약명, 2=본문검색)
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"
            gana: Dictionary search (ga, na, da, ...)
            eft_yd: Effective date range (YYYYMMDD~YYYYMMDD)
            conc_yd: Conclusion date range (YYYYMMDD~YYYYMMDD)
            cls: Treaty type - 1=양자 (bilateral), 2=다자 (multilateral)
            nat_cd: Country code filter
            ctx: MCP context (injected automatically)

        Returns:
            Search results with treaty list or error

        Examples:
            Search bilateral treaties with the US:
            >>> trty_search(query="미합중국", cls=1)

            Search multilateral treaties:
            >>> trty_search(cls=2, display=20)
        """
        resolved_oc = resolve_oc(override_oc=oc)
        if eft_yd:
            validate_date_range(eft_yd, "eft_yd")
        if conc_yd:
            validate_date_range(conc_yd, "conc_yd")
        snake_params = {
            "oc": resolved_oc, "target": "trty", "type": type,
            "query": query, "display": display, "page": page,
        }
        if search is not None: snake_params["search"] = search
        if sort: snake_params["sort"] = sort
        if gana: snake_params["gana"] = gana
        if eft_yd: snake_params["eft_yd"] = eft_yd
        if conc_yd: snake_params["conc_yd"] = conc_yd
        if cls is not None: snake_params["cls"] = cls
        if nat_cd is not None: snake_params["nat_cd"] = nat_cd
        return run_search(
            get_client=_get_client, target="trty", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="조약명", list_type="items", item_category="trty",
            over_fetch_key="display",
        )

    # ==================== TOOL 31: trty_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def trty_service(
        id: Union[str, int],
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve treaty full text (조약 본문 조회).

        This tool retrieves the complete text of a Korean international treaty.

        ⚠️ 응답이 클 수 있고 크기 제어 옵션 없음.

        Args:
            id: Treaty sequence number (조약일련번호, required)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full treaty text with details or error

        Examples:
            Retrieve a treaty by ID:
            >>> trty_service(id="123")
        """
        if not id:
            raise ValueError("'id' parameter is required")
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "trty", "type": type,
            "id": str(id),
        }
        return run_service(get_client=_get_client, target="trty",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 32: lstrm_ai_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lstrm_ai_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Search legal terms using AI (법령용어 AI 조회).

        This tool searches Korean legal terminology using AI-powered semantic
        matching. Returns definitions and explanations of legal terms.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Search results or error
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "lstrmAI", "type": type,
            "query": query, "display": display, "page": page,
        }
        return run_search(
            get_client=_get_client, target="lstrmAI", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 33: dlytrm_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def dlytrm_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Search everyday terms (일상용어 조회).

        This tool searches plain-language (everyday) terms and their legal
        equivalents, helping bridge common language with formal legal terminology.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Search results or error
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "dlytrm", "type": type,
            "query": query, "display": display, "page": page,
        }
        return run_search(
            get_client=_get_client, target="dlytrm", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 34: lstrm_rlt_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lstrm_rlt_search(
        query: Optional[str] = None,
        mst: Optional[Union[str, int]] = None,
        trm_rlt_cd: Optional[Union[str, int]] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Legal term → everyday term linkage (법령용어-일상용어 연계 조회).

        Calls lawService.do?target=lstrmRlt (a lookup, not a paged search).
        Given a legal term, returns the everyday terms it is linked to with
        the relation type (동의어/반의어/상위어/하위어/연관어), plus follow-up
        links (dlytrmRlt MST, dlytrm query). Root key: lstrmRltService.

        Args:
            query: Exact legal term, e.g. "공정한이용" (required unless mst given)
            mst: Legal-term 일련번호 (MST) from a previous linkage result,
                 e.g. "1470403" (alternative to query)
            trm_rlt_cd: Optional 용어관계코드 filter — 140301 동의어, 140302 반의어,
                 140303 상위어, 140304 하위어, 140305 연관어 (Korean names accepted)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default) or "XML"
            ctx: MCP context (injected automatically)

        Note: display/page are not supported by this upstream endpoint.

        Returns:
            Response with raw_content plus parsed_data (검색결과개수, 법령용어 →
            연계용어[]) or a structured error.

        Examples:
            >>> lstrm_rlt_search(query="공정한이용")
            >>> lstrm_rlt_search(mst="1470403", trm_rlt_cd="140305")
        """
        from .linkage import attach_parsed_data, require_query_or_mst, validate_trm_rlt_cd

        (mst,) = stringify_id(mst)
        require_query_or_mst(query, mst, "lstrm_rlt_search")
        trm_rlt_cd = validate_trm_rlt_cd(trm_rlt_cd)
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "lstrmRlt", "type": type}
        if query: snake_params["query"] = query
        if mst: snake_params["mst"] = mst
        if trm_rlt_cd: snake_params["trm_rlt_cd"] = trm_rlt_cd
        response = run_service(get_client=_get_client, target="lstrmRlt",
                               snake_params=snake_params, response_type=type)
        return attach_parsed_data(response, type)

    # ==================== TOOL 35: dlytrm_rlt_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def dlytrm_rlt_search(
        query: Optional[str] = None,
        mst: Optional[Union[str, int]] = None,
        trm_rlt_cd: Optional[Union[str, int]] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Everyday term → legal term linkage (일상용어-법령용어 연계 조회).

        Calls lawService.do?target=dlytrmRlt (a lookup, not a paged search).
        Given an everyday word, returns the formal legal terms it maps to with
        the relation type (동의어/반의어/상위어/하위어/연관어) and follow-up links
        (lstrmRlt MST, lstrmRltJo MST). Root key: dlytrmRltService.

        Args:
            query: Exact everyday term, e.g. "월세" (required unless mst given)
            mst: Everyday-term 일련번호 (MST) from a previous result (alternative to query)
            trm_rlt_cd: Optional 용어관계코드 filter — 140301 동의어, 140302 반의어,
                 140303 상위어, 140304 하위어, 140305 연관어 (Korean names accepted)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default) or "XML"
            ctx: MCP context (injected automatically)

        Note: display/page are not supported by this upstream endpoint.

        Returns:
            Response with raw_content plus parsed_data (검색결과개수, 일상용어 →
            연계용어[]) or a structured error.

        Examples:
            >>> dlytrm_rlt_search(query="월세")
            >>> dlytrm_rlt_search(query="월세", trm_rlt_cd="동의어")
        """
        from .linkage import attach_parsed_data, require_query_or_mst, validate_trm_rlt_cd

        (mst,) = stringify_id(mst)
        require_query_or_mst(query, mst, "dlytrm_rlt_search")
        trm_rlt_cd = validate_trm_rlt_cd(trm_rlt_cd)
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "dlytrmRlt", "type": type}
        if query: snake_params["query"] = query
        if mst: snake_params["mst"] = mst
        if trm_rlt_cd: snake_params["trm_rlt_cd"] = trm_rlt_cd
        response = run_service(get_client=_get_client, target="dlytrmRlt",
                               snake_params=snake_params, response_type=type)
        return attach_parsed_data(response, type)

    # ==================== TOOL 36: lstrm_rlt_jo_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lstrm_rlt_jo_search(
        query: Optional[str] = None,
        mst: Optional[Union[str, int]] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Legal term → article linkage (법령용어-조문 연계 조회).

        Calls lawService.do?target=lstrmRltJo (a lookup, not a paged search).
        Given a legal term, returns the law articles that define or use it:
        법령명, 조번호 (4 digits), 조가지번호 (2 digits), 용어구분 (핵심용어 등),
        조문내용. Root key: lstrmRltJoService.

        Args:
            query: Exact legal term, e.g. "공정한이용" (required unless mst given)
            mst: Legal-term 일련번호 (MST), e.g. "1470403" (alternative to query)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default) or "XML"
            ctx: MCP context (injected automatically)

        Note: display/page are not supported by this upstream endpoint.

        Returns:
            Response with raw_content plus parsed_data (검색결과개수, 법령용어 →
            연계법령[]) or a structured error.

        Examples:
            >>> lstrm_rlt_jo_search(query="공정한이용")
        """
        from .linkage import attach_parsed_data, require_query_or_mst

        (mst,) = stringify_id(mst)
        require_query_or_mst(query, mst, "lstrm_rlt_jo_search")
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "lstrmRltJo", "type": type}
        if query: snake_params["query"] = query
        if mst: snake_params["mst"] = mst
        response = run_service(get_client=_get_client, target="lstrmRltJo",
                               snake_params=snake_params, response_type=type)
        return add_no_results_guidance(attach_parsed_data(response, type))

    # ==================== TOOL 37: jo_rlt_lstrm_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def jo_rlt_lstrm_search(
        jo: Union[str, int],
        query: Optional[str] = None,
        law_id: Optional[Union[str, int]] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Article → legal term linkage (조문-법령용어 연계 조회).

        Calls lawService.do?target=joRltLstrm (a lookup, not a paged search).
        Given a law (name or 법령ID) and an article, returns the legal terms
        selected in that article: 법령용어명, 용어구분 (선정용어/핵심용어),
        용어구분코드, plus lstrmRlt / lstrmRltJo follow-up links.
        Root key: joRltLstrmService.

        Args:
            jo: Article (REQUIRED). Accepts "35", "35의5", "제35조의5" or the
                6-digit upstream code "003505"; normalized to XXXXYY.
            query: Law name, e.g. "저작권법" (required unless law_id given)
            law_id: 법령ID of the law (upstream param ID; alternative to query)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default) or "XML"
            ctx: MCP context (injected automatically)

        Note: display/page are not supported by this upstream endpoint.

        Returns:
            Response with raw_content, parsed_data (검색결과개수, 법령조문 →
            연계용어[]) and the normalized `jo` code, or a structured error.

        Examples:
            >>> jo_rlt_lstrm_search(query="저작권법", jo="35의5")
            >>> jo_rlt_lstrm_search(law_id="001823", jo="003505")
        """
        from ._helpers import ToolValidationError
        from .linkage import attach_parsed_data, normalize_jo_code

        (law_id,) = stringify_id(law_id)
        jo_code = normalize_jo_code(jo)
        if (not query or query.strip() in ("", "*")) and not law_id:
            raise ToolValidationError(
                "jo_rlt_lstrm_search: provide 'query' (law name) or 'law_id' (법령ID)",
                hints=[
                    "query='저작권법', jo='35의5'",
                    "law_id='001823', jo='3'",
                ],
            )
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "joRltLstrm", "type": type, "jo": jo_code}
        if query: snake_params["query"] = query
        if law_id: snake_params["id"] = law_id
        response = run_service(get_client=_get_client, target="joRltLstrm",
                               snake_params=snake_params, response_type=type)
        response = attach_parsed_data(response, type)
        if response.get("status") == "ok":
            response["jo"] = jo_code
        return response

    # ==================== TOOL 38: ls_rlt_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def ls_rlt_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Related law search (관련법령 조회).

        This tool searches for laws related to a given query term. Part of the
        법령정보 지식베이스, it identifies associations between laws based on
        shared subject matter or cross-references.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Search results or error
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "lsRlt", "type": type,
            "query": query, "display": display, "page": page,
        }
        return run_search(
            get_client=_get_client, target="lsRlt", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TASK 12: 위원회 결정문 ====================

    # Committee target code mapping
    COMMITTEE_CODES = {
        "개인정보보호위원회": "ppc",
        "고용보험심사위원회": "eiac",
        "공정거래위원회": "ftc",
        "국민권익위원회": "acr",
        "금융위원회": "fsc",
        "노동위원회": "nlrc",
        "방송미디어통신위원회": "kcc",
        "산업재해보상보험재심사위원회": "iaciac",
        "중앙토지수용위원회": "oclt",
        "중앙환경분쟁조정위원회": "ecc",
        "증권선물위원회": "sfc",
        "국가인권위원회": "nhrck",
    }

    # ==================== TOOL 39: committee_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def committee_search(
        committee: str,
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        search: Optional[int] = None,
        sort: Optional[str] = None,
        gana: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search committee decisions (위원회 결정문 목록 조회).

        Search decisions from Korean government committees.

        Args:
            committee: Committee name in Korean. Valid values:
                개인정보보호위원회, 고용보험심사위원회, 공정거래위원회,
                국민권익위원회, 금융위원회, 노동위원회, 방송미디어통신위원회,
                산업재해보상보험재심사위원회, 중앙토지수용위원회,
                중앙환경분쟁조정위원회, 증권선물위원회, 국가인권위원회
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            search: 1=안건명 (case name), 2=본문검색 (full text)
            sort: Sort order
            gana: Dictionary search
            ctx: MCP context (injected automatically)

        Returns:
            Committee decision list or error

        Examples:
            Search 공정거래위원회 decisions:
            >>> committee_search(committee="공정거래위원회", query="담합")
        """
        target = COMMITTEE_CODES.get(committee)
        if not target:
            valid = ", ".join(COMMITTEE_CODES.keys())
            raise ValueError(f"Invalid committee: '{committee}'. Valid values: {valid}")

        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target, "type": type,
            "query": query, "display": display, "page": page,
        }
        if search: snake_params["search"] = search
        if sort: snake_params["sort"] = sort
        if gana: snake_params["gana"] = gana

        return run_search(
            get_client=_get_client, target=target, query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="안건명", list_type="items", item_category=target,
            over_fetch_key="display",
        )

    # ==================== TOOL 40: committee_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def committee_service(
        committee: str,
        id: Union[str, int],
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve committee decision full text (위원회 결정문 본문 조회).

        ⚠️ 응답이 클 수 있고 크기 제어 옵션 없음.

        Args:
            committee: Committee name (same values as committee_search)
            id: Decision serial number (결정문일련번호)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full decision text or error
        """
        target = COMMITTEE_CODES.get(committee)
        if not target:
            valid = ", ".join(COMMITTEE_CODES.keys())
            raise ValueError(f"Invalid committee: '{committee}'. Valid values: {valid}")

        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target,
            "id": str(id), "type": type,
        }
        response = run_service(get_client=_get_client, target=target,
                               snake_params=snake_params, response_type=type)
        # Unknown ids come back as 200 with every field the literal "null"/blank
        if (response.get("status") == "ok" and isinstance(response.get("raw_content"), str)
                and body_is_all_null(response["raw_content"], type, str(id))):
            return create_error_response(
                ErrorCode.NOT_FOUND,
                f"{committee} 결정문일련번호 {id}에 해당하는 결정문이 없습니다 (본문 필드가 모두 비어 있음).",
                hints=["committee_search 결과의 실제 결정문일련번호를 사용하세요"],
            )
        return response

    # ==================== TASK 13: 중앙부처 1차 해석 ====================

    # Ministry/tribunal code tables and target builders live in agency_codes.py
    # (upstream target is "{code}CgmExpc", e.g. moelCgmExpc — NOT "cgmExpc{Code}").
    from .agency_codes import (
        MINISTRY_CODES, MINISTRIES_LIST_ONLY, TRIBUNAL_CODES,
        CGM_EXPC_LIST_KEY, CGM_EXPC_TITLE_FIELD,
        SPECIAL_DECC_LIST_KEY, SPECIAL_DECC_TITLE_FIELD,
        resolve_ministry, valid_ministry_names,
        cgm_expc_target, special_decc_target, enforce_display,
    )
    from ._helpers import ToolValidationError

    # ==================== TOOL 41: cgm_expc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def cgm_expc_search(
        ministry: str,
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        search: Optional[int] = None,
        sort: Optional[str] = None,
        gana: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search ministry law interpretations (중앙부처 1차 해석 목록 조회).

        Search law interpretation opinions from Korean central government ministries.

        Args:
            ministry: Ministry name in Korean. Valid values:
                고용노동부, 국토교통부, 재정경제부, 해양수산부, 행정안전부,
                기후에너지환경부, 관세청, 국세청, 교육부, 과학기술정보통신부,
                국가보훈부, 국방부, 농림축산식품부, 문화체육관광부, 법무부,
                보건복지부, 산업통상부, 성평등가족부, 외교부, 중소벤처기업부,
                통일부, 법제처, 식품의약품안전처, 인사혁신처, 기상청,
                국가유산청, 농촌진흥청, 경찰청, 방위사업청, 병무청, 산림청,
                소방청, 재외동포청, 조달청, 질병관리청, 국가데이터처,
                지식재산처, 해양경찰청, 행정중심복합도시건설청
                (former names such as 기획재정부 → 재정경제부 are accepted as aliases)
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            search: 1=사건명 (case name), 2=본문검색 (full text)
            sort: Sort order
            gana: Dictionary search
            ctx: MCP context (injected automatically)

        Returns:
            Ministry interpretation list or error. Each item has 안건명, 법령해석일련번호
            (use as `id` for cgm_expc_service), 해석기관명, 해석일자, 법령해석상세링크.
            For 재정경제부/국세청 only this list exists upstream — follow 법령해석상세링크
            for the text instead of cgm_expc_service.

        Examples:
            Search 고용노동부 interpretations:
            >>> cgm_expc_search(ministry="고용노동부", query="퇴직금")
        """
        canonical = resolve_ministry(ministry)
        if not canonical:
            raise ValueError(
                f"Invalid ministry: '{ministry}'. Valid values: {valid_ministry_names()}"
            )
        code = MINISTRY_CODES[canonical]

        target = cgm_expc_target(code)
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target, "type": type,
            "query": query, "display": display, "page": page,
        }
        if search: snake_params["search"] = search
        if sort: snake_params["sort"] = sort
        if gana: snake_params["gana"] = gana

        # Response root is "CgmExpc", list key "cgmExpc" (same for every ministry)
        response = run_search(
            get_client=_get_client, target=target, query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field=CGM_EXPC_TITLE_FIELD, list_type="items",
            item_category=CGM_EXPC_LIST_KEY, over_fetch_key="display",
            finalize_ids=False,
        )
        # Never leak the 100-row over-fetch, even if ranking didn't run
        response = enforce_display(response, display, CGM_EXPC_LIST_KEY)
        # After enforce_display: its raw_content rewrite must keep the upstream ids
        return rename_row_ids_to_rank(response)

    # ==================== TOOL 42: cgm_expc_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def cgm_expc_service(
        ministry: str,
        id: Union[str, int],
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve ministry interpretation full text (중앙부처 1차 해석 본문 조회).

        ⚠️ 응답이 클 수 있고 크기 제어 옵션 없음.

        Args:
            ministry: Ministry name (same values as cgm_expc_search).
                Not available for 재정경제부 and 국세청 — upstream provides no
                full-text API for them (list only; see 법령해석상세링크 in search results).
            id: Interpretation serial number (법령해석일련번호 from cgm_expc_search)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full interpretation text (root CgmExpcService: 안건명, 질의요지, 회답, 이유 ...) or error
        """
        canonical = resolve_ministry(ministry)
        if not canonical:
            raise ValueError(
                f"Invalid ministry: '{ministry}'. Valid values: {valid_ministry_names()}"
            )
        if canonical in MINISTRIES_LIST_ONLY:
            raise ToolValidationError(
                f"'{canonical}' provides the interpretation list API only; law.go.kr has no "
                f"full-text (본문) API for this ministry, so cgm_expc_service cannot be used.",
                hints=[
                    f"Use cgm_expc_search(ministry='{canonical}', ...) to list interpretations.",
                    "Each list item's 법령해석상세링크 points to the ministry's own site "
                    "(taxlaw.nts.go.kr) where the full text is published.",
                    f"Ministries without full text: {', '.join(sorted(MINISTRIES_LIST_ONLY))}.",
                ],
            )
        code = MINISTRY_CODES[canonical]

        target = cgm_expc_target(code)
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target,
            "id": str(id), "type": type,
        }
        return run_service(get_client=_get_client, target=target,
                          snake_params=snake_params, response_type=type)

    # ==================== TASK 14: 특별행정심판 ====================

    # TRIBUNAL_CODES ({code}SpecialDecc pattern) imported from agency_codes above.

    # ==================== TOOL 43: special_decc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def special_decc_search(
        tribunal: str,
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "JSON",
        search: Optional[int] = None,
        sort: Optional[str] = None,
        gana: Optional[str] = None,
        cls: Optional[str] = None,
        date: Optional[int] = None,
        dpa_yd: Optional[str] = None,
        rsl_yd: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search special administrative appeal decisions (특별행정심판 목록 조회).

        Search decisions from Korean special administrative appeal tribunals.

        Args:
            tribunal: Tribunal name in Korean. Valid values:
                조세심판원, 해양안전심판원, 국민권익위원회,
                인사혁신처 소청심사위원회
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "JSON" (default), "XML", or "HTML"
            search: 1=사건명 (case name), 2=본문검색 (full text)
            sort: Sort order
            gana: Dictionary search
            cls: 재결례유형 (decision type classification)
            date: Reference date (YYYYMMDD)
            dpa_yd: Decision date range (YYYYMMDD~YYYYMMDD)
            rsl_yd: Resolution date range (YYYYMMDD~YYYYMMDD)
            ctx: MCP context (injected automatically)

        Returns:
            Special appeal decision list or error

        Examples:
            Search 조세심판원 decisions:
            >>> special_decc_search(tribunal="조세심판원", query="부가가치세")
        """
        code = TRIBUNAL_CODES.get(tribunal)
        if not code:
            valid = ", ".join(TRIBUNAL_CODES.keys())
            raise ValueError(f"Invalid tribunal: '{tribunal}'. Valid values: {valid}")

        target = special_decc_target(code)
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target, "type": type,
            "query": query, "display": display, "page": page,
        }
        if search: snake_params["search"] = search
        if sort: snake_params["sort"] = sort
        if gana: snake_params["gana"] = gana
        if cls: snake_params["cls"] = cls
        if date: snake_params["date"] = date
        if dpa_yd:
            validate_date_range(dpa_yd, "dpa_yd")
            snake_params["dpa_yd"] = dpa_yd
        if rsl_yd:
            validate_date_range(rsl_yd, "rsl_yd")
            snake_params["rsl_yd"] = rsl_yd

        # Response root is "Decc", list key "decc" — not the target name
        response = run_search(
            get_client=_get_client, target=target, query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field=SPECIAL_DECC_TITLE_FIELD, list_type="items",
            item_category=SPECIAL_DECC_LIST_KEY, over_fetch_key="display",
            finalize_ids=False,
        )
        # Never leak the 100-row over-fetch, even if ranking didn't run
        response = enforce_display(response, display, SPECIAL_DECC_LIST_KEY)
        # After enforce_display: its raw_content rewrite must keep the upstream ids
        return rename_row_ids_to_rank(response)

    # ==================== TOOL 44: special_decc_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def special_decc_service(
        tribunal: str,
        id: Union[str, int],
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve special administrative appeal decision full text (특별행정심판 본문 조회).

        ⚠️ 응답이 클 수 있고 크기 제어 옵션 없음.

        Args:
            tribunal: Tribunal name (same values as special_decc_search)
            id: Decision serial number (재결례일련번호)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"
            ctx: MCP context (injected automatically)

        Returns:
            Full decision text or error
        """
        code = TRIBUNAL_CODES.get(tribunal)
        if not code:
            valid = ", ".join(TRIBUNAL_CODES.keys())
            raise ValueError(f"Invalid tribunal: '{tribunal}'. Valid values: {valid}")

        target = special_decc_target(code)
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target,
            "id": str(id), "type": type,
        }
        return run_service(get_client=_get_client, target=target,
                          snake_params=snake_params, response_type=type)

    # ==================== PHASE 8: PUBLIC LEGAL ASSISTANCE ====================

    # Shared helpers for the Phase 8/9 tools (article text, version selection).
    from .article_text import (
        ArticleNotFoundError, normalize_article, article_label,
        extract_article, law_rows, select_law_rows, pick_current_version,
        dedupe_versions, revision_record, previous_version, parse_article_history,
        end_of_current_year, strip_html, compact_delegation_tree,
    )
    from ._helpers import ToolValidationError, slim_enabled
    from .as_of import normalize_as_of, build_candidates, select_as_of, describe, day_before, is_repeal
    PERIOD_MAX = 12  # law_as_of period mode: max revisions fetched
    from .validation import format_article_number

    def _internal_format(response_type: str) -> str:
        """Tools accept HTML for pass-through, but internal parsing needs JSON/XML."""
        return response_type if response_type in ("JSON", "XML") else "JSON"

    def _items_from_result(result: dict, response_type: str) -> tuple[list, int]:
        """Return (items, totalCnt) from a run_search result.

        Uses ranked_data when present; otherwise falls back to the raw body so a
        failed ranking step (unknown list key) does not look like an empty result.
        """
        ranked = result.get("ranked_data")
        parsed = ranked
        if parsed is None:
            raw = result.get("raw_content", "")
            if raw and response_type == "JSON":
                try:
                    jd = json.loads(raw)
                    parsed = list(jd.values())[0] if isinstance(jd, dict) and jd else None
                except ValueError:
                    parsed = None
            elif raw:
                parsed = parse_xml_response(raw)
        if not isinstance(parsed, dict):
            return [], 0
        items: list = []
        for val in parsed.values():
            if isinstance(val, list) and (not val or isinstance(val[0], dict)):
                items = val
                break
            if isinstance(val, dict) and any(k in val for k in ("판례일련번호", "사건명", "사건번호")):
                items = [val]
                break
        total = parsed.get("totalCnt", len(items))
        if isinstance(total, str):
            total = int(total) if total.isdigit() else len(items)
        elif not isinstance(total, int):
            total = len(items)
        return items, total

    def _result_error(result: dict, source: str) -> Optional[dict]:
        """Failure record for a non-ok run_search result (code only: no upstream text)."""
        if isinstance(result, dict) and result.get("status") != "ok":
            return {
                "source": source,
                "error_code": result.get("error_code") or ErrorCode.UPSTREAM_ERROR,
            }
        return None

    def _failure_warnings(failures: list) -> list[str]:
        return [f"{f['source']} 조회 실패 ({f['error_code']}): 결과가 누락되었을 수 있습니다" for f in failures]

    def _all_failed_response(failures: list, request_id: Optional[str] = None) -> dict:
        """Error response when every sub-search failed (keeps a single shared code)."""
        codes = {f["error_code"] for f in failures}
        code = next(iter(codes)) if len(codes) == 1 else ErrorCode.UPSTREAM_ERROR
        listed = ", ".join(f"{f['source']}={f['error_code']}" for f in failures)
        hints = [
            "검색 결과가 없는 것이 아니라 모든 하위 조회가 실패했습니다. 잠시 후 다시 시도하세요",
            "OC 승인 및 해당 API 신청 여부(open.law.go.kr)와 네트워크 상태를 확인하세요",
        ]
        if code == ErrorCode.API_NOT_SUBSCRIBED:
            hints.append("open.law.go.kr에서 해당 목록/본문 API 사용 신청이 필요합니다")
        return create_error_response(
            error_code=code,
            message=f"모든 하위 검색이 실패했습니다: {listed}. All upstream sub-searches failed.",
            hints=hints,
            request_id=request_id,
            success=False,
            failed_sources=[dict(f) for f in failures],
        )

    def _search_with_fallback(
        *, target: str, query: str, display: int, response_type: str,
        resolved_oc: str, ranking_field: str, item_category: str,
        min_results: int = 1, extra_params: Optional[dict] = None,
    ) -> dict:
        """Case-name search (search=1) first; retry as full-text (search=2) when thin.

        Returns {"items", "total", "mode", "attempts", "errors", "all_failed"}.
        ``mode`` names the search that produced the items so callers can report it;
        ``errors`` lists failed attempts and ``all_failed`` is True when none succeeded.
        """
        modes = [(1, "사건명(search=1)"), (2, "본문(search=2)")]
        best = {"items": [], "total": 0, "mode": modes[0][1], "attempts": [],
                "errors": [], "all_failed": False}
        succeeded = 0
        for code, label in modes:
            params = {
                "oc": resolved_oc, "target": target, "type": response_type,
                "query": query, "display": display, "page": 1, "search": code,
            }
            if extra_params:
                params.update(extra_params)
            result = run_search(
                get_client=_get_client, target=target, query=query,
                snake_params=params, response_type=response_type, display=display,
                ranking_field=ranking_field, list_type="items", item_category=item_category,
                over_fetch_key="display",
            )
            err = _result_error(result, f"{target} {label}")
            if err:
                best["errors"].append(err)
                best["attempts"].append({"mode": label, "error_code": err["error_code"]})
                continue
            succeeded += 1
            items, total = _items_from_result(result, response_type)
            best["attempts"].append({"mode": label, "found": total})
            if len(items) > len(best["items"]):
                best.update(items=items, total=total, mode=label)
            if len(items) >= max(1, min_results):
                break
        best["all_failed"] = succeeded == 0
        return best

    HISTORY_MAX_PAGES = 30  # safety cap: 100 rows/page

    def _upstream_failure_response(law_name: str, failure: dict) -> dict:
        return create_error_response(
            error_code=failure["error_code"],
            message=f"법령 '{law_name}' 조회 중 upstream 오류가 발생했습니다 ({failure['source']}={failure['error_code']}). Upstream request failed.",
            hints=["법령이 없는 것이 아니라 조회가 실패했습니다. 잠시 후 다시 시도하세요",
                   "OC 승인 및 해당 API 신청 여부(open.law.go.kr)와 네트워크 상태를 확인하세요"],
            success=False,
            failed_sources=[dict(failure)],
        )

    def _resolve_law_versions(law_name: str, resolved_oc: str, response_type: str,
                              need_history: bool = False, law_id: str = "",
                              include_repealed: bool = False) -> dict:
        """Resolve a law name to one 법령ID and (optionally) all of its versions.

        Step 1: eflaw search by name → rows for the best-matching 법령ID
                (exact 법령명한글, 법률 preferred unless the user named a 시행령/시행규칙).
        Step 2 (need_history): eflaw search filtered by LID (paged, nw=1,2,3: JSON
                returns only the 현행 row without it) → every 연혁/현행/시행예정 row
                of that law, de-duplicated by MST.

        An upstream failure returns the error response itself (``status == "error"``)
        so callers can pass it on instead of reporting "법령을 찾을 수 없습니다".
        """
        if law_id:
            rows: list = []
            head: dict = {"법령ID": law_id}
        else:
            rows = []
            target_name = re.sub(r"\s+", "", law_name)
            # include_repealed: a repealed law has no 현행 row, so the default (current-only)
            # name search cannot see it; retry once with nw=1,2,3 unless an exact name matched.
            for extra in ([{}, {"nw": "1,2,3"}] if include_repealed else [{}]):
                search_params = {
                    "oc": resolved_oc, "target": "eflaw", "type": response_type,
                    "query": law_name, "display": 100, "page": 1, **extra,
                }
                search_result = run_search(
                    get_client=_get_client, target="eflaw", query=law_name,
                    snake_params=search_params, response_type=response_type, display=100,
                    ranking_field="법령명한글", list_type="law",
                    over_fetch_key="numOfRows",
                )
                err = _result_error(search_result, "eflaw 법령 검색")
                if err:
                    return _upstream_failure_response(law_name, err)
                rows = select_law_rows(law_rows(search_result), law_name)
                if any(re.sub(r"\s+", "", r.get("법령명한글", "")) == target_name for r in rows):
                    break
            if not rows:
                raise ToolValidationError(
                    f"법령 '{law_name}'을(를) 찾을 수 없습니다.",
                    hints=["정식 법령명(예: '저작권법', '근로기준법')으로 다시 시도하세요."],
                )
            head = rows[0]
            law_id = head.get("법령ID", "")
        info = {
            "law_id": law_id,
            "law_name": head.get("법령명한글", law_name),
            "law_type": head.get("법령구분명", ""),
            "ministry": head.get("소관부처명", ""),
        }

        all_rows = list(rows)
        if need_history and law_id:
            fetched: list = []
            raw_count = 0
            page = 1
            while page <= HISTORY_MAX_PAGES:
                lid_params = {
                    "oc": resolved_oc, "target": "eflaw", "type": response_type,
                    "lid": law_id, "display": 100, "page": page, "nw": "1,2,3",
                }
                lid_result = run_search(
                    get_client=_get_client, target="eflaw", query="",
                    snake_params=lid_params, response_type=response_type, display=100,
                    ranking_field=None, list_type=None,
                )
                err = _result_error(lid_result, "eflaw 연혁 조회")
                if err:
                    return _upstream_failure_response(law_name, err)
                raw_rows = law_rows(lid_result)
                fetched.extend(r for r in raw_rows if r.get("법령ID") == law_id)
                raw_count += len(raw_rows)
                _, total = _items_from_result(lid_result, response_type)
                if not raw_rows or raw_count >= total:
                    break
                if page == HISTORY_MAX_PAGES:
                    info["warnings"] = [
                        f"연혁 조회가 {HISTORY_MAX_PAGES}페이지({raw_count}행)에서 중단되었습니다 "
                        f"(upstream 총 {total}행): 오래된 개정 이력이 누락되었을 수 있습니다"
                    ]
                page += 1
            if fetched:
                all_rows = fetched
                if not rows:  # resolved by 법령ID: take the header fields from the history
                    head = pick_current_version(fetched) or fetched[0]
                    info.update(law_name=head.get("법령명한글", law_name),
                                law_type=head.get("법령구분명", ""), ministry=head.get("소관부처명", ""))

        info["rows"] = all_rows
        info["versions"] = dedupe_versions(all_rows)
        info["current"] = pick_current_version(all_rows) or (info["versions"][0] if info["versions"] else head)
        return info

    def _fetch_article(mst: str, article: int, branch: int, resolved_oc: str,
                       response_type: str) -> dict:
        """Fetch one article via lawService.do?target=law&MST=…&JO=… and flatten it.

        Raises ArticleNotFoundError (with hints) when the version lacks the article.
        """
        jo = format_article_number(article, branch)
        svc_params = {
            "oc": resolved_oc, "target": "law", "type": response_type,
            "mst": str(mst), "jo": jo,
        }
        result = run_service(
            get_client=_get_client, target="law",
            snake_params=svc_params, response_type=response_type,
        )
        if result.get("error_code") == ErrorCode.NOT_FOUND:
            # 일치하는 법령 없음/빈 본문: callers (e.g. _try_fetch) treat it as a missing version
            raise ArticleNotFoundError(
                f"MST {mst} {article_label(article, branch)}: {result.get('message', '본문을 찾을 수 없습니다')}",
                hints=result.get("hints"),
            )
        if result.get("status") != "ok":
            raise ValueError(
                f"MST {mst} {article_label(article, branch)} 조회 실패: {result.get('message', result.get('error_code', 'upstream error'))}"
            )
        info = extract_article(result.get("raw_content", ""), response_type, article, branch)
        info["mst"] = str(mst)
        info["jo"] = jo
        return info

    def _version_meta(info: dict) -> dict:
        """Compact version descriptor for diff outputs."""
        law = info.get("law", {}) if info else {}
        return {
            "mst": info.get("mst", "") if info else "",
            "law_name": law.get("law_name", ""),
            "date": law.get("announced", ""),
            "announcement_no": law.get("announcement_no", ""),
            "effective_date": law.get("effective", ""),
            "revision_type": law.get("revision_type", ""),
            "article_effective": info.get("effective", "") if info else "",
            "text": info.get("text", "") if info else "",
        }

    # ==================== TOOL 45: check_precedent_odds ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def check_precedent_odds(
        query: str,
        display: int = 20,
        top_n: int = 5,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Find precedent statistics and key outcome factors for a legal question (판례 결과 분포).

        Searches court precedents, classifies each case's 주문 (disposition, e.g. 파기환송/
        상고기각/항소기각/각하/일부인용; 불명 when unclear) and extracts key factors. This is a
        distribution of dispositions, NOT a win rate: see outcome_note before drawing conclusions.

        Args:
            query: Legal question or keywords (e.g., "택배 파손 보상", "임대차 보증금 반환")
            display: Number of precedents to search (max 100, default 20)
            top_n: Number of top precedents to analyze in detail (default 5)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Outcome statistics, key factors, and representative case summaries

        Examples:
            >>> check_precedent_odds(query="택배 파손 보상")
            >>> check_precedent_odds(query="부당해고", display=50, top_n=10)
        """
        resolved_oc = resolve_oc(override_oc=oc)

        # Step 1: Search precedents — 사건명(search=1) first, 본문(search=2) fallback
        # when the case-name search yields fewer than top_n hits (topical queries
        # such as "저작권 공정이용" rarely appear verbatim in case names).
        fmt = _internal_format(type)
        found = _search_with_fallback(
            target="prec", query=query, display=display, response_type=fmt,
            resolved_oc=resolved_oc, ranking_field="판례명", item_category="prec",
            min_results=max(1, top_n),
        )
        if found["all_failed"]:
            return _all_failed_response(found["errors"])
        prec_list = found["items"]
        total_found = found["total"]
        search_mode = found["mode"]

        # Step 2: Analyze top_n precedents
        outcomes = {}
        all_factors = []
        cases = []
        unavailable = 0
        slim_cut = False

        seen_case_numbers: set = set()
        for item in prec_list:
            if len(cases) >= top_n:
                break
            prec_id = item.get("판례일련번호")
            if not prec_id:
                continue
            # Upstream lists the same judgment under several ids; analyze it once
            case_no = item.get("사건번호", "")
            if case_no and case_no in seen_case_numbers:
                continue
            seen_case_numbers.add(case_no)

            # Fetch summary
            svc_params = {
                "oc": resolved_oc, "target": "prec",
                "id": str(prec_id), "type": type,
            }
            svc_result = run_service(
                get_client=_get_client, target="prec",
                snake_params=svc_params, response_type=type,
            )

            # Body unavailable (NOT_FOUND etc.): skip, try the next candidate
            if svc_result.get("status") != "ok":
                unavailable += 1
                continue

            # Parse the response to extract 판시사항 and 판결요지
            raw = svc_result.get("raw_content", "")
            holding = ""
            summary_text = ""
            body_text = ""  # 판례내용: the only place the 주문 lives

            if raw and type == "JSON":
                try:
                    import json as _json
                    jd = _json.loads(raw)
                    root = list(jd.values())[0] if jd else {}
                    holding = root.get("판시사항", "")
                    summary_text = root.get("판결요지", "")
                    body_text = root.get("판례내용", "")
                except:
                    pass
            elif raw:
                import re as _re
                h_match = _re.search(r'<판시사항>(.*?)</판시사항>', raw, _re.DOTALL)
                s_match = _re.search(r'<판결요지>(.*?)</판결요지>', raw, _re.DOTALL)
                if h_match:
                    holding = h_match.group(1).strip()
                if s_match:
                    summary_text = s_match.group(1).strip()
                b_match = _re.search(r'<판례내용>(.*?)</판례내용>', raw, _re.DOTALL)
                if b_match:
                    body_text = b_match.group(1).strip()

            # Upstream prose carries <br/> tags; strip them before analysis/output
            holding = strip_html(holding)
            summary_text = strip_html(summary_text)

            # Extract outcome and factors
            # Outcome comes from the 주문 only; recitals/판결요지 are never read
            order = extract_order(body_text)
            outcome = classify_order(order)
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            factors = [strip_html(f) for f in extract_key_factors(holding)]
            all_factors.extend(f for f in factors if f)

            cases.append({
                "id": str(prec_id),
                "name": strip_html(item.get("사건명", "")),
                "date": item.get("선고일자", ""),
                "case_number": item.get("사건번호", ""),
                "court": item.get("법원명", ""),
                "outcome": outcome,
                "order": order[:compact_limit(300)] if order else "",
                "holding": holding[:compact_limit(500)] if holding else "",
                "summary": summary_text[:compact_limit(500)] if summary_text else "",
            })
            if slim_enabled() and (len(holding or "") > 500 or len(summary_text or "") > 500):
                slim_cut = True

        # Deduplicate factors
        seen = set()
        unique_factors = []
        for f in all_factors:
            if f not in seen:
                seen.add(f)
                unique_factors.append(f)

        if slim_enabled() and (len(unique_factors) > 10 or any(len(f) >= 100 for f in unique_factors)):
            slim_cut = True
        result = {
            "status": "ok",
            "query": query,
            "total_found": total_found,
            "analyzed": len(cases),
            "unavailable_cases": unavailable,
            "outcome_summary": outcomes,
            "key_factors": unique_factors[:compact_limit(10)],
            "search_mode": search_mode,
            "search_attempts": found["attempts"],
            "representative_cases": cases,
            "outcome_note": OUTCOME_NOTE,
            "disclaimer": "이 분석은 참고용이며 법률 자문이 아닙니다. 정확한 판단을 위해 변호사와 상담하세요.",
        }
        if found["errors"]:
            result["warnings"] = _failure_warnings(found["errors"])
        elif not cases and not total_found:
            result.update(_no_results_fields(body_search=True))
        if slim_cut:
            mark_slim_cut(result, "SLIM_RESPONSE: 판시사항/요지(500자)와 key_factors(100자·10개)가 줄었습니다. 전문은 prec_service(id=사건 id, sections=\"summary\")로 조회하세요.")
        return result

    # ==================== TOOL 46: legal_resolver ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def legal_resolver(
        situation: str,
        display: int = 5,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Find all applicable laws, precedents, and interpretations for a situation (법률 종합 분석).

        Given a plain language description of a legal situation, this tool searches across
        multiple legal databases in one call: law articles, court precedents, legal
        interpretations, and citation networks.

        Args:
            situation: Plain language description (e.g., "직원이 고객 데이터를 USB에 담아갔다")
            display: Results per sub-query (default 5)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Comprehensive legal analysis with applicable laws, precedents, interpretations, and citations

        Examples:
            >>> legal_resolver(situation="집주인이 보증금을 안 돌려줘요")
            >>> legal_resolver(situation="회사에서 갑자기 해고당했어요", display=3)
        """
        resolved_oc = resolve_oc(override_oc=oc)
        api_calls = 0
        failures: list = []
        attempted = 0

        # Step 1: AI search for relevant law articles
        ai_params = {
            "oc": resolved_oc, "target": "aiSearch", "type": type,
            "query": situation, "search": 0, "display": display, "page": 1,
        }
        ai_result = run_search(
            get_client=_get_client, target="aiSearch", query=situation,
            snake_params=ai_params, response_type=type, display=display,
        )
        api_calls += 1
        attempted += 1
        _e = _result_error(ai_result, "aiSearch")
        if _e:
            failures.append(_e)

        # Extract law articles from AI search
        applicable_laws = []
        slim_cut = False
        ranked = ai_result.get("ranked_data", {})
        articles = []
        for key, val in ranked.items():
            if isinstance(val, list):
                articles = val
                break

        resolver_warnings: list[str] = []
        low = None if _e else low_relevance_warning(situation, articles[:display])
        if low:
            resolver_warnings.append(low)

        law_names_seen = set()
        for art in articles[:display]:
            law_name = art.get("법령명", "")
            applicable_laws.append({
                "law_name": law_name,
                "law_id": art.get("법령ID", ""),
                "article": art.get("조문번호", ""),
                "article_title": art.get("조문제목", ""),
                "article_text": (art.get("조문내용", "") or "")[:compact_limit(500)],
            })
            if slim_enabled() and len(art.get("조문내용", "") or "") > 500:
                slim_cut = True
            if law_name:
                law_names_seen.add(law_name)

        # Step 2: Search precedents for each unique law (max 3 laws)
        related_precedents = []
        for law_name in list(law_names_seen)[:3]:
            prec_params = {
                "oc": resolved_oc, "target": "prec", "type": type,
                "query": law_name, "display": 3, "page": 1,
            }
            prec_result = run_search(
                get_client=_get_client, target="prec", query=law_name,
                snake_params=prec_params, response_type=type, display=3,
                ranking_field="판례명", list_type="items", item_category="prec",
                over_fetch_key="display",
            )
            api_calls += 1
            attempted += 1
            _e = _result_error(prec_result, f"prec({law_name})")
            if _e:
                failures.append(_e)

            prec_ranked = prec_result.get("ranked_data", {})
            for key, val in prec_ranked.items():
                if isinstance(val, list):
                    for p in val[:3]:
                        related_precedents.append({
                            "id": p.get("판례일련번호", ""),
                            "name": p.get("사건명", ""),
                            "case_number": p.get("사건번호", ""),
                            "date": p.get("선고일자", ""),
                            "court": p.get("법원명", ""),
                        })
                    break

        # Step 3: Citation network for top article
        citations = []
        if applicable_laws:
            top = applicable_laws[0]
            mst = ""
            # Get MST from a quick search — prefer the 현행 version, not the first
            # row (which is usually a 시행예정 MST)
            search_params = {
                "oc": resolved_oc, "target": "eflaw", "type": type,
                "query": top["law_name"], "display": 20, "page": 1,
            }
            s_result = run_search(
                get_client=_get_client, target="eflaw", query=top["law_name"],
                snake_params=search_params, response_type=type, display=20,
                ranking_field="법령명한글", list_type="law",
                over_fetch_key="numOfRows",
            )
            api_calls += 1
            attempted += 1
            _e = _result_error(s_result, "eflaw")
            if _e:
                failures.append(_e)

            s_rows = select_law_rows(law_rows(s_result), top["law_name"])
            current_row = pick_current_version(s_rows)
            if current_row:
                mst = current_row.get("법령일련번호", "")

            if mst and top.get("article"):
                try:
                    from .citation import extract_article_citations
                    art_num = int(top["article"]) if top["article"].isdigit() else 0
                    if art_num > 0:
                        # FastMCP already runs a loop; run the coroutine in a worker thread
                        cit_result = run_coroutine_sync(
                            extract_article_citations(
                                mst=mst, law_name=top["law_name"],
                                article=art_num, article_branch=0,
                            )
                        )
                        api_calls += 1
                        if cit_result.get("success") is False:
                            errs = "; ".join(
                                redact_oc(str(x), resolved_oc)
                                for x in (cit_result.get("errors") or ["unknown error"])
                            )
                            resolver_warnings.append(
                                f"인용 관계 추출에 실패했습니다 ({errs})"
                            )
                        if slim_enabled() and len(cit_result.get("citations", [])) > 10:
                            slim_cut = True
                        for c in cit_result.get("citations", [])[:compact_limit(10)]:
                            citations.append({
                                "from_law": top["law_name"],
                                "from_article": f"제{art_num}조",
                                "to_law": c.get("target_law_name") or top["law_name"],
                                "to_article": f"제{c.get('target_article', '')}조" if c.get("target_article") else "",
                                "type": c.get("type", ""),
                            })
                except Exception as e:
                    # Citation extraction is best-effort, but report why it failed
                    resolver_warnings.append(
                        f"인용 관계 추출에 실패했습니다 ({e.__class__.__name__}: "
                        f"{redact_oc(str(e), resolved_oc)})"
                    )

        # Step 4: Legal interpretations
        interpretations = []
        expc_params = {
            "oc": resolved_oc, "target": "expc", "type": type,
            "query": situation, "display": 3, "page": 1, "search": 1,
        }
        expc_result = run_search(
            get_client=_get_client, target="expc", query=situation,
            snake_params=expc_params, response_type=type, display=3,
            ranking_field="사건명", list_type="items", item_category="expc",
            over_fetch_key="display",
        )
        api_calls += 1
        attempted += 1
        _e = _result_error(expc_result, "expc")
        if _e:
            failures.append(_e)

        expc_ranked = expc_result.get("ranked_data", {})
        for key, val in expc_ranked.items():
            if isinstance(val, list):
                for e in val[:3]:
                    interpretations.append({
                        "id": e.get("법령해석례일련번호", ""),
                        "title": e.get("안건명", ""),
                        "date": e.get("회신일자", ""),
                    })
                break

        result = {
            "status": "ok",
            "situation": situation,
            "applicable_laws": applicable_laws,
            "related_precedents": related_precedents,
            "legal_interpretations": interpretations,
            "citations": citations,
            "laws_analyzed": len(law_names_seen),
            "api_calls_made": api_calls,
            "disclaimer": "이 분석은 참고용이며 법률 자문이 아닙니다. 정확한 판단을 위해 변호사와 상담하세요.",
        }
        if failures and len(failures) >= attempted:
            return _all_failed_response(failures)
        if failures:
            resolver_warnings = _failure_warnings(failures) + resolver_warnings
        if resolver_warnings:
            result["warnings"] = resolver_warnings
        if not failures and not applicable_laws and not related_precedents and not interpretations:
            result.update(_no_results_fields())
        if slim_cut:
            mark_slim_cut(result, "SLIM_RESPONSE: 조문 본문(500자)과 인용(조문당 10건)이 줄었습니다. 전문은 eflaw_service(jo=...)·article_citation으로 조회하세요.")
        return result

    # ==================== TOOL 47: simplify_article ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def simplify_article(
        law_name: str,
        article: Union[int, str],
        article_branch: Union[int, str] = 0,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Get a law article plus a glossary of its legal terms (쉬운 법률 읽기).

        Fetches a law article (heading + 항 + 호 + 목, from the 현행 version of the
        law) and lists, in term_glossary, exact 동의어 links from the 법제처 legal
        terminology database. The article text is never rewritten: simplified_text
        equals original_text, and the links may differ from the legal meaning.

        Args:
            law_name: Law name (e.g., "민법", "근로기준법")
            article: Article number (e.g., 750 for 제750조). Strings such as
                "35의5" or "제35조의5" are accepted too.
            article_branch: Branch number (e.g., 2 for 제37조의2, default 0)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Original text (unchanged), and a term glossary of database synonym links

        Examples:
            >>> simplify_article(law_name="민법", article=750)
            >>> simplify_article(law_name="건축법", article=37, article_branch=2)
        """
        from .linkage import pick_linked_term

        resolved_oc = resolve_oc(override_oc=oc)
        fmt = _internal_format(type)
        article, article_branch = normalize_article(article, article_branch)

        # Step 1: Resolve the law and pick its 현행 version (not the first row,
        # which is typically a 시행예정 MST)
        law_info = _resolve_law_versions(law_name, resolved_oc, fmt)
        if law_info.get("status") == "error":
            return law_info
        current = law_info["current"]
        mst = str(current.get("법령일련번호", ""))
        if not mst:
            raise ValueError(f"법령 '{law_name}'의 MST를 확인할 수 없습니다.")

        # Step 2: Get article text — lawService.do?target=law&MST=…&JO=…
        # (full text: heading + 항내용 + 호내용 + 목내용)
        article_info = _fetch_article(mst, article, article_branch, resolved_oc, fmt)
        original_text = article_info["text"]
        client = _get_client()

        # Step 3: Extract legal terms
        terms = list(dict.fromkeys(extract_legal_terms(original_text)))

        # Step 4: Look up each term in knowledge base
        glossary = []
        terms_mapped = 0

        for term in terms:
            plain_korean = ""
            relation = ""
            ambiguous = False
            source = "not_found"

            # Try 법령용어→일상용어
            try:
                # 지식베이스 연계 API는 lawService.do 전용 (lawSearch.do는 빈 응답)
                term_params = {
                    "oc": resolved_oc, "target": "lstrmRlt", "type": "JSON",
                    "query": term,
                }
                upstream = map_params_to_upstream(term_params)
                term_result = client.get("/DRF/lawService.do", upstream, "JSON")
                term_raw = term_result.get("raw_content", "")
                if term_raw:
                    import json as _json
                    td = _json.loads(term_raw)
                    root = list(td.values())[0] if td else {}
                    plain_korean, relation, ambiguous = pick_linked_term(root, "일상용어명", term)
                    if plain_korean:
                        source = "법령용어DB"
            except:
                pass

            # Try 일상용어→법령용어 (reverse)
            if not plain_korean:
                try:
                    term_params2 = {
                        "oc": resolved_oc, "target": "dlytrmRlt", "type": "JSON",
                        "query": term,
                    }
                    upstream2 = map_params_to_upstream(term_params2)
                    term_result2 = client.get("/DRF/lawService.do", upstream2, "JSON")
                    term_raw2 = term_result2.get("raw_content", "")
                    if term_raw2:
                        import json as _json
                        td2 = _json.loads(term_raw2)
                        root2 = list(td2.values())[0] if td2 else {}
                        plain_korean, relation, amb2 = pick_linked_term(root2, "법령용어명", term)
                        ambiguous = ambiguous or amb2
                        if plain_korean:
                            source = "일상용어DB"
                except:
                    pass

            entry = {
                "term": term,
                "plain_korean": plain_korean,
                "relation": relation,
                "source": source,
            }
            if ambiguous and not plain_korean:
                entry["source"] = "ambiguous"
                entry["note"] = "동음이의어가 여러 개라 뜻을 특정할 수 없어 연결하지 않았습니다"
            glossary.append(entry)

            if plain_korean:
                terms_mapped += 1

        article_display = f"제{article}조" if article_branch == 0 else f"제{article}조의{article_branch}"

        result = {
            "status": "ok",
            "law_name": law_info["law_name"],
            "query": law_name,
            "article": article_display,
            "article_title": article_info.get("title", ""),
            "mst": mst,
            "version": {
                "status": current.get("현행연혁코드", ""),
                "date": current.get("공포일자", ""),
                "announcement_no": current.get("공포번호", ""),
                "effective_date": current.get("시행일자", ""),
                "law_type": current.get("법령구분명", ""),
            },
            "original_text": original_text,
            "simplified_text": original_text,
            "term_glossary": glossary,
            "terms_found": len(terms),
            "terms_mapped": terms_mapped,
            "disclaimer": "용어 해설은 법제처 법령용어 데이터베이스 기준이며, 맥락에 따라 의미가 다를 수 있습니다.",
        }
        result["note"] = (
            "simplified_text는 법률 원문과 같으며 본문을 바꾸지 않았습니다. term_glossary의 항목은 "
            "법령용어DB의 동의어 연결일 뿐 법적 의미와 다를 수 있으므로 원문 해석에 쓰지 마세요."
            + ("" if terms_mapped else " 이번 조문에서는 연결된 용어가 없었습니다.")
        )
        return result

    # ==================== TOOL 48: law_amendment_summary ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def law_amendment_summary(
        law_name: str,
        date_from: Annotated[str, Field(description="시작일 YYYYMMDD (기본 20100101). 기본적으로 '공포일' 기준이며 시행일이 아님 (date_basis로 변경). Start of range.")] = "20100101",
        date_to: Annotated[Optional[str], Field(description="종료일 YYYYMMDD (기본: 올해 말). 기본은 공포일 기준. End of range.")] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        date_basis: Annotated[str, Field(description="date_from/date_to를 무엇에 적용할지: 'announced'(기본, 공포일자) 또는 'effective'(시행일자; 이 경우 date_from 당시 시행 중이던 개정본도 in_force_at_period_start=true로 포함해 좁은 구간에서도 누락되지 않음). Which date the range filters.")] = "announced",
        ctx: Context = None,
    ) -> dict:
        """
        List a law's revisions (법령 개정 이력 조회). date_from/date_to filter by 공포일 (announcement) by default, NOT 시행일; use date_basis="effective" to filter by 시행일 and keep the revision in force at date_from. For the text as of a date use law_as_of.

        Resolves the name to a single 법령ID (법률 preferred over 시행령/시행규칙
        unless you name the 시행령) and lists every version of that law —
        연혁, 현행 and 시행예정 — announced in the range. Use the MST values from
        the results with article_amendment_diff to see specific article changes.

        Args:
            law_name: Law name (e.g., "근로기준법")
            date_from: Start date YYYYMMDD (default "20100101")
            date_to: End date YYYYMMDD (default: end of the current year)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"
            date_basis: "announced" (default; range applies to 공포일자) or "effective" (range applies to
                each (MST, 시행일자); the revision in force at date_from is also returned, marked
                in_force_at_period_start)

        Returns:
            Revisions (date, effective_date, type, announcement_no, mst, status,
            law_type) sorted by announcement date, newest first; with date_basis="effective"
            one record per (MST, 시행일자), newest 시행일 first

        Examples:
            >>> law_amendment_summary(law_name="근로기준법", date_from="20200101")
            >>> law_amendment_summary(law_name="민법", date_from="20150101", date_to="20251231")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        fmt = _internal_format(type)
        date_to = date_to or end_of_current_year()
        validate_date_range(f"{date_from}~{date_to}", "date_from~date_to")

        # Resolve to one 법령ID and fetch all of its versions (eflaw, LID filter)
        law_info = _resolve_law_versions(law_name, resolved_oc, fmt, need_history=True)
        if law_info.get("status") == "error":
            return law_info

        basis = (date_basis or "announced").strip().lower()
        if basis not in ("announced", "effective"):
            raise ValueError("date_basis must be 'announced' (공포일) or 'effective' (시행일).")
        if basis == "effective":
            ecands = build_candidates(law_info["rows"])
            in_range = [c for c in ecands if date_from <= c["effective_date"] <= date_to]
            start = select_as_of(ecands, date_from)["selected"]
            revisions = []
            if start is not None and all(start is not c for c in in_range):
                rec = revision_record(start["row"])
                rec["in_force_at_period_start"] = True
                revisions.append(rec)
            revisions.extend(revision_record(c["row"]) for c in in_range)
            revisions.sort(key=lambda r: (r["effective_date"], r["date"], r["announcement_no"]), reverse=True)
        else:
            revisions = [
                revision_record(row) for row in law_info["versions"]
                if date_from <= (row.get("공포일자", "") or "") <= date_to
            ]
        current = law_info.get("current") or {}

        out = {
            "status": "ok",
            "law_name": law_info["law_name"],
            "query": law_name,
            "law_id": law_info["law_id"],
            "law_type": law_info["law_type"],
            "period": f"{date_from}~{date_to}",
            "current_mst": str(current.get("법령일련번호", "")),
            "revisions": revisions,
            "total_revisions": len(revisions),
            "total_versions": len(law_info["versions"]),
            "date_basis": basis,
            "date_filter_field": "시행일자" if basis == "effective" else "공포일자",
            "source": "eflaw_search (target=eflaw, 법령ID filter; 현행연혁코드 = status)",
        }
        if law_info.get("warnings"):
            out["warnings"] = law_info["warnings"]
        return out

    # ==================== TOOL 49: article_amendment_diff ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def article_amendment_diff(
        mst_old: Union[str, int],
        mst_new: Union[str, int],
        article: Union[int, str],
        article_branch: Union[int, str] = 0,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Compare how a specific article changed between two law versions (조문 신구대조).

        Fetches the full article text (heading + 항 + 호 + 목) from each MST via
        lawService.do?target=law&MST=…&JO=… and diffs them line by line.
        Use MST values from law_amendment_summary (same 법령ID) for both sides.

        Args:
            mst_old: MST of the older version (법령일련번호, from law_amendment_summary)
            mst_new: MST of the newer version
            article: Article number (e.g., 52 for 제52조; "35의5" also accepted)
            article_branch: Branch number (e.g., 2 for 제52조의2, default 0)
            oc: Optional OC override
            type: Response format - "JSON" (default), "XML", or "HTML"

        Returns:
            Side-by-side comparison with line-level diff

        Examples:
            >>> article_amendment_diff(mst_old="270165", mst_new="283335", article=35, article_branch=5)
        """
        resolved_oc = resolve_oc(override_oc=oc)
        fmt = _internal_format(type)
        mst_old, mst_new = stringify_id(mst_old, mst_new)
        if not mst_old or not mst_new:
            raise ValueError("mst_old and mst_new are both required (법령일련번호).")
        article, article_branch = normalize_article(article, article_branch)
        article_display = article_label(article, article_branch)

        def _try_fetch(mst: str):
            try:
                return _fetch_article(mst, article, article_branch, resolved_oc, fmt), None
            except ArticleNotFoundError as e:
                return None, str(e)

        old_info, old_err = _try_fetch(mst_old)
        new_info, new_err = _try_fetch(mst_new)

        if old_info is None and new_info is None:
            raise ToolValidationError(
                f"{article_display} 텍스트를 두 버전(MST {mst_old}, {mst_new}) 모두에서 찾을 수 없습니다.",
                hints=[h for h in (old_err, new_err) if h] + [
                    "law_amendment_summary로 같은 법령ID의 MST인지, 조문 번호/가지번호가 맞는지 확인하세요.",
                ],
            )

        old_meta = _version_meta(old_info) if old_info else {"mst": mst_old, "text": "", "note": old_err}
        new_meta = _version_meta(new_info) if new_info else {"mst": mst_new, "text": "", "note": new_err}
        old_text = old_meta.get("text", "")
        new_text = new_meta.get("text", "")

        same_law = bool(
            old_info and new_info
            and old_info["law"].get("law_id") and new_info["law"].get("law_id")
            and old_info["law"].get("law_id") == new_info["law"].get("law_id")
        )
        warning = None
        if old_info and new_info and not same_law:
            warning = (
                f"서로 다른 법령을 비교하고 있습니다: {old_info['law'].get('law_name')} "
                f"(ID {old_info['law'].get('law_id')}) vs {new_info['law'].get('law_name')} "
                f"(ID {new_info['law'].get('law_id')})"
            )

        # Handle article added/deleted
        if not old_text:
            result = {
                "status": "ok",
                "article": article_display,
                "old_version": old_meta,
                "new_version": new_meta,
                "has_changes": True,
                "changes": [{"type": "added", "old_line": None, "new_line": line} for line in new_text.splitlines()],
                "unified_diff": "\n".join(f"+{line}" for line in new_text.splitlines()),
                "summary": "Article added in new version (old version has no such article)",
            }
        elif not new_text:
            result = {
                "status": "ok",
                "article": article_display,
                "old_version": old_meta,
                "new_version": new_meta,
                "has_changes": True,
                "changes": [{"type": "deleted", "old_line": line, "new_line": None} for line in old_text.splitlines()],
                "unified_diff": "\n".join(f"-{line}" for line in old_text.splitlines()),
                "summary": "Article deleted in new version (new version has no such article)",
            }
        else:
            changes, unified, summary = compute_text_diff(old_text, new_text)
            result = {
                "status": "ok",
                "article": article_display,
                "old_version": old_meta,
                "new_version": new_meta,
                "has_changes": len(changes) > 0,
                "changes": changes,
                "unified_diff": unified,
                "summary": summary if changes else "No textual changes between the two versions",
            }
        if warning:
            result["warning"] = warning
        return result

    # ==================== PHASE 9: CHAIN TOOLS & UTILITIES ====================

    # ==================== TOOL 50: chain_full_research ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def chain_full_research(
        query: str,
        display: int = 5,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Complete legal research in one call (종합 법률 조사).

        Chains: AI search → statutes → precedents with outcome analysis → interpretations → citations.
        This is the most comprehensive single-call research tool.

        Args:
            query: Natural language query (e.g., "음주운전 처벌 기준", "임대차 보증금 반환")
            display: Results per sub-query (default 5)
            oc: Optional OC override
            type: Response format

        Returns:
            Combined legal analysis with statutes, precedent statistics, interpretations, and citations

        Examples:
            >>> chain_full_research(query="부당해고 구제")
            >>> chain_full_research(query="개인정보 유출 신고 의무")
        """
        # Step 1: Get base legal analysis from legal_resolver
        base = legal_resolver(situation=query, display=display, oc=oc, type=type, ctx=ctx)

        # Step 2: Add precedent outcome analysis
        odds = check_precedent_odds(query=query, display=20, top_n=5, oc=oc, type=type, ctx=ctx)

        step_errors = [
            {"source": name, "error_code": r.get("error_code") or ErrorCode.UPSTREAM_ERROR}
            for name, r in (("legal_resolver", base), ("check_precedent_odds", odds))
            if r.get("status") != "ok"
        ]
        if len(step_errors) == 2:
            # expand to the underlying failed sub-sources when available
            detail = [f for r in (base, odds) for f in (r.get("failed_sources") or [])]
            return _all_failed_response(detail or step_errors)

        # Combine
        result = {
            "status": "ok",
            "query": query,
            "applicable_laws": base.get("applicable_laws", []),
            "precedent_analysis": {
                "total_found": odds.get("total_found", 0),
                "outcome_summary": odds.get("outcome_summary", {}),
                "outcome_note": odds.get("outcome_note", OUTCOME_NOTE),
                "key_factors": odds.get("key_factors", []),
                "representative_cases": odds.get("representative_cases", [])[:compact_limit(3)],
                "search_mode": odds.get("search_mode", ""),
            },
            "legal_interpretations": base.get("legal_interpretations", []),
            "citations": base.get("citations", []),
            "api_calls_made": base.get("api_calls_made", 0) + odds.get("analyzed", 0) + 1,
            "disclaimer": "이 분석은 참고용이며 법률 자문이 아닙니다.",
        }
        if slim_enabled() and len(odds.get("representative_cases", [])) > 3:
            mark_slim_cut(result, "SLIM_RESPONSE: 대표 판례를 3건으로 줄였습니다. 나머지는 check_precedent_odds(top_n=...)로 조회하세요.")
        for src in (base, odds):
            for note in src.get("truncated_notes") or []:
                mark_slim_cut(result, note)
        warnings = list(base.get("warnings") or []) + list(odds.get("warnings") or [])
        for e in step_errors:
            warnings.append(f"{e['source']} 조회 실패 ({e['error_code']}): 결과가 누락되었을 수 있습니다")
        if warnings:
            result["warnings"] = warnings
        return result

    # ==================== TOOL 51: chain_amendment_track ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def chain_amendment_track(
        law_name: str,
        article: Union[int, str] = 0,
        date_from: str = "20200101",
        date_to: Optional[str] = None,
        article_branch: Union[int, str] = 0,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Track law amendment history with optional article-level diff (법령 개정 추적).

        Chains: revision list (one 법령ID, 연혁/현행/시행예정) → per-article change
        history (lsJoHstInf) → full-text diff of the article between two adjacent
        versions of the SAME law. If article=0, returns only the revision list.

        Version pair selection: the most recent version in the period where
        lsJoHstInf says the article changed, against the version right before
        it; if no article-level history is available, the two most recent
        revisions in the period.

        Args:
            law_name: Law name (e.g., "근로기준법")
            article: Article number to diff (0 = summary only; 52, "35의5", "제35조의5")
            date_from: Start date YYYYMMDD (default "20200101")
            date_to: End date YYYYMMDD (default: end of the current year)
            article_branch: Branch number (e.g., 5 for 제35조의5, default 0)
            oc: Optional OC override
            type: Response format

        Returns:
            Revision history, article change history and optional article diff

        Examples:
            >>> chain_amendment_track(law_name="근로기준법")
            >>> chain_amendment_track(law_name="저작권법", article=35, article_branch=5)
        """
        resolved_oc = resolve_oc(override_oc=oc)
        fmt = _internal_format(type)
        date_to = date_to or end_of_current_year()
        validate_date_range(f"{date_from}~{date_to}", "date_from~date_to")

        # Step 1: Resolve the law and list every version of that single 법령ID
        law_info = _resolve_law_versions(law_name, resolved_oc, fmt, need_history=True)
        if law_info.get("status") == "error":
            return law_info
        all_versions = [revision_record(r) for r in law_info["versions"]]
        revisions = [r for r in all_versions if date_from <= r["date"] <= date_to]
        current = law_info.get("current") or {}

        result = {
            "status": "ok",
            "law_name": law_info["law_name"],
            "query": law_name,
            "law_id": law_info["law_id"],
            "law_type": law_info["law_type"],
            "current_mst": str(current.get("법령일련번호", "")),
            "revisions": revisions,
            "total_revisions": len(revisions),
            "period": f"{date_from}~{date_to}",
        }
        if law_info.get("warnings"):
            result["warnings"] = law_info["warnings"]

        if not article or str(article).strip() in ("0", ""):
            return result

        # Step 2: Article-level change history (lsJoHstInf) for the same 법령ID
        number, branch = normalize_article(article, article_branch)
        jo = format_article_number(number, branch)
        history: list = []
        if law_info["law_id"]:
            hist_params = {
                "oc": resolved_oc, "target": "lsJoHstInf", "type": fmt,
                "id": law_info["law_id"], "jo": jo, "display": 100,
            }
            hist_result = run_service(
                get_client=_get_client, target="lsJoHstInf",
                snake_params=hist_params, response_type=fmt,
            )
            if hist_result.get("status") == "ok":
                history = parse_article_history(hist_result.get("raw_content", ""), fmt)
        result["article"] = article_label(number, branch)
        result["article_history"] = history

        # Step 3: Choose two adjacent versions of this law to diff
        pair = None
        basis = ""
        known = {v["mst"]: v for v in all_versions}
        for change in history:
            change_date = change.get("date") or change.get("change_date") or ""
            if not (date_from <= change_date <= date_to):
                continue
            newer = known.get(change["mst"])
            if not newer:
                continue
            older = previous_version(all_versions, change["mst"])
            if older:
                pair = (older, newer)
                basis = f"lsJoHstInf: {change.get('change_date')} {change.get('reason')} (MST {change['mst']})"
                break
        if pair is None and len(revisions) >= 2:
            # Prefer in-force versions (현행/연혁): two 시행예정 rows, or a 시행예정
            # vs. an in-force one, are not a meaningful before/after pair.
            in_force = [r for r in revisions if r.get("status") != "시행예정"]
            candidates = in_force if len(in_force) >= 2 else revisions
            pair = (candidates[1], candidates[0])
            why = ("lsJoHstInf had no entry in the period" if not history else
                   f"none of the {len(history)} lsJoHstInf entries matched a version in the period")
            basis = (
                f"fallback: latest two {'in-force (현행/연혁)' if candidates is in_force else 'listed'} "
                f"revisions in period, MST {candidates[1]['mst']} vs {candidates[0]['mst']} "
                f"(article-level history did not match: {why})"
            )

        if pair is None:
            result["article_diff"] = None
            result["note"] = "비교할 두 버전이 없습니다 (기간 내 개정이 1건 이하)."
            return result

        older, newer = pair
        diff = article_amendment_diff(
            mst_old=older["mst"], mst_new=newer["mst"], article=number,
            article_branch=branch, oc=oc, type=type, ctx=ctx,
        )
        if diff.get("status") != "ok":
            result["article_diff"] = {
                "article": article_label(number, branch),
                "old_mst": older["mst"], "new_mst": newer["mst"],
                "basis": basis,
                "error": diff,
            }
            return result

        result["article_diff"] = {
            "article": diff.get("article", ""),
            "basis": basis,
            "old_mst": older["mst"],
            "old_date": older.get("date", ""),
            "old_status": older.get("status", ""),
            "new_mst": newer["mst"],
            "new_date": newer.get("date", ""),
            "new_status": newer.get("status", ""),
            "has_changes": diff.get("has_changes", False),
            "changes": diff.get("changes", []),
            "summary": diff.get("summary", ""),
            "old_text": diff.get("old_version", {}).get("text", ""),
            "new_text": diff.get("new_version", {}).get("text", ""),
        }
        if diff.get("warning"):
            result["article_diff"]["warning"] = diff["warning"]
        return result

    # ==================== TOOL 52: chain_dispute_prep ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def chain_dispute_prep(
        query: str,
        display: int = 5,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Prepare for a legal dispute by gathering all case law (분쟁 준비 자료).

        Chains: precedent search + admin appeals + constitutional decisions + special tribunal.
        Gathers all decision-type legal sources in one call.

        Args:
            query: Dispute topic (e.g., "부당해고", "개인정보 유출", "조세 부과 취소")
            display: Results per category (default 5)
            oc: Optional OC override
            type: Response format

        Returns:
            Precedents, admin appeals, constitutional decisions, and special tribunal decisions

        Examples:
            >>> chain_dispute_prep(query="부당해고")
            >>> chain_dispute_prep(query="개인정보 유출 과징금")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        fmt = _internal_format(type)
        results = {}
        search_modes = {}

        # Each source: 사건명(search=1) first, 본문(search=2) fallback when the
        # case-name search returns fewer than `display` hits.
        sources = [
            ("precedents", "prec", "판례명", "prec"),
            ("admin_appeals", "decc", "사건명", "decc"),
            ("constitutional_decisions", "detc", "사건명", "detc"),
            ("special_tribunal", "ttSpecialDecc", "사건명", "decc"),
        ]
        failures: list = []
        n_failed_sources = 0
        for key, target, ranking_field, category in sources:
            found = _search_with_fallback(
                target=target, query=query, display=display, response_type=fmt,
                resolved_oc=resolved_oc, ranking_field=ranking_field,
                item_category=category, min_results=display,
            )
            results[key] = found["items"][:display]
            search_modes[key] = {"mode": found["mode"], "total_found": found["total"]}
            failures.extend(found["errors"])
            n_failed_sources += 1 if found["all_failed"] else 0
            if found["all_failed"]:
                search_modes[key]["error_code"] = found["errors"][-1]["error_code"]

        if n_failed_sources == len(sources):
            return _all_failed_response(failures)
        total = sum(len(v) for v in results.values())

        response = {
            "status": "ok",
            "query": query,
            "total_results": total,
            "search_modes": search_modes,
            "precedents": results["precedents"],
            "admin_appeals": results["admin_appeals"],
            "constitutional_decisions": results["constitutional_decisions"],
            "special_tribunal": results["special_tribunal"],
            "disclaimer": "이 자료는 참고용이며 법률 자문이 아닙니다.",
        }
        if failures:
            response["warnings"] = _failure_warnings(failures)
        elif total == 0:
            response.update(_no_results_fields(body_search=True))
        return response

    # ==================== TOOL 53: chain_law_system ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def chain_law_system(
        law_name: str,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Map the full law system hierarchy (법령 체계 조회).

        Chains: law search → delegation tree → related admin rules → linked ordinances.
        Shows how a law connects to its subordinate regulations.

        Args:
            law_name: Law name (e.g., "건축법", "근로기준법")
            oc: Optional OC override
            type: Response format

        Returns:
            Law hierarchy: parent law, delegated decrees/rules, linked ordinances

        Examples:
            >>> chain_law_system(law_name="건축법")
            >>> chain_law_system(law_name="개인정보 보호법")
        """
        resolved_oc = resolve_oc(override_oc=oc)

        # Step 1: Find the law — one 법령ID, 현행 version preferred over 시행예정
        fmt = _internal_format(type)
        resolved = _resolve_law_versions(law_name, resolved_oc, fmt)
        if resolved.get("status") == "error":
            return resolved
        law_info = resolved["current"]
        law_id = resolved["law_id"]
        mst = str(law_info.get("법령일련번호", ""))

        result = {
            "status": "ok",
            "law_name": resolved["law_name"],
            "law_id": law_id,
            "mst": mst,
            "version_status": law_info.get("현행연혁코드", ""),
            "effective_date": law_info.get("시행일자", ""),
            "law_type": resolved["law_type"],
            "ministry": law_info.get("소관부처명", ""),
        }

        warnings: list[str] = []

        # Step 2: Get delegation tree
        delegated_entries: list = []
        if law_id or mst:
            del_params = {
                "oc": resolved_oc, "target": "lsDelegated", "type": type,
            }
            if law_id:
                del_params["id"] = law_id
            elif mst:
                del_params["mst"] = mst
            del_upstream = map_params_to_upstream(del_params)
            client = _get_client()
            del_r = client.get("/DRF/lawService.do", del_upstream, type)
            if del_r.get("status") == "ok":
                # Compact structure instead of a JSON string cut mid-way
                result["delegation_tree"] = compact_delegation_tree(
                    del_r.get("raw_content", ""), type, max_entries=compact_limit(80),
                )
                if result["delegation_tree"].get("truncated"):
                    mark_slim_cut(result, "SLIM_RESPONSE: 위임 조문 목록을 80건으로 줄였습니다. 전체는 lsDelegated_service 또는 jo 지정 조회를 쓰세요.")
                delegated_entries = compact_delegation_tree(
                    del_r.get("raw_content", ""), type,
                ).get("entries", [])
            else:
                result["delegation_tree"] = {
                    "entries": [], "entry_count": 0,
                    "note": del_r.get("message", "lsDelegated 조회 실패"),
                }
                warnings.append(
                    f"lsDelegated 조회 실패 ({del_r.get('error_code') or ErrorCode.UPSTREAM_ERROR}): "
                    "admin_rules를 확인하지 못했습니다"
                )

        # Step 3: Linked ordinances (자치법규) — lnkLsOrd lists the ordinances
        # that implement this law (lnkLs would list laws, not ordinances).
        linked_ordinances: list = []
        if law_id:
            lnk_params = {
                "oc": resolved_oc, "target": "lnkLsOrd", "type": type,
                "knd": law_id, "display": 10, "page": 1,
            }
            lnk_r = run_search(
                get_client=_get_client, target="lnkLsOrd", query="*",
                snake_params=lnk_params, response_type=type, display=10,
                ranking_field="자치법규명", list_type="law",
                over_fetch_key="display",
            )
            lnk_err = _result_error(lnk_r, "lnkLsOrd 연계 자치법규")
            if lnk_err:
                warnings.extend(_failure_warnings([lnk_err]))
            else:
                _, lnk_total = _items_from_result(lnk_r, type)
                for item in law_rows(lnk_r)[:10]:
                    linked_ordinances.append({
                        "name": item.get("자치법규명", ""),
                        "id": item.get("자치법규ID", ""),
                        "type": item.get("자치법규종류", ""),
                    })
                result["linked_ordinances_total"] = lnk_total
        result["linked_ordinances"] = linked_ordinances

        # Step 4: Admin rules — the 위임행정규칙 entries of the delegation tree.
        # (admrul title search for the law name returns nothing for most laws,
        # e.g. 건축법, and the body search returns unrelated rules.)
        admin_rules: list = []
        seen_rules: set = set()
        for entry in delegated_entries:
            if entry.get("kind") != "위임행정규칙" or entry.get("target") in seen_rules:
                continue
            seen_rules.add(entry.get("target"))
            admin_rules.append({
                "name": entry.get("target", ""),
                "id": entry.get("target_id", ""),
                "article": entry.get("article", ""),
            })
        result["admin_rules"] = admin_rules
        if warnings:
            result["warnings"] = warnings

        return result

    # ==================== TOOL 54: cache_stats ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def cache_stats(ctx: Context = None) -> dict:
        """
        Show cache and resolver statistics (캐시 통계).

        Returns current cache hit rate, entry count, and law name resolver stats.
        Useful for monitoring server performance.

        Returns:
            Cache statistics and resolver stats
        """
        from .cache import get_cache
        from .resolver import get_resolver

        return {
            "status": "ok",
            "cache": get_cache().stats(),
            "resolver": get_resolver().stats(),
        }

    # ==================== TOOL 55: law_as_of ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def law_as_of(
        law_name: Annotated[str, Field(description=(
            "법령명(예: '근로기준법') 또는 법령ID(예: '001872'). Law name or 6-digit 법령ID."))],
        as_of: Annotated[Union[str, int], Field(description=(
            "기준일 D = 사건 발생일/계약일/처분일 등 '그 날 시행 중이던' 법령을 알고 싶은 날짜. "
            "20160503, 2016-05-03, 2016.5.3., 2016/5/3, 2016년 5월 3일 모두 허용. "
            "The incident date D goes HERE (never into ef_yd of other tools)."))],
        article: Annotated[Optional[Union[str, int]], Field(description=(
            "조문(선택): 23, '제23조', '76의2', '003505'. 생략하면 법령 헤더(MST·시행일·공포일)만 반환."))] = None,
        article_branch: Annotated[Union[int, str], Field(description=(
            "article이 숫자일 때 가지번호(제3조의2 → article=3, article_branch=2). 기본 0."))] = 0,
        as_of_end: Annotated[Optional[Union[str, int]], Field(description=(
            "기간 조회 종료일(선택). 주면 as_of~as_of_end 동안 시행된 모든 개정본(시행일 기준)과 조문을 "
            "period.revisions로 반환. 기간 중 개정이 있었는지 볼 때 사용."))] = None,
        oc: Optional[str] = None,
        type: str = "JSON",
        ctx: Context = None,
    ) -> dict:
        """
        Law/article text in force on date D (기준일·사건일 시점 조회): picks the revision with the latest 시행일 <= D and returns its MST, 시행일, 공포일, article text, whether it differs from the current text, and 시행예정 versions. Use this for any "as of date" question; do NOT put D into ef_yd of eflaw_service/eflaw_josub/eflaw_search.

        law.go.kr has no "in force on D" query: its ef_yd arguments are a 시행일 range
        filter (search) or a revision selector that must equal one of an MST's own 시행일
        (service). This tool lists every (MST, 시행일) of the law, selects the right one and
        fetches that exact revision (lawService target=eflaw, MST + efYd).

        Args:
            law_name: Law name (e.g., "근로기준법") or a 법령ID (e.g., "001872")
            as_of: The date D. Accepts 20160503, 2016-05-03, 2016.5.3., 2016/5/3
                or 2016년 5월 3일. Invalid dates (20160231) give VALIDATION_ERROR.
            article: Optional article, e.g. 23, "23", "제23조", "76의2", "003505"
            article_branch: Branch number when article is a plain number (3 for 제N조의3)
            as_of_end: Optional end of a period; returns every revision in force between as_of and as_of_end
            oc: Optional OC override
            type: "JSON" (default) or "XML"

        Returns:
            status "ok" with in_force true: as_of, version (mst, effective_date, announced_date,
            announcement_no, revision_type, status), valid_from/valid_until, article (label, title,
            text), comparison (is_current_version, differs_from_current for the article, current_version),
            later_amendments {exists, count, next_effective_date}, scheduled_version_exists
            (+ scheduled_versions), promulgated_not_yet_effective, same_day_alternatives, partial_effect,
            period (with as_of_end), neighbors, statement, caveats.
            status "ok" with in_force false: reason BEFORE_FIRST_ENFORCEMENT,
            BEFORE_EARLIEST_AVAILABLE_VERSION or AFTER_REPEAL (not an error).
            status "error": VALIDATION_ERROR (bad date/article/law), ARTICLE_NOT_FOUND
            (article absent in that revision, with the date context) or the upstream
            error code (an upstream failure is never reported as "not found").

        Examples:
            >>> law_as_of(law_name="근로기준법", as_of="2019-07-15", article=76, article_branch=2)
            >>> law_as_of(law_name="민법", as_of="2015.1.1.", article="제750조")
            >>> law_as_of(law_name="근로기준법", as_of="2018-01-01", as_of_end="2020-12-31", article=53)
        """
        resolved_oc = resolve_oc(override_oc=oc)
        fmt = _internal_format(type)
        d = normalize_as_of(as_of)
        end = normalize_as_of(as_of_end) if as_of_end not in (None, "") else None
        if end and end < d:
            raise ValueError(f"as_of_end ({end}) must not be earlier than as_of ({d}).")
        wanted = normalize_article(article, article_branch) if article not in (None, "") else None
        name = (law_name or "").strip()
        if not name:
            raise ToolValidationError("law_name (법령명 또는 법령ID) is required.")
        by_id = re.fullmatch(r"\d{1,6}", name) is not None
        law_id = name.zfill(6) if by_id else ""

        info = _resolve_law_versions("" if by_id else name, resolved_oc, fmt,
                                     need_history=True, law_id=law_id,
                                     include_repealed=True)
        if info.get("status") == "error":
            return info
        cands = build_candidates(info["rows"])
        if not cands:
            raise ToolValidationError(
                f"법령 '{name}'의 시행일별 버전을 찾을 수 없습니다.",
                hints=["정식 법령명 또는 6자리 법령ID로 다시 시도하세요."],
            )

        today = _today()
        sel = select_as_of(cands, d)
        cur = select_as_of(cands, today)
        cur_c = cur["selected"] if cur["outcome"] == "in_force" else None
        slim = slim_enabled()
        law_label = info["law_name"]
        out: dict = {
            "status": "ok",
            "law": {"law_id": info["law_id"], "law_name": law_label,
                    "law_type": info["law_type"], "ministry": info["ministry"]},
            "as_of": d,
            "today": today,
            "total_versions": len(cands),
            "source": "eflaw_search (LID, nw=1,2,3) + lawService target=eflaw (MST, efYd)",
        }
        caveats = [
            "시행일자 기준 판정입니다. 부칙에서 조문별로 시행일을 달리 정한 경우, 법제처가 (MST, 시행일)별로 "
            "제공하는 본문을 그대로 신뢰한 것이며 조문별 개별 시행일은 따로 검증하지 않았습니다.",
        ]
        # history truncation notices produced by _resolve_law_versions (if any)
        for key in ("warnings", "history_warnings"):
            for w in info.get(key) or []:
                caveats.append(str(w))
        if info.get("history_truncated"):
            caveats.append("연혁 목록이 조회 상한에 도달해 오래된 버전이 누락되었을 수 있습니다.")
        incomplete = bool(info.get("history_truncated") or info.get("warnings") or info.get("history_warnings"))
        out["history_complete"] = not incomplete
        if info.get("warnings"):
            out["warnings"] = list(info["warnings"])

        # 시행예정 versions (effective after today) and versions promulgated but not yet effective on D
        scheduled = [c for c in cands if c["effective_date"] > today]
        out["scheduled_version_exists"] = bool(scheduled)
        pending = [c for c in cands if (c["row"].get("공포일자", "") or "") <= d < c["effective_date"]]
        out["promulgated_not_yet_effective_exists"] = bool(pending)
        if not slim:
            out["scheduled_versions"] = [describe(c) for c in scheduled]
            out["promulgated_not_yet_effective"] = [describe(c) for c in pending]

        fallback_used: list = []

        def fetch(c: dict):
            """(info, failure_response) for the article at one (MST, 시행일)."""
            jo = format_article_number(*wanted)
            res = run_service(
                get_client=_get_client, target="eflaw", response_type=fmt,
                snake_params={"oc": resolved_oc, "target": "eflaw", "type": fmt,
                              "mst": c["mst"], "ef_yd": c["effective_date"], "jo": jo},
            )
            if res.get("error_code") == ErrorCode.API_NOT_SUBSCRIBED:
                res = run_service(
                    get_client=_get_client, target="law", response_type=fmt,
                    snake_params={"oc": resolved_oc, "target": "law", "type": fmt,
                                  "mst": c["mst"], "jo": jo},
                )
                if res.get("status") == "ok" and not fallback_used:
                    fallback_used.append(True)
                    caveats.append("eflaw 본문 API 미신청으로 target=law(MST 단위)로 조회했습니다. "
                                   "시행일이 여럿인 MST는 조문이 기준일과 다를 수 있습니다.")
            if res.get("status") != "ok":
                return None, res
            return extract_article(res.get("raw_content", ""), fmt, *wanted), None

        def period_block(start_c) -> dict:
            """All revisions in force during [d, end]; article text per revision when requested."""
            revs = [start_c] if start_c is not None and sel["outcome"] == "in_force" else []
            efs = sorted({c["effective_date"] for c in cands
                          if d < c["effective_date"] <= end
                          and (not revs or c["effective_date"] > revs[0]["effective_date"])})
            for e in efs:
                revs.append(select_as_of(cands, e)["selected"])
            truncated = len(revs) > PERIOD_MAX
            revs = revs[:PERIOD_MAX]
            rows_out = []
            for i, c in enumerate(revs):
                nxt_c = revs[i + 1] if i + 1 < len(revs) else None
                until = day_before(nxt_c["effective_date"]) if nxt_c else None
                if nxt_c is None:
                    later = [x for x in cands if x["effective_date"] > c["effective_date"]]
                    until = day_before(later[0]["effective_date"]) if later else None
                entry = {"version": describe(c), "valid_from": max(c["effective_date"], d),
                         "valid_until": min(until, end) if until else end}
                if is_repeal(c["row"]):
                    entry["repealed"] = True
                elif wanted:
                    try:
                        a, fail = fetch(c)
                    except ArticleNotFoundError:
                        entry["article_status"] = ErrorCode.ARTICLE_NOT_FOUND
                    else:
                        if fail is not None:
                            entry["article_status"] = fail.get("error_code") or ErrorCode.UPSTREAM_ERROR
                        else:
                            entry["article"] = {"label": a["article"], "title": a["title"], "text": a["text"]}
                rows_out.append(entry)
            block = {"from": d, "to": end, "revision_count": len(rows_out), "revisions": rows_out}
            if wanted:
                texts = {re.sub(r"\s+", "", e["article"]["text"]) if "article" in e else "\0absent"
                         for e in rows_out}
                block["article_changed_within_period"] = len(texts) > 1
            if truncated:
                block["truncated"] = True
                caveats.append(f"기간 내 개정본이 많아 처음 {PERIOD_MAX}개만 조회했습니다.")
            return block

        if sel["outcome"] == "before_first_version":
            first = cands[0]
            truly_new = (first["row"].get("제개정구분명", "") == "제정") and not incomplete
            out.update({
                "in_force": False,
                "reason": "BEFORE_FIRST_ENFORCEMENT" if truly_new else "BEFORE_EARLIEST_AVAILABLE_VERSION",
                "first_version": describe(first),
                "statement": (
                    f"{law_label}은(는) 기준일 {d}에 시행 전이었습니다. 최초 시행일은 {first['effective_date']}입니다."
                    if truly_new else
                    f"기준일 {d} 이전의 버전은 조회된 연혁에 없습니다(가장 이른 버전 시행일 {first['effective_date']}, "
                    f"{first['row'].get('제개정구분명', '')}). 그 이전에 시행 중이었는지는 확인할 수 없습니다."
                ),
            })
            if end:
                out["period"] = period_block(None)
            out["caveats"] = caveats
            return out

        chosen = sel["selected"]
        mst, eff = chosen["mst"], chosen["effective_date"]
        version = describe(chosen)
        if sel["outcome"] == "repealed":
            out.update({
                "in_force": False,
                "reason": "AFTER_REPEAL",
                "repealed_on": eff,
                "repealing_version": version,
                "last_version_before_repeal": describe(sel["previous"]),
                "statement": f"{law_label}은(는) {eff}자로 폐지되어 기준일 {d}에는 시행 중이 아니었습니다 "
                             f"(폐지 MST {mst}, {version['revision_type']}).",
            })
            if end:
                out["period"] = period_block(chosen)
            out["caveats"] = caveats
            return out

        mst_dates = sorted({c["effective_date"] for c in cands if c["mst"] == mst})
        nxt = sel["next"]
        later_all = [c for c in cands if c["effective_date"] > eff]
        out.update({
            "in_force": True,
            "version": version,
            "is_future_version": eff > today,
            "valid_from": eff,
            "valid_until": day_before(nxt["effective_date"]) if nxt else None,
            "later_amendments": {
                "exists": bool(later_all),
                "count": len({(c["mst"], c["effective_date"]) for c in later_all}),
                "next_effective_date": nxt["effective_date"] if nxt else None,
            },
            "partial_effect": {
                "possible": len(mst_dates) > 1,
                "mst_effective_dates": mst_dates,
                "note": ("이 개정(MST)은 시행일이 여러 개입니다(단계적 시행). 기준일에 해당하는 시행일 "
                         f"{eff} 기준 본문을 조회했습니다.") if len(mst_dates) > 1 else "",
            },
        })
        if sel["same_day"]:
            out["same_day_alternatives"] = [describe(c) for c in sel["same_day"]]
            caveats.append(
                f"같은 시행일 {eff}에 시행되는 버전이 {len(sel['same_day']) + 1}개입니다. "
                "공포일자가 가장 늦은 MST를 선택했습니다."
            )
        if eff > today:
            caveats.append("시행예정 버전입니다. 시행일 전에 다시 개정될 수 있습니다.")
        if pending:
            caveats.append(
                "기준일 현재 공포되었으나 아직 시행 전인 개정이 있습니다(promulgated_not_yet_effective): "
                + ", ".join(f"MST {c['mst']}(시행 {c['effective_date']})" for c in pending)
                + ". 기준일에 적용되는 것은 위 version입니다."
            )
        if not slim:
            out["neighbors"] = {"previous": describe(sel["previous"]), "next": describe(nxt)}
        is_current = bool(cur_c and cur_c["mst"] == mst and cur_c["effective_date"] == eff)
        comparison = {
            "is_current_version": is_current,
            "current_version": describe(cur_c),
            "current_state": cur["outcome"],
        }

        art = None
        if wanted:
            label = article_label(*wanted)
            try:
                art, failure = fetch(chosen)
            except ArticleNotFoundError as e:
                if not end:
                    return create_error_response(
                        error_code=ErrorCode.ARTICLE_NOT_FOUND,
                        message=(f"{law_label} {label}: 기준일 {d}에 시행 중인 버전(MST {mst}, 시행일 {eff})에 "
                                 f"해당 조문이 없습니다. Article not found in the version in force on {d}."),
                        hints=["조문이 신설되기 전이거나 삭제된 시점일 수 있습니다. 다른 기준일로 다시 조회하거나 "
                               "law_amendment_summary로 개정 이력을 확인하세요.",
                               *(e.hints or [])],
                        as_of=d, version=version, law_name=law_label, article=label,
                    )
                art, failure = None, None
                out["article_status"] = ErrorCode.ARTICLE_NOT_FOUND
            if failure is not None:
                code = failure.get("error_code") or ErrorCode.UPSTREAM_ERROR
                return create_error_response(
                    error_code=code,
                    message=(f"{law_label} {label}: 기준일 {d}의 버전(MST {mst}, 시행일 {eff})은 확인했으나 "
                             f"본문 조회에 실패했습니다 ({code}). 조문이 없다는 뜻이 아닙니다. "
                             "Version resolved but its body could not be fetched."),
                    hints=["잠시 후 다시 시도하세요", "OC 승인 및 API 신청 여부(open.law.go.kr)를 확인하세요"],
                    success=False, as_of=d, version=version, law_name=law_label, article=label,
                )
            if art is not None:
                out["article"] = {
                    "label": art["article"], "title": art["title"], "text": art["text"],
                    "upstream_article_effective_date": art["effective"],
                    "upstream_changed_flag": art["changed"],
                }
            if is_current:
                comparison["differs_from_current"] = False
            elif cur_c is None:
                comparison["differs_from_current"] = True
                comparison["note"] = "현재 시행 중인 버전이 없습니다(폐지)."
            else:
                try:
                    cur_art, cur_fail = fetch(cur_c)
                except ArticleNotFoundError:
                    comparison["differs_from_current"] = art is not None
                    comparison["note"] = f"현재 버전(MST {cur_c['mst']})에는 이 조문이 없습니다."
                else:
                    if cur_fail is not None:
                        comparison["differs_from_current"] = None
                        comparison["note"] = (f"현재 버전 본문 조회 실패({cur_fail.get('error_code')}): "
                                              "비교하지 못했습니다.")
                    elif art is None:
                        comparison["differs_from_current"] = True
                    else:
                        same = re.sub(r"\s+", "", cur_art["text"]) == re.sub(r"\s+", "", art["text"])
                        comparison["differs_from_current"] = not same
                        if not slim and not same:
                            comparison["current_article_text"] = cur_art["text"]
            what = f"{law_label} {art['article'] if art else label}"
        else:
            comparison["differs_from_current"] = None
            comparison["note"] = "조문을 지정하지 않아 법령 헤더만 반환했습니다(조문 비교 없음)."
            what = law_label
        out["comparison"] = comparison
        if end:
            out["period"] = period_block(chosen)
        out["statement"] = (
            f"기준일 {d} 현재 시행 중인 {what}은(는) MST {mst} "
            f"(시행일 {eff}, 공포일 {version['announced_date']}, 공포번호 {version['announcement_no']}, "
            f"{version['revision_type']}) 기준입니다."
            + (f" 이 버전은 {out['valid_until']}까지 유효합니다." if out["valid_until"] else " 이후 시행 예정 개정은 없습니다.")
            + (" 이후 개정이 있습니다." if later_all else "")
            + (" 시행예정 버전이 있습니다." if scheduled else "")
        )
        out["caveats"] = caveats
        return out

    # ==================== PROMPTS ====================

    @server.prompt(
        name="search-korean-law",
        description="Search for a Korean law by name or keyword and provide a summary"
    )
    def search_korean_law(law_name: str) -> list:
        """
        Prompt to help users search for a Korean law by name.

        Args:
            law_name: Name or keyword of the law (e.g., '민법', '자동차관리법', 'civil code')

        Returns:
            List of messages to guide the AI assistant
        """
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Please search for the Korean law named '{law_name}' using the eflaw_search tool.

Once you find the law, provide:
1. The official Korean name (법령명한글) and English name if available
2. The law ID and announcement date
3. A brief summary of what this law covers
4. The current status (effective or historical)

If the law is found, offer to retrieve specific articles if needed."""
                }
            }
        ]

    @server.prompt(
        name="get-law-article",
        description="Retrieve and explain a specific article from a Korean law"
    )
    def get_law_article(law_id: str, article_number: int) -> list:
        """
        Prompt to help users retrieve a specific article from a law.

        Args:
            law_id: Law ID (e.g., '000001' for 민법)
            article_number: Article number (e.g., 20 for 제20조)

        Returns:
            List of messages to guide the AI assistant
        """
        # Format article number to 6-digit format (XXXXXX)
        formatted_jo = f"{article_number:04d}00"

        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Please retrieve Article {article_number} (제{article_number}조) from law ID '{law_id}' using the eflaw_service tool with jo parameter '{formatted_jo}'.

After retrieving the article:
1. Display the full text of the article in Korean
2. Provide a clear explanation in English of what the article means
3. Highlight any important conditions, requirements, or exceptions
4. If relevant, explain how this article relates to other parts of the law

Note: The jo parameter format is XXXXXX where first 4 digits are the article number (zero-padded) and last 2 digits are for branch articles (00 for main article)."""
                }
            }
        ]

    @server.prompt(
        name="get-article-with-citations",
        description="Retrieve a law article AND all its citations (referenced laws)"
    )
    def get_article_with_citations(law_name: str, article_number: int) -> list:
        """
        Prompt to retrieve article content AND extract all citations.

        This prompt chains:
        1. eflaw_search to find the law
        2. eflaw_service to get article content
        3. article_citation to get all referenced laws

        Args:
            law_name: Law name (e.g., '건축법', '자본시장법')
            article_number: Article number (e.g., 3 for 제3조)

        Returns:
            List of messages guiding the AI to use all three tools
        """
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Please analyze '{law_name}' Article {article_number} (제{article_number}조) with full citation information.

**REQUIRED STEPS** (must complete all 3):

1. **Search for the law** using eflaw_search:
   - Query: "{law_name}"
   - Extract: 법령일련번호 (MST) and 법령명한글 (full law name)

2. **Get article content** using eflaw_service:
   - Use the MST from step 1
   - jo parameter: "{article_number:04d}00" (e.g., "000300" for 제3조)
   - Display the full article text

3. **Extract all citations** using article_citation:
   - mst: (from step 1)
   - law_name: (from step 1)
   - article: {article_number}
   - List ALL external and internal citations

**OUTPUT FORMAT**:
- Article text in Korean
- Citation summary: total count, external vs internal
- List of all cited laws with specific article/paragraph references
- Brief explanation of why each citation is relevant"""
                }
            }
        ]

    @server.prompt(
        name="analyze-law-citations",
        description="Search a law and automatically analyze citations for specified articles"
    )
    def analyze_law_citations(law_name: str, articles: str = "1,2,3") -> list:
        """
        Prompt to search a law and analyze citations for multiple articles.

        Args:
            law_name: Law name to search
            articles: Comma-separated article numbers (e.g., "1,2,3" or "11")

        Returns:
            List of messages guiding comprehensive citation analysis
        """
        article_list = [a.strip() for a in articles.split(",")]
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Please analyze the citation network for '{law_name}'.

**WORKFLOW**:

1. **First**, search for '{law_name}' using eflaw_search to get:
   - 법령일련번호 (MST)
   - 법령명한글 (official name)

2. **Then**, for EACH of these articles: {', '.join(f'제{a}조' for a in article_list)}
   Call article_citation with:
   - mst: (from search result)
   - law_name: (official name from search)
   - article: (each article number)

3. **Compile a citation report**:
   - Total citations per article
   - Most frequently cited external laws
   - Internal cross-references within the law
   - Summary table of all citations

**IMPORTANT**: You MUST call article_citation for each article listed above.
Do not skip the citation extraction step."""
                }
            }
        ]

    @server.prompt(
        name="search-admin-rules",
        description="Search Korean administrative rules (행정규칙) by keyword"
    )
    def search_admin_rules(keyword: str) -> list:
        """
        Prompt to help users search for administrative rules.

        Args:
            keyword: Search keyword for administrative rules (e.g., '학교', '환경')

        Returns:
            List of messages to guide the AI assistant
        """
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Please search for Korean administrative rules (행정규칙) related to '{keyword}' using the admrul_search tool.

Administrative rules include:
- 훈령 (directives)
- 예규 (regulations)
- 고시 (public notices)
- 공고 (announcements)
- 지침 (guidelines)

After searching:
1. List the top relevant administrative rules found
2. For each rule, provide the rule name and issuing ministry
3. Note the announcement date and current status
4. Offer to retrieve the full text of any specific rule if needed

Use display=10 to get a good sample of results."""
                }
            }
        ]

    @server.prompt(
        name="tool-selection-guide",
        description="Guidance on which search tool to use based on query clarity"
    )
    def tool_selection_guide() -> list:
        """
        Prompt to guide LLMs on tool selection strategy.

        Returns:
            List of messages explaining when to use which tools
        """
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": """When searching Korean law, select tools based on query clarity:

🔍 VAGUE/UNCLEAR queries → Use aiSearch or aiRltLs_search FIRST
   These AI-powered tools use semantic search for natural language understanding.
   Examples: "음주운전 처벌", "이혼 재산분할", "뺑소니", "상속 문제"

📋 SPECIFIC queries → Use eflaw_search, law_search, prec_search
   Use these when the user mentions specific law names, article numbers, or case numbers.
   Examples: "형법 제148조의2", "민법 상속편", "대법원 2023다12345"

🔗 RELATED LAWS → Use aiRltLs_search
   When user wants to discover laws related to a topic or another law.
   Examples: "민법과 관련된 법률", "의료법 연관 법령"

Tool selection priority for unclear queries:
1. aiSearch (semantic article search) - for finding specific provisions
2. aiRltLs_search (related laws) - for exploring law landscape
3. eflaw_search/law_search (keyword) - fallback for precise matches

📚 LEGAL TERMS & DEFINITIONS → Use knowledge base tools
   lstrm_ai_search, dlytrm_search, lstrm_rlt_search, dlytrm_rlt_search
   Examples: "뺑소니 정의", "법률 용어 정리"

🏛️ COMMITTEE/TRIBUNAL DECISIONS → Use committee or special appeal tools
   committee_search, special_decc_search
   Examples: "공정거래위원회 담합 결정", "조세심판원 재결례"

🏢 MINISTRY INTERPRETATIONS → Use cgm_expc_search
   Examples: "고용노동부 근로시간 해석", "국토교통부 건축법 해석"

🌍 TREATIES → Use trty_search
   Examples: "한미 FTA", "기후변화 조약"

📋 LOCAL ORDINANCES → Use ordin_search
   Examples: "서울시 주차 조례", "청소년 보호 조례\""""
                }
            }
        ]

    # ==================== PUBLIC LEGAL ASSISTANCE PROMPTS ====================

    @server.prompt(
        name="analyze-legal-situation",
        description="Describe a legal situation in plain Korean → get applicable laws, rights, and action steps"
    )
    def analyze_legal_situation(situation: str) -> list:
        """
        Prompt for analyzing a legal situation described in plain language.

        Args:
            situation: Plain language description (e.g., "집주인이 보증금을 안 돌려줘요")
        """
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""다음 법률 상황을 분석해주세요: "{situation}"

**필수 단계** (모두 완료해야 합니다):

1. **관련 법령 찾기**: legal_resolver 도구를 사용하여 종합 분석을 수행하세요.
   - legal_resolver(situation="{situation}")

2. **판례 확인**: check_precedent_odds 도구로 유사 판례의 결과 분포(승률 아님; outcome_note 참고)를 확인하세요.
   - check_precedent_odds(query="{situation}")

3. **결과 정리**: 다음 형식으로 응답하세요:

**📋 적용 법률**
- 관련 법령과 조문 번호를 나열하세요

**⚖️ 당신의 권리**
- 해당 법률에 따른 권리를 설명하세요

**📌 조치 방법**
- 구체적인 행동 단계를 안내하세요 (내용증명, 소액재판, 신고 등)

**📊 유사 판례**
- 비슷한 사례와 결과를 요약하세요

**🏢 관련 기관**
- 도움을 받을 수 있는 기관 안내

⚠️ 이 분석은 참고용이며 법률 자문이 아닙니다. 정확한 판단을 위해 변호사와 상담하세요."""
                }
            }
        ]

    @server.prompt(
        name="explain-legal-document",
        description="Paste a legal document → get plain Korean explanation"
    )
    def explain_legal_document(document_text: str) -> list:
        """
        Prompt for explaining legal document text in plain Korean.

        Args:
            document_text: Legal text to explain (contract clause, court notice, etc.)
        """
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""다음 법률 문서를 쉬운 한국어로 설명해주세요:

---
{document_text}
---

**필수 단계**:

1. 문서에서 법률 용어를 찾아 dlytrm_rlt_search 또는 lstrm_rlt_search로 쉬운 말을 검색하세요.
2. 언급된 법령이 있으면 eflaw_search 또는 aiSearch로 관련 조문을 확인하세요.

**응답 형식**:

**📖 쉬운 설명**
- 이 문서가 무엇을 말하는지 일상적인 한국어로 설명

**📝 핵심 용어**
| 법률 용어 | 쉬운 말 |
|-----------|---------|
| (용어) | (설명) |

**💡 당신에게 미치는 영향**
- 이 문서가 당신에게 의미하는 바

**⚠️ 주의사항**
- 특이하거나 주의해야 할 조항

**📋 관련 법령**
- 이 문서에서 참조하는 법률 조항

⚠️ 이 설명은 참고용이며 법률 자문이 아닙니다."""
                }
            }
        ]

    @server.prompt(
        name="check-legal-precedent",
        description="Ask a yes/no legal question → get precedent-backed answer (outcome distribution, not a win rate)"
    )
    def check_legal_precedent(question: str) -> list:
        """
        Prompt for checking legal precedents for a yes/no question.

        Args:
            question: Legal question (e.g., "임대인이 계약 갱신을 거절할 수 있나요?")
        """
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""법률 질문: "{question}"

**필수 단계** (모두 완료해야 합니다):

1. **관련 법령 확인**: aiSearch로 관련 법률 조문을 찾으세요.
   - aiSearch(query="{question}")

2. **판례 분석**: check_precedent_odds로 판례 통계와 핵심 요소를 확인하세요.
   - check_precedent_odds(query="{question}")

3. **결과 정리**: 다음 형식으로 응답하세요:

**✅ 답변**
- 예 / 아니오 / 경우에 따라 다름 — 법적 근거와 함께

**📊 판례 통계**
- 분석한 N건의 주문 분포(예: 파기환송 a건, 상고기각 b건, 불명 c건). 승소율/성공률로 환산하지 말고 outcome_note의 해석 주의를 그대로 전달
- 핵심 판단 요소 나열

**📋 대표 판례**
- 가장 관련성 높은 2-3개 판례 요약

**🔍 핵심 판단 요소**
- 법원이 중요하게 본 요소들
- 당신의 경우에 어떤 요소가 해당하는지

**💡 참고사항**
- 상황에 따라 달라질 수 있는 부분

⚠️ 이 분석은 참고용이며 법률 자문이 아닙니다. 정확한 판단을 위해 변호사와 상담하세요."""
                }
            }
        ]

    logger.info("LexLink server initialized with 55 tools, 9 prompts, and 2 resources")
    logger.info("Phase 1 & 2 Tools (15):")
    logger.info("  - eflaw_search, law_search, eflaw_service, law_service, eflaw_josub, law_josub")
    logger.info("  - elaw_search, elaw_service, admrul_search, admrul_service")
    logger.info("  - lnkLs_search, lnkLsOrdJo_search, lnkDep_search, drlaw_search, lsDelegated_service")
    logger.info("Phase 3 Tools (8):")
    logger.info("  - prec_search, prec_service, detc_search, detc_service")
    logger.info("  - expc_search, expc_service, decc_search, decc_service")
    logger.info("Phase 4 Tools (1):")
    logger.info("  - article_citation")
    logger.info("Phase 5 Tools (2):")
    logger.info("  - aiSearch, aiRltLs_search (Knowledge Base AI-powered search)")
    logger.info("Phase 7 Tools (18):")
    logger.info("  - ordin_search, ordin_service, ordinLsCon_search")
    logger.info("  - trty_search, trty_service")
    logger.info("  - lstrm_ai_search, dlytrm_search, lstrm_rlt_search, dlytrm_rlt_search")
    logger.info("  - lstrm_rlt_jo_search, jo_rlt_lstrm_search, ls_rlt_search")
    logger.info("  - committee_search, committee_service")
    logger.info("  - cgm_expc_search, cgm_expc_service")
    logger.info("  - special_decc_search, special_decc_service")
    logger.info("Phase 8 Tools (5):")
    logger.info("  - check_precedent_odds, legal_resolver, simplify_article")
    logger.info("  - law_amendment_summary, article_amendment_diff")
    logger.info("Phase 9 Chain Tools (5):")
    logger.info("  - chain_full_research, chain_amendment_track, chain_dispute_prep")
    logger.info("  - chain_law_system, cache_stats")
    logger.info("Phase 10 Tool (1):")
    logger.info("  - law_as_of (version in force on a given date)")
    logger.info("Prompts (9): search-korean-law, get-law-article, get-article-with-citations, analyze-law-citations, search-admin-rules, tool-selection-guide, analyze-legal-situation, explain-legal-document, check-legal-precedent")
    logger.info("Resources (2): frequently-used-laws (static), law-code-lookup (template)")
    return server
