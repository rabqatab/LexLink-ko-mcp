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
from mcp.types import ToolAnnotations
from smithery.decorators import smithery

from .client import LawAPIClient
from .config import LexLinkConfig
from .errors import ErrorCode, create_error_response
from .params import map_params_to_upstream, resolve_oc
from .validation import validate_date_range
from .parser import parse_xml_response, extract_law_list, update_law_list, extract_items_list, update_items_list
from .ranking import rank_search_results, should_apply_ranking, detect_query_language

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def slim_response(response: dict) -> dict:
    """
    Slim down response for size-constrained platforms (e.g., Kakao PlayMCP).

    When SLIM_RESPONSE=true:
    - Removes 'raw_content' (XML) entirely
    - Keeps only essential fields in 'ranked_data' items

    When not set, returns response unchanged (for Smithery.ai compatibility).

    Args:
        response: The response dictionary containing 'raw_content' and/or 'ranked_data'

    Returns:
        Original response or slimmed response with essential fields only
    """
    if not os.getenv("SLIM_RESPONSE"):
        return response

    result = response.copy()

    # Remove raw_content entirely
    result.pop("raw_content", None)

    # Slim down ranked_data to essential fields only
    if "ranked_data" in result and isinstance(result["ranked_data"], dict):
        ranked_data = result["ranked_data"].copy()

        # Pattern-based essential field detection
        # Works automatically for any data type without manual definitions
        essential_patterns = [
            r'.*일련번호$',      # IDs: 판례일련번호, 법령일련번호, 헌재결정례일련번호, etc.
            r'.*명한글$',        # Korean names: 법령명한글
            r'^사건명$',         # Case name
            r'^사건번호$',       # Case number
            r'^안건번호$',       # Agenda number
            r'.*일자$',          # Dates: 선고일자, 시행일자, 재결일자, 회신일자, etc.
            r'^법령ID$',         # Law ID (special case)
            r'^현행연혁코드$',   # Law status code
            r'^법원명$',         # Court name
            r'^종국결과$',       # Constitutional court result
            r'^재결결과$',       # Administrative appeal result
            r'^회신기관$',       # Reply organization
            r'^소관부처명$',     # Ministry name
            r'.*규칙명$',        # Rule names: 행정규칙명
            r'.*해석례명$',      # Interpretation names: 법령해석례명
        ]

        def is_essential_field(field_name: str) -> bool:
            """Check if field matches any essential pattern."""
            return any(re.match(pattern, field_name) for pattern in essential_patterns)

        # Find and slim the data list (case-insensitive key matching)
        # API uses inconsistent casing: 'prec' vs 'Detc' vs 'Expc' vs 'Decc'
        list_keys = ["law", "prec", "detc", "expc", "decc", "admrul", "elaw"]
        for target_key in list_keys:
            # Case-insensitive key lookup
            actual_key = None
            for key in ranked_data.keys():
                if key.lower() == target_key.lower():
                    actual_key = key
                    break

            if actual_key:
                items = ranked_data[actual_key]
                if isinstance(items, list):
                    ranked_data[actual_key] = [
                        {k: v for k, v in item.items() if is_essential_field(k)}
                        for item in items
                    ]
                elif isinstance(items, dict):
                    ranked_data[actual_key] = {k: v for k, v in items.items() if is_essential_field(k)}
                break

        result["ranked_data"] = ranked_data
        result["slimmed"] = True

    return result


@smithery.server(config_schema=LexLinkConfig)
def create_server(session_config: Optional[LexLinkConfig] = None) -> FastMCP:
    """
    Create and configure the LexLink MCP server.

    This factory function is called by Smithery to create the server instance.
    Tools access session configuration via Context parameter injection at request time.

    Args:
        session_config: User configuration from Smithery session (available at request time via Context)

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

## Quick Reference
- MST (법령일련번호): Unique law identifier from search results
- Article format: "000300" = 제3조, "001102" = 제11조의2
"""

    server = FastMCP("LexLink - Korean Law API", instructions=SERVER_INSTRUCTIONS)

    # Get client configuration from session or use defaults
    def _get_client() -> LawAPIClient:
        """Create HTTP client with default or session configuration."""
        if session_config:
            return LawAPIClient(
                base_url=session_config.base_url,
                timeout=session_config.http_timeout_s
            )
        return LawAPIClient()

    # ==================== TOOL 1: eflaw_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
        ctx: Context = None,  # ← Context injection for session config
    ) -> dict:
        """
        Search current laws by effective date (시행일 기준 현행법령 검색).

        This tool searches Korean laws organized by effective date.
        Use this when you need to find laws that are currently in effect.

        Args:
            query: Search keyword (law name or content)
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # 1. Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # 2. Resolve OC parameter with all 3 priority levels
            resolved_oc = resolve_oc(
                override_oc=oc,        # Priority 1: Tool argument
                session_oc=session_oc  # Priority 2: Session config (FROM CONTEXT!)
            )
            # Priority 3: Environment variable (handled in resolve_oc)

            # 2. Build parameter dict (snake_case)
            snake_params = {
                "oc": resolved_oc,
                "target": "eflaw",
                "type": type,
                "query": query,
                "display": display,
                "page": page,
            }

            # Add optional params
            if sort:
                snake_params["sort"] = sort
            if ef_yd:
                # Validate date range format
                validate_date_range(ef_yd, "ef_yd")
                snake_params["ef_yd"] = ef_yd
            if org:
                snake_params["org"] = org
            if knd:
                snake_params["knd"] = knd

            # 3. Map to upstream format
            upstream_params = map_params_to_upstream(snake_params)

            # 4. Determine if we need to fetch more results for ranking
            original_display = display
            ranking_enabled = (type == "XML" and should_apply_ranking(query))

            if ranking_enabled and original_display < 100:
                # Fetch more results to rank (up to 100, API max) for better relevance
                upstream_params["numOfRows"] = "100"
                logger.debug(f"Ranking enabled: fetching 100 results instead of {original_display}")

            # 5. Execute request
            client = _get_client()
            response = client.get("/DRF/lawSearch.do", upstream_params, type)

            # 6. Apply relevance ranking if XML response and appropriate query
            if response.get("status") == "ok" and ranking_enabled:
                raw_content = response.get("raw_content", "")
                if raw_content:
                    # Parse XML
                    parsed_data = parse_xml_response(raw_content)
                    if parsed_data:
                        # Extract law list
                        laws = extract_law_list(parsed_data)
                        if laws:
                            # Rank by relevance (exact matches first)
                            ranked_laws = rank_search_results(laws, query, "법령명한글")

                            # Trim to original requested display amount
                            if len(ranked_laws) > original_display:
                                ranked_laws = ranked_laws[:original_display]
                                logger.debug(f"Trimmed results from {len(laws)} to {original_display}")

                            # Update parsed data with ranked results
                            parsed_data = update_law_list(parsed_data, ranked_laws)
                            # Update numOfRows to reflect trimmed results
                            parsed_data["numOfRows"] = str(original_display)
                            # Add ranked data to response for LLM consumption
                            response["ranked_data"] = parsed_data

            return slim_response(response)

        except ValueError as e:
            # Configuration or validation error
            logger.warning(f"Validation error in eflaw_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
                hints=[
                    "Check parameter formats",
                    "See tool documentation for valid values",
                ]
            )
        except Exception as e:
            # Unexpected error
            logger.exception(f"Unexpected error in eflaw_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}",
                hints=[
                    "This is an internal server error",
                    "Check server logs for details",
                ]
            )

    # ==================== TOOL 2: law_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
        ctx: Context = None,  # ← Context injection for session config
    ) -> dict:
        """
        Search current laws by announcement date (공포일 기준 현행법령 검색).

        This tool searches Korean laws organized by announcement (publication) date.

        Args:
            query: Search keyword (law name or content)
            display: Number of results per page (max 100, default 20). **Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found.**
            page: Page number (1-based, default 1)
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
            sort: Sort order
            date: Announcement date (YYYYMMDD)
            org: Ministry/department code filter
            knd: Law type filter

        Returns:
            Search results with law list or error
        """
        try:
            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with all 3 priority levels
            resolved_oc = resolve_oc(
                override_oc=oc,
                session_oc=session_oc
            )

            snake_params = {
                "oc": resolved_oc,
                "target": "law",
                "type": type,
                "query": query,
                "display": display,
                "page": page,
            }

            if sort:
                snake_params["sort"] = sort
            if date:
                snake_params["date"] = date
            if org:
                snake_params["org"] = org
            if knd:
                snake_params["knd"] = knd

            upstream_params = map_params_to_upstream(snake_params)

            # Determine if we need to fetch more results for ranking
            original_display = display
            ranking_enabled = (type == "XML" and should_apply_ranking(query))

            if ranking_enabled and original_display < 100:
                # Fetch more results to rank (up to 100, API max) for better relevance
                upstream_params["numOfRows"] = "100"
                logger.debug(f"Ranking enabled: fetching 100 results instead of {original_display}")

            client = _get_client()
            response = client.get("/DRF/lawSearch.do", upstream_params, type)

            # Apply relevance ranking if XML response and appropriate query
            if response.get("status") == "ok" and ranking_enabled:
                raw_content = response.get("raw_content", "")
                if raw_content:
                    parsed_data = parse_xml_response(raw_content)
                    if parsed_data:
                        laws = extract_law_list(parsed_data)
                        if laws:
                            ranked_laws = rank_search_results(laws, query, "법령명한글")

                            # Trim to original requested display amount
                            if len(ranked_laws) > original_display:
                                ranked_laws = ranked_laws[:original_display]
                                logger.debug(f"Trimmed results from {len(laws)} to {original_display}")

                            parsed_data = update_law_list(parsed_data, ranked_laws)
                            # Update numOfRows to reflect trimmed results
                            parsed_data["numOfRows"] = str(original_display)
                            response["ranked_data"] = parsed_data

            return slim_response(response)

        except ValueError as e:
            logger.warning(f"Validation error in law_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in law_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 3: eflaw_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

        Returns:
            Full law content or specific article content

        Examples:
            Retrieve specific article (RECOMMENDED):
            >>> eflaw_service(mst="279823", jo="017400", type="XML")  # 자본시장법 제174조

            Retrieve full law (WARNING: large response for some laws):
            >>> eflaw_service(id="1747", type="XML")
        """
        try:
            # Convert id/mst/jo to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)
            if jo is not None:
                jo = str(jo)

            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with all 3 priority levels
            resolved_oc = resolve_oc(
                override_oc=oc,
                session_oc=session_oc
            )

            # Validate that either id or mst is provided
            if not id and not mst:
                raise ValueError("Either 'id' or 'mst' parameter is required")

            # Build parameter dict
            snake_params = {
                "oc": resolved_oc,
                "target": "eflaw",
                "type": type,
            }

            # Add id or mst
            if id:
                snake_params["id"] = id
            if mst:
                snake_params["mst"] = mst

            # Add optional params
            if ef_yd:
                snake_params["ef_yd"] = ef_yd
            if jo:
                snake_params["jo"] = jo
            if chr_cls_cd:
                snake_params["chr_cls_cd"] = chr_cls_cd

            # Map to upstream format
            upstream_params = map_params_to_upstream(snake_params)

            # Execute request
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, type)

        except ValueError as e:
            logger.warning(f"Validation error in eflaw_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
                hints=[
                    "Provide either 'id' or 'mst' parameter",
                    "When using 'mst', provide 'ef_yd' (effective date)",
                ]
            )
        except Exception as e:
            logger.exception(f"Unexpected error in eflaw_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 4: law_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

        Returns:
            Full law content or specific article content

        Examples:
            Retrieve specific article (RECOMMENDED):
            >>> law_service(mst="279823", jo="017400", type="XML")  # 자본시장법 제174조

            Retrieve full law (WARNING: large response for some laws):
            >>> law_service(id="009682", type="XML")
        """
        try:
            # Convert id/mst/jo to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)
            if jo is not None:
                jo = str(jo)

            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with all 3 priority levels
            resolved_oc = resolve_oc(
                override_oc=oc,
                session_oc=session_oc
            )

            # Validate that either id or mst is provided
            if not id and not mst:
                raise ValueError("Either 'id' or 'mst' parameter is required")

            # Build parameter dict
            snake_params = {
                "oc": resolved_oc,
                "target": "law",
                "type": type,
            }

            # Add id or mst
            if id:
                snake_params["id"] = id
            if mst:
                snake_params["mst"] = mst

            # Add optional params
            if lm:
                snake_params["lm"] = lm
            if ld:
                snake_params["ld"] = ld
            if ln:
                snake_params["ln"] = ln
            if jo:
                snake_params["jo"] = jo
            if lang:
                snake_params["lang"] = lang

            # Map to upstream format
            upstream_params = map_params_to_upstream(snake_params)

            # Execute request
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, type)

        except ValueError as e:
            logger.warning(f"Validation error in law_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
                hints=[
                    "Provide either 'id' or 'mst' parameter",
                ]
            )
        except Exception as e:
            logger.exception(f"Unexpected error in law_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 5: eflaw_josub ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

        Returns:
            Specific law section content

        Examples:
            Query 자본시장법 제174조:
            >>> eflaw_josub(mst="279823", jo="017400", type="XML")

            Query 건축법 제3조 제1항:
            >>> eflaw_josub(mst="276925", jo="000300", hang="000100", type="XML")
        """
        try:
            # Convert id/mst/jo to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)
            if jo is not None:
                jo = str(jo)

            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with all 3 priority levels
            resolved_oc = resolve_oc(
                override_oc=oc,
                session_oc=session_oc
            )

            # Validate that either id or mst is provided
            if not id and not mst:
                raise ValueError("Either 'id' or 'mst' parameter is required")

            # Build parameter dict
            snake_params = {
                "oc": resolved_oc,
                "target": "eflawjosub",
                "type": type,
            }

            # Add id or mst
            if id:
                snake_params["id"] = id
            if mst:
                snake_params["mst"] = mst

            # Add optional params
            if ef_yd:
                snake_params["ef_yd"] = ef_yd
            if jo:
                snake_params["jo"] = jo
            if hang:
                snake_params["hang"] = hang
            if ho:
                snake_params["ho"] = ho
            if mok:
                snake_params["mok"] = mok

            # Map to upstream format
            upstream_params = map_params_to_upstream(snake_params)

            # Execute request
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, type)

        except ValueError as e:
            logger.warning(f"Validation error in eflaw_josub: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
                hints=[
                    "Provide either 'id' or 'mst' parameter",
                    "When using 'mst', provide 'ef_yd' (effective date)",
                ]
            )
        except Exception as e:
            logger.exception(f"Unexpected error in eflaw_josub: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 6: law_josub ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

        Returns:
            Specific law section content

        Examples:
            Query 자본시장법 제174조:
            >>> law_josub(mst="279823", jo="017400", type="XML")

            Query 건축법 제3조 제1항:
            >>> law_josub(mst="276925", jo="000300", hang="000100", type="XML")
        """
        try:
            # Convert id/mst/jo to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)
            if jo is not None:
                jo = str(jo)

            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with all 3 priority levels
            resolved_oc = resolve_oc(
                override_oc=oc,
                session_oc=session_oc
            )

            # Validate that either id or mst is provided
            if not id and not mst:
                raise ValueError("Either 'id' or 'mst' parameter is required")

            # Build parameter dict
            snake_params = {
                "oc": resolved_oc,
                "target": "lawjosub",
                "type": type,
            }

            # Add id or mst
            if id:
                snake_params["id"] = id
            if mst:
                snake_params["mst"] = mst

            # Add optional params
            if jo:
                snake_params["jo"] = jo
            if hang:
                snake_params["hang"] = hang
            if ho:
                snake_params["ho"] = ho
            if mok:
                snake_params["mok"] = mok

            # Map to upstream format
            upstream_params = map_params_to_upstream(snake_params)

            # Execute request
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, type)

        except ValueError as e:
            logger.warning(f"Validation error in law_josub: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
                hints=[
                    "Provide either 'id' or 'mst' parameter",
                ]
            )
        except Exception as e:
            logger.exception(f"Unexpected error in law_josub: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 7: elaw_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

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

        except ValueError as e:
            logger.error(f"Validation error in elaw_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in elaw_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 8: elaw_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Convert id/mst to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)

            # Require either id or mst
            if not id and not mst:
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Either 'id' or 'mst' parameter is required",
                    hints=[
                        "Provide 'id' (law ID) or 'mst' (law master number)",
                        "Get these from elaw_search results",
                        "Example: id='000744' or mst='127280'"
                    ]
                )

            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "elaw",
            }

            # Add id or mst
            if id:
                params["id"] = id
            if mst:
                params["mst"] = mst

            # Add optional parameters
            if lm:
                params["lm"] = lm
            if ld:
                params["ld"] = ld
            if ln:
                params["ln"] = ln

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, response_type=type)

        except ValueError as e:
            logger.error(f"Validation error in elaw_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in elaw_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 9: admrul_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Validate date ranges if provided
            if prml_yd:
                validate_date_range(prml_yd, "prml_yd")
            if mod_yd:
                validate_date_range(mod_yd, "mod_yd")

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "admrul",
                "query": query,
                "display": display,
                "page": page,
                "nw": nw,
                "search": search,
            }

            # Add optional parameters
            if org:
                params["org"] = org
            if knd:
                params["knd"] = knd
            if date:
                params["date"] = date
            if prml_yd:
                params["prml_yd"] = prml_yd
            if mod_yd:
                params["mod_yd"] = mod_yd
            if sort:
                params["sort"] = sort

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

            # Apply relevance ranking for administrative rules
            if response.get("status") == "ok" and ranking_enabled:
                raw_content = response.get("raw_content", "")
                if raw_content:
                    parsed_data = parse_xml_response(raw_content)
                    if parsed_data:
                        # Extract administrative rules list (key might be "admrul" instead of "law")
                        rules = parsed_data.get("admrul", [])
                        if not isinstance(rules, list):
                            rules = [rules] if rules else []
                        if rules:
                            # Administrative rules use "행정규칙명" field
                            ranked_rules = rank_search_results(rules, query, "행정규칙명")

                            # Trim to original requested display amount
                            if len(ranked_rules) > original_display:
                                ranked_rules = ranked_rules[:original_display]
                                logger.debug(f"Trimmed results from {len(rules)} to {original_display}")

                            parsed_data["admrul"] = ranked_rules
                            # Update numOfRows to reflect trimmed results
                            parsed_data["numOfRows"] = str(original_display)
                            response["ranked_data"] = parsed_data

            return slim_response(response)

        except ValueError as e:
            logger.error(f"Validation error in admrul_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in admrul_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 10: admrul_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Convert id/lid to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if lid is not None:
                lid = str(lid)

            # Require at least one identifier
            if not id and not lid and not lm:
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="At least one of 'id', 'lid', or 'lm' is required",
                    hints=[
                        "Provide 'id' (rule sequence number), 'lid' (rule ID), or 'lm' (rule name)",
                        "Get these from admrul_search results",
                        "Example: id='62505' or lid='10000005747'"
                    ]
                )

            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "admrul",
            }

            # Add identifiers
            if id:
                params["id"] = id
            if lid:
                params["lid"] = lid
            if lm:
                params["lm"] = lm

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, response_type=type)

        except ValueError as e:
            logger.error(f"Validation error in admrul_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in admrul_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 11: lnkLs_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
            sort: Sort order - "lasc"|"ldes"|"dasc"|"ddes"|"nasc"|"ndes"
            ctx: MCP context (injected automatically)

        Returns:
            Search results with linked laws list or error

        Examples:
            Search for "자동차관리법":
            >>> lnkLs_search(query="자동차관리법", type="XML")
        """
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "lnkLs",
                "query": query,
                "display": display,
                "page": page,
            }

            # Add optional parameters
            if sort:
                params["sort"] = sort

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            response = client.get("/DRF/lawSearch.do", upstream_params, response_type=type)
            return slim_response(response)

        except ValueError as e:
            logger.error(f"Validation error in lnkLs_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in lnkLs_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 12: lnkLsOrdJo_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "lnkLsOrdJo",
                "query": query,
                "display": display,
                "page": page,
            }

            # Add optional parameters
            if knd:
                params["knd"] = knd
            if jo is not None:
                # Convert to 4-digit format if needed
                params["jo"] = jo if jo >= 1000 else jo
            if jobr is not None:
                params["jobr"] = jobr
            if sort:
                params["sort"] = sort

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            response = client.get("/DRF/lawSearch.do", upstream_params, response_type=type)
            return slim_response(response)

        except ValueError as e:
            logger.error(f"Validation error in lnkLsOrdJo_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in lnkLsOrdJo_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 13: lnkDep_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)
            sort: Sort order
            ctx: MCP context (injected automatically)

        Returns:
            Search results with ministry's linked ordinances or error

        Examples:
            Search ordinances linked to ministry 1400000:
            >>> lnkDep_search(org="1400000", type="XML")
        """
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "lnkDep",
                "org": org,
                "display": display,
                "page": page,
            }

            # Add optional parameters
            if sort:
                params["sort"] = sort

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            response = client.get("/DRF/lawSearch.do", upstream_params, response_type=type)
            return slim_response(response)

        except ValueError as e:
            logger.error(f"Validation error in lnkDep_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in lnkDep_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 14: drlaw_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
            ctx: MCP context (injected automatically)

        Returns:
            HTML response with linkage statistics or error

        Examples:
            Get linkage statistics:
            >>> drlaw_search()
        """
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters (HTML only)
            params = {
                "oc": resolved_oc,
                "target": "drlaw",
            }

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API (force HTML as only supported format)
            client = _get_client()
            return client.get("/DRF/lawSearch.do", upstream_params, response_type="HTML")

        except ValueError as e:
            logger.error(f"Validation error in drlaw_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in drlaw_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 15: lsDelegated_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "XML" only (JSON not supported by API, HTML not available)
            ctx: MCP context (injected automatically)

        Returns:
            Delegation hierarchy with delegated laws/rules/ordinances or error

        Examples:
            Retrieve delegations for 초·중등교육법:
            >>> lsDelegated_service(id="000900", type="XML")
        """
        try:
            # Convert id/mst to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)

            # Require either id or mst
            if not id and not mst:
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Either 'id' or 'mst' parameter is required",
                    hints=[
                        "Provide 'id' (law ID) or 'mst' (law master number)",
                        "Get these from law search results",
                        "Example: id='000900' (초·중등교육법)"
                    ]
                )

            # Warn if HTML requested
            if type.upper() == "HTML":
                logger.warning("lsDelegated_service does not support HTML format, using XML")
                type = "XML"

            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "lsDelegated",
            }

            # Add id or mst
            if id:
                params["id"] = id
            if mst:
                params["mst"] = mst

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, response_type=type)

        except ValueError as e:
            logger.error(f"Validation error in lsDelegated_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in lsDelegated_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== PHASE 3: CASE LAW & LEGAL RESEARCH ====================

    # ==================== TOOL 16: prec_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameter dict
            snake_params = {
                "oc": resolved_oc,
                "target": "prec",
                "type": type,
                "query": query,
                "display": display,
                "page": page,
            }

            # Add optional params
            if search:
                snake_params["search"] = search
            if sort:
                snake_params["sort"] = sort
            if org:
                snake_params["org"] = org
            if curt:
                snake_params["curt"] = curt
            if jo:
                snake_params["jo"] = jo
            if gana:
                snake_params["gana"] = gana
            if date:
                snake_params["date"] = date
            if prnc_yd:
                validate_date_range(prnc_yd, "prnc_yd")
                snake_params["prnc_yd"] = prnc_yd
            if nb:
                snake_params["nb"] = nb
            if dat_src_nm:
                snake_params["dat_src_nm"] = dat_src_nm
            if pop_yn:
                snake_params["pop_yn"] = pop_yn

            # Map to upstream format
            upstream_params = map_params_to_upstream(snake_params)

            # Determine if we need to fetch more results for ranking
            original_display = display
            ranking_enabled = (type == "XML" and should_apply_ranking(query))

            if ranking_enabled and original_display < 100:
                upstream_params["display"] = "100"
                logger.debug(f"Ranking enabled: fetching 100 results instead of {original_display}")

            # Execute request
            client = _get_client()
            response = client.get("/DRF/lawSearch.do", upstream_params, type)

            # Apply relevance ranking if XML response
            if response.get("status") == "ok" and ranking_enabled:
                raw_content = response.get("raw_content", "")
                if raw_content:
                    parsed_data = parse_xml_response(raw_content)
                    if parsed_data:
                        items = extract_items_list(parsed_data, 'prec')
                        if items:
                            ranked_items = rank_search_results(items, query, "판례명")
                            if len(ranked_items) > original_display:
                                ranked_items = ranked_items[:original_display]
                            parsed_data = update_items_list(parsed_data, ranked_items, 'prec')
                            parsed_data["display"] = str(original_display)
                            response["ranked_data"] = parsed_data

            return slim_response(response)

        except ValueError as e:
            logger.error(f"Validation error in prec_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in prec_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 17: prec_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "prec",
                "id": str(id),
                "type": type,
            }

            if lm:
                params["lm"] = lm

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, response_type=type)

        except ValueError as e:
            logger.error(f"Validation error in prec_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in prec_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 18: detc_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameter dict
            snake_params = {
                "oc": resolved_oc,
                "target": "detc",
                "type": type,
                "query": query,
                "display": display,
                "page": page,
            }

            # Add optional params
            if search:
                snake_params["search"] = search
            if gana:
                snake_params["gana"] = gana
            if sort:
                snake_params["sort"] = sort
            if date:
                snake_params["date"] = date
            if ed_yd:
                validate_date_range(ed_yd, "ed_yd")
                snake_params["ed_yd"] = ed_yd
            if nb:
                snake_params["nb"] = nb
            if pop_yn:
                snake_params["pop_yn"] = pop_yn

            # Map to upstream format
            upstream_params = map_params_to_upstream(snake_params)

            # Determine if we need to fetch more results for ranking
            original_display = display
            ranking_enabled = (type == "XML" and should_apply_ranking(query))

            if ranking_enabled and original_display < 100:
                upstream_params["display"] = "100"
                logger.debug(f"Ranking enabled: fetching 100 results instead of {original_display}")

            # Execute request
            client = _get_client()
            response = client.get("/DRF/lawSearch.do", upstream_params, type)

            # Apply relevance ranking if XML response
            if response.get("status") == "ok" and ranking_enabled:
                raw_content = response.get("raw_content", "")
                if raw_content:
                    parsed_data = parse_xml_response(raw_content)
                    if parsed_data:
                        items = extract_items_list(parsed_data, 'detc')
                        if items:
                            ranked_items = rank_search_results(items, query, "사건명")
                            if len(ranked_items) > original_display:
                                ranked_items = ranked_items[:original_display]
                            parsed_data = update_items_list(parsed_data, ranked_items, 'detc')
                            parsed_data["display"] = str(original_display)
                            response["ranked_data"] = parsed_data

            return slim_response(response)

        except ValueError as e:
            logger.error(f"Validation error in detc_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in detc_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 19: detc_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "detc",
                "id": str(id),
                "type": type,
            }

            if lm:
                params["lm"] = lm

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, response_type=type)

        except ValueError as e:
            logger.error(f"Validation error in detc_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in detc_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 20: expc_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Validate date ranges if provided
            if reg_yd:
                validate_date_range(reg_yd, "reg_yd")
            if expl_yd:
                validate_date_range(expl_yd, "expl_yd")

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "expc",
                "query": query,
                "display": display,
                "page": page,
                "search": search,
            }

            # Add optional parameters
            if inq:
                params["inq"] = inq
            if rpl is not None:
                params["rpl"] = rpl
            if gana:
                params["gana"] = gana
            if itmno is not None:
                params["itmno"] = itmno
            if reg_yd:
                params["reg_yd"] = reg_yd
            if expl_yd:
                params["expl_yd"] = expl_yd
            if sort:
                params["sort"] = sort
            if pop_yn:
                params["pop_yn"] = pop_yn

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

            # Apply relevance ranking for legal interpretations
            if response.get("status") == "ok" and ranking_enabled:
                raw_content = response.get("raw_content", "")
                if raw_content:
                    parsed_data = parse_xml_response(raw_content)
                    if parsed_data:
                        # Extract interpretations list using 'Expc' tag
                        from .parser import extract_items_list, update_items_list
                        interpretations = extract_items_list(parsed_data, 'expc')
                        if interpretations:
                            # Rank by relevance using '안건명' field
                            ranked_interpretations = rank_search_results(interpretations, query, "안건명")

                            # Trim to original requested display amount
                            if len(ranked_interpretations) > original_display:
                                ranked_interpretations = ranked_interpretations[:original_display]
                                logger.debug(f"Trimmed results from {len(interpretations)} to {original_display}")

                            # Update parsed data with ranked results
                            parsed_data = update_items_list(parsed_data, ranked_interpretations, 'expc')
                            # Update numOfRows to reflect trimmed results
                            parsed_data["numOfRows"] = str(original_display)
                            response["ranked_data"] = parsed_data

            return slim_response(response)

        except ValueError as e:
            logger.error(f"Validation error in expc_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in expc_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 17: expc_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Convert id to string if it's an integer (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)

            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "expc",
                "id": id,
            }

            # Add optional parameter
            if lm:
                params["lm"] = lm

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, response_type=type)

        except ValueError as e:
            logger.error(f"Validation error in expc_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in expc_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 18: decc_search ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Validate date ranges if provided
            if dpa_yd:
                validate_date_range(dpa_yd, "dpa_yd")
            if rsl_yd:
                validate_date_range(rsl_yd, "rsl_yd")

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "decc",
                "query": query,
                "display": display,
                "page": page,
                "search": search,
            }

            # Add optional parameters
            if cls:
                params["cls"] = cls
            if gana:
                params["gana"] = gana
            if date:
                params["date"] = date
            if dpa_yd:
                params["dpa_yd"] = dpa_yd
            if rsl_yd:
                params["rsl_yd"] = rsl_yd
            if sort:
                params["sort"] = sort
            if pop_yn:
                params["pop_yn"] = pop_yn

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

            # Apply relevance ranking for administrative appeal decisions
            if response.get("status") == "ok" and ranking_enabled:
                raw_content = response.get("raw_content", "")
                if raw_content:
                    parsed_data = parse_xml_response(raw_content)
                    if parsed_data:
                        # Extract administrative appeal decisions list using 'Decc' tag
                        decisions = extract_items_list(parsed_data, 'decc')
                        if decisions:
                            # Administrative appeal decisions use "사건명" (case_name) field
                            ranked_decisions = rank_search_results(decisions, query, "사건명")

                            # Trim to original requested display amount
                            if len(ranked_decisions) > original_display:
                                ranked_decisions = ranked_decisions[:original_display]
                                logger.debug(f"Trimmed results from {len(decisions)} to {original_display}")

                            # Update parsed data with ranked results
                            parsed_data = update_items_list(parsed_data, ranked_decisions, 'decc')
                            # Update numOfRows to reflect trimmed results
                            parsed_data["numOfRows"] = str(original_display)
                            response["ranked_data"] = parsed_data

            return slim_response(response)

        except ValueError as e:
            logger.error(f"Validation error in decc_search: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in decc_search: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== TOOL 19: decc_service ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)
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
        try:
            # Convert id to string if it's an integer (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)

            # Access session config from Context
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            # Resolve OC with 3-tier priority
            resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)

            # Build parameters
            params = {
                "oc": resolved_oc,
                "target": "decc",
                "id": id,
            }

            # Add optional parameters
            if lm:
                params["lm"] = lm

            # Map to upstream format
            upstream_params = map_params_to_upstream(params)

            # Call API
            client = _get_client()
            return client.get("/DRF/lawService.do", upstream_params, response_type=type)

        except ValueError as e:
            logger.error(f"Validation error in decc_service: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error in decc_service: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

    # ==================== PHASE 4: ARTICLE CITATION ====================

    # ==================== TOOL 24: article_citation ====================
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True
        )
    )
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
            oc: Optional OC override (defaults to session config or env)

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
        try:
            # Import citation extractor
            from .citation import extract_article_citations

            # OC is not strictly required for citation extraction (uses HTML scraping)
            # but we validate it for consistency with other tools
            config = ctx.session_config if ctx else None
            session_oc = getattr(config, 'oc', None) if config else None

            try:
                resolved_oc = resolve_oc(override_oc=oc, session_oc=session_oc)
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

        except ValueError as e:
            logger.warning(f"Validation error in article_citation: {e}")
            return create_error_response(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
                hints=[
                    "mst: Get from eflaw_search or law_search results (법령일련번호)",
                    "law_name: Full Korean law name",
                    "article: Positive integer (e.g., 3 for 제3조)",
                    "article_branch: For 가지조문 like 제37조의2, use article=37, article_branch=2"
                ]
            )
        except Exception as e:
            logger.exception(f"Unexpected error in article_citation: {e}")
            return create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}",
                hints=[
                    "Check that the law name is correct",
                    "Verify the article number exists in the law",
                    "Try with a different law to isolate the issue"
                ]
            )

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

    logger.info("LexLink server initialized with 24 tools and 5 prompts")
    logger.info("Phase 1 & 2 Tools (15):")
    logger.info("  - eflaw_search, law_search, eflaw_service, law_service, eflaw_josub, law_josub")
    logger.info("  - elaw_search, elaw_service, admrul_search, admrul_service")
    logger.info("  - lnkLs_search, lnkLsOrdJo_search, lnkDep_search, drlaw_search, lsDelegated_service")
    logger.info("Phase 3 Tools (8):")
    logger.info("  - prec_search, prec_service, detc_search, detc_service")
    logger.info("  - expc_search, expc_service, decc_search, decc_service")
    logger.info("Phase 4 Tools (1):")
    logger.info("  - article_citation")
    logger.info("Prompts (5): search-korean-law, get-law-article, get-article-with-citations, analyze-law-citations, search-admin-rules")
    logger.info(f"Session config: {session_config is not None}")

    return server
