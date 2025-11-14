"""
Parameter resolution and mapping for law.go.kr API.

This module handles:
1. OC parameter resolution from multiple sources (tool arg > session > env)
2. Parameter name mapping (snake_case → API format)
3. UTF-8 encoding for Korean parameters (MOK)
"""

import os
from typing import Optional
from urllib.parse import quote


def resolve_oc(
    override_oc: Optional[str] = None,
    session_oc: Optional[str] = None
) -> str:
    """
    Resolve OC parameter from multiple sources with priority order.

    Priority (highest to lowest):
    1. Tool argument override (passed explicitly in tool call)
    2. Session configuration (set in Smithery UI/URL)
    3. Environment variable LAW_OC

    Args:
        override_oc: Optional override from tool argument
        session_oc: Optional value from session configuration

    Returns:
        Resolved OC value

    Raises:
        ValueError: If OC cannot be resolved from any source, with helpful message

    Examples:
        >>> resolve_oc(override_oc="tool_value")
        'tool_value'

        >>> resolve_oc(session_oc="session_value")
        'session_value'

        >>> os.environ["LAW_OC"] = "env_value"
        >>> resolve_oc()
        'env_value'

        >>> resolve_oc()  # All sources empty
        ValueError: OC parameter is required but not provided...
    """
    # Priority 1: Tool argument override
    if override_oc and override_oc.strip():
        return override_oc.strip()

    # Priority 2: Session configuration
    if session_oc and session_oc.strip():
        return session_oc.strip()

    # Priority 3: Environment variable
    env_oc = os.getenv("LAW_OC", "").strip()
    if env_oc:
        return env_oc

    # Fail with helpful message
    raise ValueError(
        "OC parameter is required but not provided. "
        "Please provide it via:\n"
        "  1. Tool argument: oc='your_value' (highest priority)\n"
        "  2. Session config: Set 'oc' in Smithery settings\n"
        "  3. Environment variable: LAW_OC=your_value (fallback)\n"
        "\n"
        "OC should be your email local part (e.g., g4c@korea.kr → g4c)"
    )


def map_params_to_upstream(snake_params: dict) -> dict:
    """
    Convert snake_case tool parameters to law.go.kr API format.

    Mapping rules:
    - Most params: snake_case → camelCase (ef_yd → efYd)
    - Article params: UPPERCASE (jo → JO, hang → HANG, ho → HO, mok → MOK)
    - OC: Always uppercase (oc → OC)
    - Pass-through: query, display, page, sort, etc.

    Args:
        snake_params: Parameters from MCP tool (snake_case)

    Returns:
        Parameters ready for law.go.kr API (original format)

    Example:
        >>> map_params_to_upstream({
        ...     "oc": "g4c",
        ...     "ef_yd": "20240101~20241231",
        ...     "jo": "000300",
        ...     "query": "자동차관리법"
        ... })
        {
            "OC": "g4c",
            "efYd": "20240101~20241231",
            "JO": "000300",
            "query": "자동차관리법"
        }
    """
    # Define comprehensive mapping table
    PARAM_MAP = {
        # Session/auth (UPPERCASE)
        "oc": "OC",

        # Common search params (camelCase)
        "ef_yd": "efYd",      # 시행일자 범위
        "anc_yd": "ancYd",    # 공포일자 범위
        "anc_no": "ancNo",    # 공포번호 범위
        "prml_yd": "prmlYd",  # 발령일자 범위 (administrative rules)
        "mod_yd": "modYd",    # 수정일자 범위 (administrative rules)
        "rr_cls_cd": "rrClsCd",  # 제개정 종류 코드
        "pop_yn": "popYn",    # 팝업 여부
        "ls_chap_no": "lsChapNo",  # 법령체계 장번호
        "chr_cls_cd": "chrClsCd",  # 한글/원문 구분

        # Phase 3: Case Law & Legal Research (camelCase)
        "prnc_yd": "prncYd",  # 선고일자 기간 (precedent decision date range)
        "dat_src_nm": "datSrcNm",  # 데이터출처명 (data source name)
        "ed_yd": "edYd",      # 종국일자 기간 (constitutional final date range)
        "reg_yd": "regYd",    # 등록일자 기간 (interpretation registration date range)
        "expl_yd": "explYd",  # 해석일자 기간 (interpretation explanation date range)
        "dpa_yd": "dpaYd",    # 처분일자 기간 (appeal disposition date range)
        "rsl_yd": "rslYd",    # 의결일자 기간 (appeal resolution date range)

        # Service params (ID/MST uppercase per API convention)
        "id": "ID",
        "mst": "MST",

        # Article navigation (UPPERCASE)
        "jo": "JO",          # 조
        "jobr": "JOBR",      # 조 가지번호 (article branch number)
        "hang": "HANG",      # 항
        "ho": "HO",          # 호
        "mok": "MOK",        # 목 (requires UTF-8 encoding)

        # Pass-through (no change needed)
        "target": "target",
        "type": "type",
        "query": "query",
        "display": "display",
        "page": "page",
        "sort": "sort",
        "date": "date",
        "nb": "nb",          # 사건번호 (case number, also used in precedents/constitutional)
        "org": "org",
        "knd": "knd",
        "gana": "gana",      # 사전식 검색 (dictionary search)
        "search": "search",
        "nw": "nw",
        "ld": "ld",
        "ln": "ln",
        "lm": "lm",
        "lang": "lang",
        "lid": "LID",
        "curt": "curt",      # 법원명 (court name, precedents)
        "inq": "inq",        # 질의기관 (inquiry org, interpretations)
        "rpl": "rpl",        # 회신기관 (reply org, interpretations)
        "itmno": "itmno",    # 안건번호 (item number, interpretations)
        "cls": "cls",        # 재결례유형 (decision type, admin appeals)
    }

    upstream_params = {}

    for snake_key, value in snake_params.items():
        # Skip None or empty string values
        if value is None or value == "":
            continue

        # Get upstream key from mapping (default to original if not in map)
        upstream_key = PARAM_MAP.get(snake_key, snake_key)

        # Special handling for MOK (UTF-8 percent-encoding)
        if upstream_key == "MOK" and isinstance(value, str):
            upstream_params[upstream_key] = encode_mok(value)
        else:
            upstream_params[upstream_key] = value

    return upstream_params


def encode_mok(value: str) -> str:
    """
    UTF-8 percent-encode MOK parameter.

    Korean sub-item identifiers (가, 나, 다, 라, ...) must be
    UTF-8 encoded for the law.go.kr API.

    Args:
        value: Korean character for sub-item (e.g., "가", "나", "다")

    Returns:
        Percent-encoded string (e.g., "가" → "%EA%B0%80")

    Examples:
        >>> encode_mok("가")
        '%EA%B0%80'

        >>> encode_mok("나")
        '%EB%82%98'

        >>> encode_mok("다")
        '%EB%8B%A4'
    """
    # Encode to UTF-8 bytes, then percent-encode
    return quote(value.encode("utf-8"), safe="")
