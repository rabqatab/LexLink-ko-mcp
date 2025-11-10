"""
LexLink MCP Server - Korean National Law Information API.

This server exposes the law.go.kr Open API through MCP tools,
enabling AI agents to search and retrieve Korean legal information.

⚠️ IMPORTANT: The law.go.kr API does NOT support JSON format despite
documentation. All tools default to XML format. Use XML or HTML only.
"""

import logging
import os
from typing import Optional, Union

from mcp.server.fastmcp import FastMCP, Context
from smithery.decorators import smithery

from .client import LawAPIClient
from .config import LexLinkConfig
from .errors import ErrorCode, create_error_response
from .params import map_params_to_upstream, resolve_oc
from .validation import validate_date_range

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    server = FastMCP("LexLink - Korean Law API")

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
    @server.tool()
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
            display: Number of results per page (max 100, default 20)
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
            session_oc = config.oc if config else None

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

            # 4. Execute request
            client = _get_client()
            return client.get("/DRF/lawSearch.do", upstream_params, type)

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
    @server.tool()
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
            display: Number of results per page (max 100, default 20)
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
            session_oc = config.oc if config else None

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
            client = _get_client()
            return client.get("/DRF/lawSearch.do", upstream_params, type)

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
    @server.tool()
    def eflaw_service(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        ef_yd: Optional[int] = None,
        jo: Optional[str] = None,
        chr_cls_cd: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve full law content by effective date (시행일 기준 법령 본문 조회).

        Retrieves the complete text of a law organized by effective date.
        Use this to get the full content of a specific law.

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST/lsi_seq)
            ef_yd: Effective date (YYYYMMDD) - required when using mst
            jo: Article number in XXXXXX format (first 4 digits = article number zero-padded,
                last 2 digits = branch article suffix where 00=main article).
                Examples: "000200" (Article 2), "002000" (Article 20), "001502" (Article 15-2)
            chr_cls_cd: Language code - "010202" (Korean, default) or "010201" (Original)
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

        Returns:
            Full law content or error

        Examples:
            Retrieve law by ID:
            >>> eflaw_service(id="1747", type="XML")

            Retrieve law by MST with effective date:
            >>> eflaw_service(mst="166520", ef_yd=20151007, type="XML")

            Retrieve specific article:
            >>> eflaw_service(mst="166520", ef_yd=20151007, jo="000300", type="XML")
        """
        try:
            # Convert id/mst to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)

            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = config.oc if config else None

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
    @server.tool()
    def law_service(
        id: Optional[Union[str, int]] = None,
        mst: Optional[Union[str, int]] = None,
        lm: Optional[str] = None,
        ld: Optional[int] = None,
        ln: Optional[int] = None,
        jo: Optional[str] = None,
        lang: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Retrieve full law content by announcement date (공포일 기준 법령 본문 조회).

        Retrieves the complete text of a law organized by announcement (publication) date.

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            lm: Law modification parameter
            ld: Law date parameter (YYYYMMDD)
            ln: Law number parameter
            jo: Article number in XXXXXX format (first 4 digits = article number zero-padded,
                last 2 digits = branch article suffix where 00=main article).
                Examples: "000200" (Article 2), "002000" (Article 20), "001502" (Article 15-2)
            lang: Language - "KO" (Korean) or "ORI" (Original)
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

        Returns:
            Full law content or error

        Examples:
            Retrieve law by ID:
            >>> law_service(id="009682", type="XML")

            Retrieve law by MST:
            >>> law_service(mst="261457", type="XML")
        """
        try:
            # Convert id/mst to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)

            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = config.oc if config else None

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
    @server.tool()
    def eflaw_josub(
        id: Optional[str] = None,
        mst: Optional[str] = None,
        ef_yd: Optional[int] = None,
        jo: Optional[str] = None,
        hang: Optional[str] = None,
        ho: Optional[str] = None,
        mok: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Query specific article/paragraph by effective date (시행일 기준 조·항·호·목 조회).

        Retrieves specific sections (article, paragraph, item, subitem) of a law
        organized by effective date.

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            ef_yd: Effective date (YYYYMMDD) - required when using mst
            jo: Article number in XXXXXX format (first 4 digits = article number zero-padded,
                last 2 digits = branch article suffix where 00=main article).
                Examples: "000200" (Article 2), "002000" (Article 20), "001502" (Article 15-2)
            hang: Paragraph number (6 digits, e.g., "000100")
            ho: Item number (6 digits, e.g., "000200")
            mok: Subitem (UTF-8 encoded, e.g., "다")
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

        Returns:
            Specific law section content or error

        Examples:
            Query article/paragraph/item/subitem:
            >>> eflaw_josub(
            ...     mst="193412",
            ...     ef_yd=20171019,
            ...     jo="000300",
            ...     hang="000100",
            ...     ho="000200",
            ...     mok="다",
            ...     type="XML"
            ... )
        """
        try:
            # Convert id/mst to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)

            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = config.oc if config else None

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
    @server.tool()
    def law_josub(
        id: Optional[str] = None,
        mst: Optional[str] = None,
        jo: Optional[str] = None,
        hang: Optional[str] = None,
        ho: Optional[str] = None,
        mok: Optional[str] = None,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,
    ) -> dict:
        """
        Query specific article/paragraph by announcement date (공포일 기준 조·항·호·목 조회).

        Retrieves specific sections (article, paragraph, item, subitem) of a law
        organized by announcement (publication) date.

        Args:
            id: Law ID (either id or mst is required)
            mst: Law serial number (MST)
            jo: Article number in XXXXXX format (first 4 digits = article number zero-padded,
                last 2 digits = branch article suffix where 00=main article).
                Examples: "000200" (Article 2), "002000" (Article 20), "001502" (Article 15-2)
            hang: Paragraph number (6 digits, e.g., "000100")
            ho: Item number (6 digits, e.g., "000200")
            mok: Subitem (UTF-8 encoded, e.g., "다")
            oc: Optional OC override (defaults to session config or env)
            type: Response format - "HTML" or "XML" (default "XML", JSON not supported by API)

        Returns:
            Specific law section content or error

        Examples:
            Query article/paragraph/item/subitem:
            >>> law_josub(
            ...     id="001823",
            ...     jo="000300",
            ...     hang="000100",
            ...     ho="000200",
            ...     mok="다",
            ...     type="XML"
            ... )
        """
        try:
            # Convert id/mst to strings if they're integers (LLMs may extract numbers as ints)
            if id is not None:
                id = str(id)
            if mst is not None:
                mst = str(mst)

            # Access session config from Context at REQUEST time
            config = ctx.session_config if ctx else None
            session_oc = config.oc if config else None

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
    @server.tool()
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
            display: Number of results per page (max 100, default 20)
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
            session_oc = config.oc if config else None

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

            # Call API
            client = _get_client()
            return client.get("/DRF/lawSearch.do", upstream_params, response_type=type)

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
    @server.tool()
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
            session_oc = config.oc if config else None

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
    @server.tool()
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
            display: Number of results per page (max 100, default 20)
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
            session_oc = config.oc if config else None

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

            # Call API
            client = _get_client()
            return client.get("/DRF/lawSearch.do", upstream_params, response_type=type)

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
    @server.tool()
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
            session_oc = config.oc if config else None

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
    @server.tool()
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
            display: Number of results per page (max 100, default 20)
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
            session_oc = config.oc if config else None

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
            return client.get("/DRF/lawSearch.do", upstream_params, response_type=type)

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
    @server.tool()
    def lnkLsOrdJo_search(
        query: str = "*",
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        knd: Optional[str] = None,
        jo: Optional[int] = None,
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
            display: Number of results per page (max 100, default 20)
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
            session_oc = config.oc if config else None

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
            return client.get("/DRF/lawSearch.do", upstream_params, response_type=type)

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
    @server.tool()
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
            display: Number of results per page (max 100, default 20)
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
            session_oc = config.oc if config else None

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
            return client.get("/DRF/lawSearch.do", upstream_params, response_type=type)

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
    @server.tool()
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
            session_oc = config.oc if config else None

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
    @server.tool()
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
            session_oc = config.oc if config else None

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

    logger.info("LexLink server initialized with 15 tools")
    logger.info("Tools: eflaw_search, law_search, eflaw_service, law_service, eflaw_josub, law_josub")
    logger.info("       elaw_search, elaw_service, admrul_search, admrul_service")
    logger.info("       lnkLs_search, lnkLsOrdJo_search, lnkDep_search, drlaw_search, lsDelegated_service")
    logger.info(f"Session config: {session_config is not None}")

    return server
