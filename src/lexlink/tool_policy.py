"""Per-tool policy metadata (contract v1) published as MCP ``_meta["lexlink/policy"]``.

Every tool must have exactly one entry in ``TOOL_POLICIES``; ``create_server()`` refuses to
register a tool without one. The values come from reading each tool's code and measuring
live responses, and consumers use them to decide what to expose. The contract is described
in docs/API_REFERENCE.md ("도구 정책 메타데이터").

Rules used to fill the table:

* ``evidence``: ``primary`` = a response body that is the original statute or decision text
  as returned upstream (``*_service`` tools, ``*_josub``); ``derived`` = lists, indexes and
  anything upstream or LexLink edited (every ``*_search`` tool, because LexLink re-ranks and
  re-pages the rows; 신구조문표, diffs, version selection, citation extraction);
  ``heuristic`` = estimates, statistics and summaries; ``none`` = no legal content.
* ``size``: ``large`` when the usual response is about 50KB or more, or no argument can
  reduce it. A tool whose ``jo``/``sections``/``display`` control brings the response under
  50KB counts as ``normal`` and says so in ``notes``.
* ``upstream_calls``: the usual maximum number of law.go.kr requests per tool call (cold
  cache; anti-bot redirect hops and pagination beyond one page not counted). Larger caps
  are in ``notes``.
* ``may_expose_credential``: true only if a response can contain the OC after client redaction.
"""

from typing import Any, Optional

META_KEY = "lexlink/policy"
POLICY_VERSION = 1

CATEGORIES = frozenset({
    "law", "law_history", "law_compare", "admin_rule", "ordinance", "treaty", "precedent",
    "constitutional", "interpretation", "admin_appeal", "committee", "knowledge", "chain",
    "assist", "meta",
})
EVIDENCE = frozenset({"primary", "derived", "heuristic", "none"})
SIZES = frozenset({"normal", "large"})
FIELDS = frozenset({
    "version", "category", "evidence", "size", "upstream_calls", "may_expose_credential", "notes",
})
NOTES_MAX = 300


def validate_policy(policy: Any) -> dict:
    """Return ``policy`` if it satisfies contract v1, else raise ``ValueError``."""
    if not isinstance(policy, dict):
        raise ValueError("policy must be a dict")
    extra = set(policy) - FIELDS
    missing = (FIELDS - {"notes"}) - set(policy)
    if extra or missing:
        raise ValueError(f"policy fields: unexpected {sorted(extra)}, missing {sorted(missing)}")
    v = policy["version"]
    if type(v) is not int or v != POLICY_VERSION:
        raise ValueError(f"version must be {POLICY_VERSION}, got {v!r}")
    for key, allowed in (("category", CATEGORIES), ("evidence", EVIDENCE), ("size", SIZES)):
        if policy[key] not in allowed:
            raise ValueError(f"{key} must be one of {sorted(allowed)}, got {policy[key]!r}")
    n = policy["upstream_calls"]
    if type(n) is not int or n < 0:
        raise ValueError(f"upstream_calls must be a non-negative integer, got {n!r}")
    if type(policy["may_expose_credential"]) is not bool:
        raise ValueError("may_expose_credential must be a bool")
    if "notes" in policy:
        notes = policy["notes"]
        if not isinstance(notes, str) or not notes.strip() or len(notes) > NOTES_MAX:
            raise ValueError(f"notes must be a non-empty string of at most {NOTES_MAX} characters")
    return policy


def _p(category: str, evidence: str, size: str, upstream_calls: int,
       notes: Optional[str] = None, *, credential: bool = False) -> dict:
    policy = {
        "version": POLICY_VERSION,
        "category": category,
        "evidence": evidence,
        "size": size,
        "upstream_calls": upstream_calls,
        "may_expose_credential": credential,
    }
    if notes:
        policy["notes"] = notes
    return validate_policy(policy)


TOOL_POLICIES: dict[str, dict] = {
    # ---- 법령 ----
    "eflaw_search": _p("law", "derived", "normal", 1),
    "law_search": _p("law", "derived", "normal", 1),
    "eflaw_service": _p("law", "primary", "normal", 1,
                        "jo 없이 호출하면 법령 전체(민법 약 1.3MB). 조문 지정 시 수 KB"),
    "law_service": _p("law", "primary", "normal", 1,
                      "jo 없이 호출하면 법령 전체(민법 약 1.2MB). 조문 지정 시 수 KB"),
    "eflaw_josub": _p("law", "primary", "normal", 1),
    "law_josub": _p("law", "primary", "normal", 1),
    "elaw_search": _p("law", "derived", "normal", 1),
    "elaw_service": _p("law", "primary", "large", 1, "영문 법령 본문, 크기 제어 인자 없음(측정 77KB)"),
    "lsDelegated_service": _p("law", "primary", "large", 1, "위임 구조 전체, 법령별 17~392KB, 크기 제어 인자 없음"),
    "article_citation": _p("law", "derived", "normal", 3,
                           "인용 대상 확인 + lsiSeq 조회 + 조문 HTML 스크래핑, 1~3회"),
    "lsAbrv_search": _p("law", "derived", "normal", 1, "업스트림 2.3MB 목록을 서버가 걸러 요청한 페이지만 반환"),
    "licbyl_search": _p("law", "derived", "normal", 1, "별표서식 링크만 반환"),
    # ---- 행정규칙 ----
    "admrul_search": _p("admin_rule", "derived", "normal", 1),
    "admrul_service": _p("admin_rule", "primary", "normal", 1, "측정 2~33KB, 별표가 큰 규칙은 더 클 수 있음"),
    # ---- 자치법규 / 법령-자치법규 연계 ----
    "ordin_search": _p("ordinance", "derived", "normal", 1),
    "ordin_service": _p("ordinance", "primary", "large", 1, "측정 36~58KB, 크기 제어 인자 없음"),
    "ordinLsCon_search": _p("ordinance", "derived", "normal", 1),
    "lnkLs_search": _p("ordinance", "derived", "normal", 1),
    "lnkLsOrdJo_search": _p("ordinance", "derived", "normal", 1),
    "lnkDep_search": _p("ordinance", "derived", "normal", 1),
    "drlaw_search": _p("ordinance", "derived", "normal", 1,
                       "업스트림 HTML을 표로 파싱. 클라이언트가 OC를 제거하며 라이브에서 노출 미확인"),
    # ---- 조약 ----
    "trty_search": _p("treaty", "derived", "normal", 1),
    "trty_service": _p("treaty", "primary", "normal", 1, "측정 5~27KB"),
    # ---- 판례 / 헌재 / 해석 / 심판 / 위원회 ----
    "prec_search": _p("precedent", "derived", "normal", 1),
    "prec_service": _p("precedent", "primary", "normal", 1,
                       "전문 약 30KB, sections=summary 약 7KB. 본문 미제공 판례는 NOT_FOUND"),
    "detc_search": _p("constitutional", "derived", "normal", 1),
    "detc_service": _p("constitutional", "primary", "normal", 1),
    "expc_search": _p("interpretation", "derived", "normal", 1),
    "expc_service": _p("interpretation", "primary", "normal", 1),
    "cgm_expc_search": _p("interpretation", "derived", "normal", 1),
    "cgm_expc_service": _p("interpretation", "primary", "normal", 1),
    "decc_search": _p("admin_appeal", "derived", "normal", 1),
    "decc_service": _p("admin_appeal", "primary", "normal", 1),
    "special_decc_search": _p("admin_appeal", "derived", "normal", 1),
    "special_decc_service": _p("admin_appeal", "primary", "normal", 1),
    "committee_search": _p("committee", "derived", "normal", 1),
    "committee_service": _p("committee", "primary", "normal", 1),
    # ---- 지식베이스 ----
    "aiSearch": _p("knowledge", "derived", "normal", 1,
                   "조문 전문 포함, 측정 24~47KB(display=50이면 76KB)"),
    "aiRltLs_search": _p("knowledge", "derived", "normal", 1),
    "lstrm_ai_search": _p("knowledge", "derived", "normal", 1),
    "dlytrm_search": _p("knowledge", "derived", "normal", 1),
    "lstrm_rlt_search": _p("knowledge", "derived", "normal", 1),
    "dlytrm_rlt_search": _p("knowledge", "derived", "normal", 1),
    "lstrm_rlt_jo_search": _p("knowledge", "derived", "normal", 1),
    "jo_rlt_lstrm_search": _p("knowledge", "derived", "normal", 1),
    "ls_rlt_search": _p("knowledge", "derived", "normal", 1, "측정 4~49KB, 질의에 따라 50KB에 근접"),
    "lstrm_search": _p("knowledge", "derived", "normal", 1),
    "lstrm_service": _p("knowledge", "primary", "normal", 1),
    # ---- 연혁 / 시점 / 신구 / 3단 ----
    "law_as_of": _p("law_history", "derived", "normal", 5,
                    "조문 지정 4~5회(법령ID 지정 시 4), 동명 선행 법령 교체 시 최대 6, 기간 모드는 기간 내 개정본 수에 "
                    "비례(최대 12개), 부칙 확인용 전체 법령 조회 약 1MB"),
    "law_amendment_summary": _p("law_history", "derived", "normal", 2, "개정 이력이 100행을 넘으면 페이지당 1회 추가"),
    "article_amendment_diff": _p("law_history", "derived", "normal", 2, "LexLink가 계산한 비교, 원문 대조는 eflaw_service"),
    "oldAndNew_search": _p("law_history", "derived", "normal", 1),
    "oldAndNew_service": _p("law_history", "derived", "normal", 1, "가공물, 원문 대조는 eflaw_service/law_as_of"),
    "lsJoHstInf_search": _p("law_history", "derived", "large", 1,
                            "기본 display=20에서 측정 102KB. display를 8 이하로 줄이면 50KB 미만"),
    "lsHstInf_search": _p("law_history", "derived", "normal", 1, "기본 29KB, display=50이면 72KB"),
    "delHst_search": _p("law_history", "derived", "normal", 1),
    "thdCmp_search": _p("law_compare", "derived", "normal", 1),
    "thdCmp_service": _p("law_compare", "derived", "normal", 1,
                         "가공물. jo 없이 호출하면 측정 204KB(90~610KB), jo 지정 시 2~17KB"),
    # ---- 보조 / 추정 ----
    "check_precedent_odds": _p("assist", "heuristic", "normal", 7,
                               "주문 분포 추정, 승률 아님. 검색 최대 2회 + top_n건 본문 조회"),
    "legal_resolver": _p("assist", "heuristic", "normal", 8, "상황 -> 법령·판례·해석 묶음. 5~8회(조문 인용 포함)"),
    "simplify_article": _p("assist", "heuristic", "normal", 6,
                           "본문은 바꾸지 않고 용어 사전만 추가. 보통 3~6회, 용어 20개면 최대 42회"),
    # ---- 체인 ----
    "chain_full_research": _p("chain", "heuristic", "normal", 15, "legal_resolver + check_precedent_odds 묶음, 측정 13~15회"),
    "chain_amendment_track": _p("chain", "derived", "normal", 5, "연혁 100행 초과 시 페이지당 1회 추가"),
    "chain_dispute_prep": _p("chain", "derived", "normal", 8, "4개 출처, 결과가 적으면 출처마다 본문 검색 1회 추가(5~8회)"),
    "chain_law_system": _p("chain", "derived", "large", 3, "위임 구조 전체 포함(측정 32~154KB), 업스트림 응답 최대 3.8MB"),
    # ---- 메타 ----
    "cache_stats": _p("meta", "none", "normal", 0),
}


def policy_for(tool_name: str) -> dict:
    """Policy for ``tool_name``; ``KeyError`` with a fix hint if the tool has none."""
    try:
        return TOOL_POLICIES[tool_name]
    except KeyError:
        raise KeyError(
            f"tool {tool_name!r} has no entry in lexlink.tool_policy.TOOL_POLICIES "
            "(add one: see docs/DEVELOPMENT.md, 'Adding a tool')"
        ) from None


def policy_meta(tool_name: str) -> dict:
    """The ``meta=`` value to register ``tool_name`` with."""
    return {META_KEY: dict(policy_for(tool_name))}
