"""
LexLink MCP Server - Korean National Law Information API.

This server exposes the law.go.kr Open API through MCP tools,
enabling AI agents to search and retrieve Korean legal information.

⚠️ IMPORTANT: The law.go.kr API does NOT support JSON format despite
documentation. All tools default to XML format. Use XML or HTML only.
"""

import logging
import os
import re
from typing import Optional, Union

from mcp.server.fastmcp import FastMCP, Context

from .client import LawAPIClient
from .errors import ErrorCode, create_error_response
from .params import map_params_to_upstream, resolve_oc
from .validation import validate_date_range
from .parser import parse_xml_response, extract_law_list, update_law_list
from .ranking import detect_query_language
from ._helpers import (
    TOOL_ANNOTATIONS, stringify_id, handle_tool_error,
    slim_response, run_search, run_service,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)



def create_server() -> FastMCP:
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
   - This provides 100% accurate citation data

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

**Knowledge Base (AI-powered search):**
- aiSearch: Semantic search for law articles - returns FULL article text
- aiRltLs_search: Find semantically related laws

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

    server = FastMCP("LexLink - Korean Law API", instructions=SERVER_INSTRUCTIONS)

    def _get_client() -> LawAPIClient:
        """Create HTTP client from environment variables or defaults."""
        return LawAPIClient(
            base_url=os.getenv("LEXLINK_BASE_URL", "http://www.law.go.kr"),
            timeout=int(os.getenv("LEXLINK_TIMEOUT", "60")),
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
        description="Look up a specific Korean law's stable 법령ID by name (Korean). Returns the law's ID, full name, abbreviation, and type. If not found, use eflaw_search or law_search tool instead.",
        mime_type="application/json",
    )
    def get_law_by_name(name: str) -> str:
        """Look up a law by name or abbreviation."""
        import json
        if entry := _law_cache.get(name):
            return json.dumps(entry, ensure_ascii=False, indent=2)
        return json.dumps(
            {"error": "not_found", "message": f"'{name}' not in cache. Use eflaw_search or law_search tool to find it."},
            ensure_ascii=False,
        )

    # ==================== TOOL 1: eflaw_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def eflaw_search(
        query: str,
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        sort: Optional[str] = None,
        ef_yd: Optional[str] = None,
        org: Optional[str] = None,
        knd: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        Search current laws by effective date (시행일 기준 현행법령 검색).

        This tool searches Korean laws organized by effective date.
        Use this when you need to find laws that are currently in effect.

        Args:
            query: Search keyword (law name or content)
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"|"efasc"|"efdes"
            ef_yd: Effective date range (YYYYMMDD~YYYYMMDD, e.g., "20240101~20241231")
            org: Ministry/department code filter
            knd: Law type filter

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
        snake_params = {
            "oc": resolved_oc, "target": "eflaw", "type": type,
            "query": query, "display": display, "page": page,
        }
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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        ef_yd: Optional[int] = None,
        jo: Optional[Union[str, int]] = None,
        chr_cls_cd: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve full law content by effective date (시행일 기준 법령 본문 조회).

        Retrieves the complete text of a law organized by effective date.

        **IMPORTANT: For specific article queries (e.g., "제174조"), ALWAYS use the `jo` parameter.
        Some laws (e.g., 자본시장법) have 400+ articles and the full response can exceed 1MB.
        Using `jo` returns only the requested article, which is much faster and cleaner.**

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST/lsi_seq)
            ef_yd: Effective date (YYYYMMDD) - required when using mst
            jo: **REQUIRED for specific articles.** Article number in XXXXXX format.
                Format: first 4 digits = article number (zero-padded), last 2 digits = branch suffix (00=main).
                Examples: "017400" (제174조), "017200" (제172조), "000300" (제3조), "001502" (제15조의2)
            chr_cls_cd: Language code - "010202" (Korean, default) or "010201" (Original)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

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
        if not id and not mst:
            raise ValueError("Either 'id' or 'mst' parameter is required")
        snake_params = {"oc": resolved_oc, "target": "eflaw", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if ef_yd: snake_params["ef_yd"] = ef_yd
        if jo: snake_params["jo"] = jo
        if chr_cls_cd: snake_params["chr_cls_cd"] = chr_cls_cd
        return run_service(get_client=_get_client, target="eflaw",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 4: law_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def law_service(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        lm: Optional[str] = None,
        ld: Optional[int] = None,
        ln: Optional[int] = None,
        jo: Optional[Union[str, int]] = None,
        lang: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve full law content by announcement date (공포일 기준 법령 본문 조회).

        Retrieves the complete text of a law organized by announcement (publication) date.

        **IMPORTANT: For specific article queries (e.g., "제174조"), ALWAYS use the `jo` parameter.
        Some laws (e.g., 자본시장법) have 400+ articles and the full response can exceed 1MB.
        Using `jo` returns only the requested article, which is much faster and cleaner.**

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            lm: Law modification parameter
            ld: Law date parameter (YYYYMMDD)
            ln: Law number parameter
            jo: **REQUIRED for specific articles.** Article number in XXXXXX format.
                Format: first 4 digits = article number (zero-padded), last 2 digits = branch suffix (00=main).
                Examples: "017400" (제174조), "017200" (제172조), "000300" (제3조), "001502" (제15조의2)
            lang: Language - "KO" (Korean) or "ORI" (Original)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

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
        if not id and not mst:
            raise ValueError("Either 'id' or 'mst' parameter is required")
        snake_params = {"oc": resolved_oc, "target": "law", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if lm: snake_params["lm"] = lm
        if ld: snake_params["ld"] = ld
        if ln: snake_params["ln"] = ln
        if jo: snake_params["jo"] = jo
        if lang: snake_params["lang"] = lang
        return run_service(get_client=_get_client, target="law",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 5: eflaw_josub ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def eflaw_josub(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        ef_yd: Optional[int] = None,
        jo: Optional[Union[str, int]] = None,
        hang: Optional[str] = None,
        ho: Optional[str] = None,
        mok: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Query specific article/paragraph by effective date (시행일 기준 조·항·호·목 조회).

        **BEST TOOL for querying specific articles like "제174조", "제3조" etc.**
        This returns only the requested article/paragraph, avoiding large full-law responses.

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            ef_yd: Effective date (YYYYMMDD) - required when using mst
            jo: Article number in XXXXXX format.
                Format: first 4 digits = article number (zero-padded), last 2 digits = branch suffix (00=main).
                Examples: "017400" (제174조), "017200" (제172조), "000300" (제3조), "001502" (제15조의2)
            hang: Paragraph number (6 digits, e.g., "000100" for 제1항)
            ho: Item number (6 digits, e.g., "000200" for 제2호)
            mok: Subitem (UTF-8 encoded, e.g., "다" for 다목)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

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
        snake_params = {"oc": resolved_oc, "target": "eflawjosub", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if ef_yd: snake_params["ef_yd"] = ef_yd
        if jo: snake_params["jo"] = jo
        if hang: snake_params["hang"] = hang
        if ho: snake_params["ho"] = ho
        if mok: snake_params["mok"] = mok
        return run_service(get_client=_get_client, target="eflawjosub",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 6: law_josub ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def law_josub(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        jo: Optional[Union[str, int]] = None,
        hang: Optional[str] = None,
        ho: Optional[str] = None,
        mok: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Query specific article/paragraph by announcement date (공포일 기준 조·항·호·목 조회).

        **BEST TOOL for querying specific articles like "제174조", "제3조" etc.**
        This returns only the requested article/paragraph, avoiding large full-law responses.

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            jo: Article number in XXXXXX format.
                Format: first 4 digits = article number (zero-padded), last 2 digits = branch suffix (00=main).
                Examples: "017400" (제174조), "017200" (제172조), "000300" (제3조), "001502" (제15조의2)
            hang: Paragraph number (6 digits, e.g., "000100" for 제1항)
            ho: Item number (6 digits, e.g., "000200" for 제2호)
            mok: Subitem (UTF-8 encoded, e.g., "다" for 다목)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

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
        snake_params = {"oc": resolved_oc, "target": "lawjosub", "type": type}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        if jo: snake_params["jo"] = jo
        if hang: snake_params["hang"] = hang
        if ho: snake_params["ho"] = ho
        if mok: snake_params["mok"] = mok
        return run_service(get_client=_get_client, target="lawjosub",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 7: elaw_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def elaw_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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

        # Map to upstream format
        upstream_params = map_params_to_upstream(params)

        # Determine if we need to fetch more results for ranking
        original_display = display
        ranking_enabled = (type == "XML" and should_apply_ranking(query))

        if ranking_enabled and original_display < 100:
            # Fetch more results to rank (up to 100, API max) for better relevance
            upstream_params["numOfRows"] = "100"
            logger.debug(f"Ranking enabled: fetching 100 results instead of {original_display}")

        # Call API
        client = _get_client()
        response = client.get("/DRF/lawSearch.do", upstream_params, response_type=type)

        # Apply relevance ranking for English-translated laws
        # elaw target accepts both Korean and English queries, so detect language
        if response.get("status") == "ok" and ranking_enabled:
            raw_content = response.get("raw_content", "")
            if raw_content:
                parsed_data = parse_xml_response(raw_content)
                if parsed_data:
                    laws = extract_law_list(parsed_data)
                    if laws:
                        # Detect query language and rank by matching field
                        # Korean query "가정폭력방지" → rank by 법령명한글
                        # English query "insurance" → rank by 법령명영문
                        query_lang = detect_query_language(query)
                        name_field = "법령명영문" if query_lang == "english" else "법령명한글"

                        # Verify the field exists in results, fall back if needed
                        if laws and name_field not in laws[0]:
                            name_field = "법령명한글" if name_field == "법령명영문" else "법령명영문"

                        ranked_laws = rank_search_results(laws, query, name_field)

                        # Trim to original requested display amount
                        if len(ranked_laws) > original_display:
                            ranked_laws = ranked_laws[:original_display]
                            logger.debug(f"Trimmed results from {len(laws)} to {original_display}")

                        parsed_data = update_law_list(parsed_data, ranked_laws)
                        # Update numOfRows to reflect trimmed results
                        parsed_data["numOfRows"] = str(original_display)
                        response["ranked_data"] = parsed_data

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
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve English law full text (영문법령 본문 조회).

        This tool retrieves the complete text of Korean laws translated to English.
        Useful for international legal research and cross-border understanding.

        Args:
            id: Law ID (required if mst not provided)
            mst: Law master number (required if id not provided)
            lm: Law name (alternative search method)
            ld: Announcement date (YYYYMMDD)
            ln: Announcement number
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        if not id and not mst:
            raise ValueError("Either 'id' or 'mst' parameter is required")
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {"oc": resolved_oc, "target": "elaw"}
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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve administrative rule full text (행정규칙 본문 조회).

        This tool retrieves the complete text of Korean administrative rules.
        Includes rule content, addenda, and annexes (forms/attachments).

        Args:
            id: Rule sequence number (required if lid/lm not provided)
            lid: Rule ID (alternative to id)
            lm: Rule name (exact match search)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        snake_params = {"oc": resolved_oc, "target": "admrul"}
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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        }
        if knd: snake_params["knd"] = knd
        if jo is not None:
            # Convert to 4-digit format if needed
            snake_params["jo"] = jo if jo >= 1000 else jo
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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        return client.get("/DRF/lawSearch.do", upstream_params, response_type="HTML")

    # ==================== TOOL 15: lsDelegated_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lsDelegated_service(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve delegated laws/rules/ordinances (위임 법령 조회).

        This tool retrieves information about laws, administrative rules, and
        local ordinances that are delegated by a parent law. Shows the delegation
        hierarchy and which specific articles delegate authority.

        ⚠️ Note: This API does NOT support HTML format (only XML/JSON).

        Args:
            id: Law ID (required if mst not provided)
            mst: Law master number (required if id not provided)
            oc: Optional OC override (defaults to env var)
            type: Response format - "XML" only (JSON not supported by API, HTML not available)
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
        snake_params = {"oc": resolved_oc, "target": "lsDelegated"}
        if id: snake_params["id"] = id
        if mst: snake_params["mst"] = mst
        return run_service(get_client=_get_client, target="lsDelegated",
                          snake_params=snake_params, response_type=type)

    # ==================== PHASE 3: CASE LAW & LEGAL RESEARCH ====================

    # ==================== TOOL 16: prec_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def prec_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
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
            Search results with precedent list or error

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
        return run_search(
            get_client=_get_client, target="prec", query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="판례명", list_type="items", item_category="prec",
            over_fetch_key="display",
        )

    # ==================== TOOL 17: prec_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def prec_service(
        id: Union[str, int],
        lm: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve court precedent full text (판례 본문 조회).

        Args:
            id: Precedent sequence number (판례일련번호)
            lm: Precedent name (optional)
            oc: Optional OC override
            type: Response format - "HTML" or "XML" (default "XML")

        Returns:
            Full precedent text with details or error

        Examples:
            >>> prec_service(id="228541")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "prec",
            "id": str(id), "type": type,
        }
        if lm: snake_params["lm"] = lm
        return run_service(get_client=_get_client, target="prec",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 18: detc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def detc_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
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
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve Constitutional Court decision full text (헌재결정례 본문 조회).

        Args:
            id: Constitutional Court decision sequence number (헌재결정례일련번호)
            lm: Decision name (optional)
            oc: Optional OC override
            type: Response format - "HTML" or "XML" (default "XML")

        Returns:
            Full Constitutional Court decision text or error

        Examples:
            >>> detc_service(id="58386")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "detc",
            "id": str(id), "type": type,
        }
        if lm: snake_params["lm"] = lm
        return run_service(get_client=_get_client, target="detc",
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 20: expc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def expc_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve legal interpretation full text (법령해석례 본문 조회).

        This tool retrieves the complete text of a legal interpretation precedent,
        including the question summary, answer, and reasoning.

        Args:
            id: Legal interpretation sequence number (required)
            lm: Legal interpretation name (optional)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
                          snake_params=snake_params, response_type=type)

    # ==================== TOOL 18: decc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def decc_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve administrative appeal decision full text (행정심판례 본문 조회).

        This tool retrieves the complete text of Korean administrative appeal decisions.
        Includes case details, disposition information, decision summary, and reasoning.

        Args:
            id: Decision sequence number (required)
            lm: Decision name (optional)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
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
                          snake_params=snake_params, response_type=type)

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
        providing 100% accurate citation data with zero API cost.

        The tool identifies:
        - External citations (references to other laws)
        - Internal citations (references within the same law)
        - Article, paragraph, and item level references

        Args:
            mst: Law MST code (법령일련번호) - get this from eflaw_search or law_search results
            law_name: Law name in Korean (e.g., "자본시장과 금융투자업에 관한 법률")
            article: Article number (조번호, e.g., 3 for 제3조)
            article_branch: Article branch number (조가지번호, e.g., 2 for 제37조의2, default 0)
            oc: Optional OC override (defaults to env var)

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

        # OC is not strictly required for citation extraction (uses HTML scraping)
        # but we validate it for consistency with other tools
        try:
            resolved_oc = resolve_oc(override_oc=oc)
            logger.debug(f"article_citation called with OC: {resolved_oc[:4]}...")
        except ValueError:
            # OC not required for citation extraction
            logger.debug("article_citation called without OC (not required)")

        # Validate required parameters
        if not mst:
            raise ValueError("mst (법령일련번호) is required")
        if not law_name:
            raise ValueError("law_name (법령명) is required")
        if article <= 0:
            raise ValueError("article must be a positive integer")

        # Extract citations
        result = await extract_article_citations(
            mst=str(mst),
            law_name=law_name,
            article=article,
            article_branch=article_branch
        )

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
        type: str = "XML",
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
            type: Response format - XML only (JSON not supported)

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
        return run_search(
            get_client=_get_client, target="aiSearch", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 26: aiRltLs_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def aiRltLs_search(
        query: str,
        search: int = 0,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - XML only (JSON not supported)

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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
            nw: 1=현행 (current), 2=연혁 (historical), default 1
            search: 1=자치법규명 (ordinance name), 2=본문검색 (full text), default 1
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"
            date: Announcement date (YYYYMMDD)
            ef_yd: Effective date range (YYYYMMDD~YYYYMMDD)
            anc_yd: Announcement date range (YYYYMMDD~YYYYMMDD)
            anc_no: Announcement number
            org: Local government code filter (e.g., "6110000" for Seoul)
            sborg: Sub-organization code filter
            knd: Ordinance type - 1=조례, 2=규칙, 3=교육규칙
            rr_cls_cd: Administrative district classification code
            ordin_fd: Ordinance field code
            gana: Dictionary search (ga, na, da, ...)
            ctx: MCP context (injected automatically)

        Returns:
            Search results with local ordinance list or error

        Examples:
            Search for "서울시 건축 조례":
            >>> ordin_search(query="건축", org="6110000", knd="1")

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
            ranking_field="자치법규명", list_type="ordin",
            over_fetch_key="numOfRows",
        )

    # ==================== TOOL 28: ordin_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def ordin_service(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve local ordinance full text (자치법규 본문 조회).

        This tool retrieves the complete text of a Korean local ordinance.

        Args:
            id: Ordinance ID (either id or mst is required)
            mst: Ordinance master number (either id or mst is required)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML")
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
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Search ordinance-to-law linkage (자치법규 기준 법령 연계 관련 목록 조회).

        This tool searches national law articles that are referenced or linked
        by local ordinances. Useful for finding the legal basis (상위 법령) that
        a specific ordinance is based on.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML")
            ctx: MCP context (injected automatically)

        Returns:
            Search results with ordinance-law linkage list or error

        Examples:
            Search for linked laws:
            >>> ordinLsCon_search(query="건축", type="XML")
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "ordinLsCon", "type": type,
            "query": query, "display": display, "page": page,
        }
        return run_search(
            get_client=_get_client, target="ordinLsCon", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 30: trty_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def trty_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
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
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve treaty full text (조약 본문 조회).

        This tool retrieves the complete text of a Korean international treaty.

        Args:
            id: Treaty sequence number (조약일련번호, required)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML")
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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
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
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Legal term to everyday term linkage (법령용어→일상용어 연계 조회).

        This tool searches the linkage between formal legal terms and their
        plain-language (everyday) equivalents. Useful for finding how legal
        terminology maps to everyday Korean.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML")
            ctx: MCP context (injected automatically)

        Returns:
            Search results or error
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "lstrmRlt", "type": type,
            "query": query, "display": display, "page": page,
        }
        return run_search(
            get_client=_get_client, target="lstrmRlt", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 35: dlytrm_rlt_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def dlytrm_rlt_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Everyday term to legal term linkage (일상용어→법령용어 연계 조회).

        This tool searches the linkage from plain-language (everyday) terms
        back to their formal legal equivalents. Useful for finding the correct
        legal terminology when starting from common language.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML")
            ctx: MCP context (injected automatically)

        Returns:
            Search results or error
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "dlytrmRlt", "type": type,
            "query": query, "display": display, "page": page,
        }
        return run_search(
            get_client=_get_client, target="dlytrmRlt", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 36: lstrm_rlt_jo_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def lstrm_rlt_jo_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Legal term to article linkage (법령용어→조문 연계 조회).

        This tool searches the linkage between legal terms and the specific
        law articles where those terms are used or defined.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML")
            ctx: MCP context (injected automatically)

        Returns:
            Search results or error
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "lstrmRltJo", "type": type,
            "query": query, "display": display, "page": page,
        }
        return run_search(
            get_client=_get_client, target="lstrmRltJo", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 37: jo_rlt_lstrm_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def jo_rlt_lstrm_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Article to legal term linkage (조문→법령용어 연계 조회).

        This tool searches the linkage from specific law articles to the
        legal terms defined or used within those articles. Useful for finding
        all technical terms in a given article.

        Args:
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML")
            ctx: MCP context (injected automatically)

        Returns:
            Search results or error
        """
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": "joRltLstrm", "type": type,
            "query": query, "display": display, "page": page,
        }
        return run_search(
            get_client=_get_client, target="joRltLstrm", query=query,
            snake_params=snake_params, response_type=type, display=display,
        )

    # ==================== TOOL 38: ls_rlt_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def ls_rlt_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
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
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
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
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve committee decision full text (위원회 결정문 본문 조회).

        Args:
            committee: Committee name (same values as committee_search)
            id: Decision serial number (결정문일련번호)
            oc: Optional OC override
            type: Response format - "HTML" or "XML" (default "XML")
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
        return run_service(get_client=_get_client, target=target,
                          snake_params=snake_params, response_type=type)

    # ==================== TASK 13: 중앙부처 1차 해석 ====================

    # Ministry target code mapping (for cgmExpc{Code} pattern)
    MINISTRY_CODES = {
        "고용노동부": "Moel", "국토교통부": "Molit", "기획재정부": "Moef",
        "해양수산부": "Mof", "행정안전부": "Mois", "기후에너지환경부": "Me",
        "관세청": "Kcs", "국세청": "Nts", "교육부": "Moe",
        "과학기술정보통신부": "Msit", "국가보훈부": "Mpva", "국방부": "Mnd",
        "농림축산식품부": "Mafra", "문화체육관광부": "Mcst", "법무부": "Moj",
        "보건복지부": "Mohw", "산업통상부": "Motie", "성평등가족부": "Mogef",
        "외교부": "Mofa", "중소벤처기업부": "Mss", "통일부": "Mou",
        "법제처": "Moleg", "식품의약품안전처": "Mfds", "인사혁신처": "Mpm",
        "기상청": "Kma", "국가유산청": "Khs", "농촌진흥청": "Rda",
        "경찰청": "Npa", "방위사업청": "Dapa", "병무청": "Mma",
        "산림청": "Kfs", "소방청": "Nfa", "재외동포청": "Oka",
        "조달청": "Pps", "질병관리청": "Kdca", "국가데이터처": "Kostat",
        "지식재산처": "Kipo", "해양경찰청": "Kcg",
        "행정중심복합도시건설청": "Naacc",
    }

    # ==================== TOOL 41: cgm_expc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def cgm_expc_search(
        ministry: str,
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
                고용노동부, 국토교통부, 기획재정부, 해양수산부, 행정안전부,
                기후에너지환경부, 관세청, 국세청, 교육부, 과학기술정보통신부,
                국가보훈부, 국방부, 농림축산식품부, 문화체육관광부, 법무부,
                보건복지부, 산업통상부, 성평등가족부, 외교부, 중소벤처기업부,
                통일부, 법제처, 식품의약품안전처, 인사혁신처, 기상청,
                국가유산청, 농촌진흥청, 경찰청, 방위사업청, 병무청, 산림청,
                소방청, 재외동포청, 조달청, 질병관리청, 국가데이터처,
                지식재산처, 해양경찰청, 행정중심복합도시건설청
            query: Search keyword (default "*")
            display: Number of results per page (max 100, default 20)
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to env var)
            type: Response format - "HTML" or "XML" (default "XML")
            search: 1=사건명 (case name), 2=본문검색 (full text)
            sort: Sort order
            gana: Dictionary search
            ctx: MCP context (injected automatically)

        Returns:
            Ministry interpretation list or error

        Examples:
            Search 고용노동부 interpretations:
            >>> cgm_expc_search(ministry="고용노동부", query="퇴직금")
        """
        code = MINISTRY_CODES.get(ministry)
        if not code:
            valid = ", ".join(MINISTRY_CODES.keys())
            raise ValueError(f"Invalid ministry: '{ministry}'. Valid values: {valid}")

        target = f"cgmExpc{code}"
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
            ranking_field="사건명", list_type="items", item_category=target,
            over_fetch_key="display",
        )

    # ==================== TOOL 42: cgm_expc_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def cgm_expc_service(
        ministry: str,
        id: Union[str, int],
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve ministry interpretation full text (중앙부처 1차 해석 본문 조회).

        Args:
            ministry: Ministry name (same values as cgm_expc_search)
            id: Interpretation serial number (해석례일련번호)
            oc: Optional OC override
            type: Response format - "HTML" or "XML" (default "XML")
            ctx: MCP context (injected automatically)

        Returns:
            Full interpretation text or error
        """
        code = MINISTRY_CODES.get(ministry)
        if not code:
            valid = ", ".join(MINISTRY_CODES.keys())
            raise ValueError(f"Invalid ministry: '{ministry}'. Valid values: {valid}")

        target = f"cgmExpc{code}"
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target,
            "id": str(id), "type": type,
        }
        return run_service(get_client=_get_client, target=target,
                          snake_params=snake_params, response_type=type)

    # ==================== TASK 14: 특별행정심판 ====================

    # Special tribunal target code mapping (for {Code}SpecialDecc pattern)
    TRIBUNAL_CODES = {
        "조세심판원": "tt",
        "해양안전심판원": "kmst",
        "국민권익위원회": "acr",
        "인사혁신처 소청심사위원회": "adap",
    }

    # ==================== TOOL 43: special_decc_search ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def special_decc_search(
        tribunal: str,
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
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
            type: Response format - "HTML" or "XML" (default "XML")
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

        target = f"{code}SpecialDecc"
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

        return run_search(
            get_client=_get_client, target=target, query=query,
            snake_params=snake_params, response_type=type, display=display,
            ranking_field="사건명", list_type="items", item_category=target,
            over_fetch_key="display",
        )

    # ==================== TOOL 44: special_decc_service ====================
    @server.tool(annotations=TOOL_ANNOTATIONS)
    @handle_tool_error
    def special_decc_service(
        tribunal: str,
        id: Union[str, int],
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve special administrative appeal decision full text (특별행정심판 본문 조회).

        Args:
            tribunal: Tribunal name (same values as special_decc_search)
            id: Decision serial number (재결례일련번호)
            oc: Optional OC override
            type: Response format - "HTML" or "XML" (default "XML")
            ctx: MCP context (injected automatically)

        Returns:
            Full decision text or error
        """
        code = TRIBUNAL_CODES.get(tribunal)
        if not code:
            valid = ", ".join(TRIBUNAL_CODES.keys())
            raise ValueError(f"Invalid tribunal: '{tribunal}'. Valid values: {valid}")

        target = f"{code}SpecialDecc"
        resolved_oc = resolve_oc(override_oc=oc)
        snake_params = {
            "oc": resolved_oc, "target": target,
            "id": str(id), "type": type,
        }
        return run_service(get_client=_get_client, target=target,
                          snake_params=snake_params, response_type=type)

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
3. eflaw_search/law_search (keyword) - fallback for precise matches"""
                }
            }
        ]

    logger.info("LexLink server initialized with 26 tools, 6 prompts, and 2 resources")
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
    logger.info("Prompts (6): search-korean-law, get-law-article, get-article-with-citations, analyze-law-citations, search-admin-rules, tool-selection-guide")
    logger.info("Resources (2): frequently-used-laws (static), law-code-lookup (template)")
    return server
