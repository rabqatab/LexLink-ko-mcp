"""Per-tool policy metadata (contract v1) published as MCP ``_meta["lexlink/policy"]``.

Every tool must have exactly one entry in ``TOOL_POLICIES``; ``create_server()`` refuses to
register a tool without one. The values come from reading each tool's code and measuring
live responses, and consumers use them to decide what to expose. The contract is described
in docs/API_REFERENCE.md ("도구 정책 메타데이터").

Rules used to fill the table:

* ``evidence``: ``primary`` = the response's statute or decision text fields (조문 본문,
  판시사항, 법령명, ID, 날짜 ...) carry the upstream wording; in primary text LexLink may
  only tidy whitespace and join 조/항/호/목 units (``article_unit_text``), and never changes
  characters. Sorting, filtering, repaging, or LexLink-computed values in separate fields
  (``in_force``, flags, diffs) still count as primary. ``derived`` = the original wording
  itself is edited or reconstructed, so its characters may differ from the original
  (``oldAndNew_service``). ``heuristic`` = estimates, statistics, summaries. ``none`` = no
  legal content. A list/search tool is ``primary`` unless it rewrites wording
  (``elaw_search`` strips markup, ``drlaw_search`` rebuilds an HTML page as a table).
* ``size``: ``large`` = the representative measured size is about 100KB or more AND the
  provided controls (``jo``, ``sections``, ``display``, ``id`` ...) cannot bring it below
  that. A tool that is huge only when called without its control (``eflaw_service`` without
  ``jo``) is ``normal``; ``notes`` says what the control is and the measured range.
* ``upstream_calls``: the usual maximum number of law.go.kr requests per tool call for a
  typical law or query (cold cache). Anti-bot redirect hops are not counted; extra history
  pages on large laws and other larger caps are in ``notes``.
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
    "eflaw_search": _p("law", "primary", "normal", 1),
    "law_search": _p("law", "primary", "normal", 1),
    "eflaw_service": _p("law", "primary", "normal", 1, "jo 없이 호출하면 법령 전체(민법 1.28MB). jo 지정 시 2~4KB"),
    "law_service": _p("law", "primary", "normal", 1, "jo 없이 호출하면 법령 전체(민법 1.19MB). jo 지정 시 2~3KB"),
    "eflaw_josub": _p("law", "primary", "normal", 1),
    "law_josub": _p("law", "primary", "normal", 1),
    "elaw_search": _p("law", "derived", "normal", 1, "업스트림이 법령명에 넣은 강조 마크업을 제거함(문자가 원문과 다를 수 있음)"),
    "elaw_service": _p("law", "primary", "large", 1, "영문 법령 본문, 크기 제어 없음. 측정 77KB, 상법 1.1MB"),
    "lsDelegated_service": _p("law", "primary", "large", 1, "크기 제어 없음. 측정 민법 17KB, 법령ID 000900 392KB, 건축법 3.9MB(업스트림 3.69MB)"),
    "article_citation": _p("law", "derived", "normal", 3, "인용 대상 확인 + lsiSeq 조회 + 조문 HTML 스크래핑, 1~3회. 스크래핑으로 재구성한 인용 목록"),
    "lsAbrv_search": _p("law", "primary", "normal", 1, "업스트림 2.3MB 목록을 서버가 걸러 요청한 페이지만 반환"),
    "licbyl_search": _p("law", "primary", "normal", 1, "별표서식 링크만 반환"),
    "admrul_search": _p("admin_rule", "primary", "normal", 1),
    "admrul_service": _p("admin_rule", "primary", "normal", 1, "측정 1.4~122KB(표본 소수), 크기 제어 없음"),
    "ordin_search": _p("ordinance", "primary", "normal", 1),
    "ordin_service": _p("ordinance", "primary", "normal", 1, "측정 44건(직접 36 + 검토자 8) 중앙값 약 18KB, 범위 1.7~292KB, 100KB 이상 6건(대도시 도시계획·건축 조례). 크기 제어 없음"),
    "ordinLsCon_search": _p("ordinance", "primary", "normal", 1),
    "lnkLs_search": _p("ordinance", "primary", "normal", 1),
    "lnkLsOrdJo_search": _p("ordinance", "primary", "normal", 1),
    "lnkDep_search": _p("ordinance", "primary", "normal", 1),
    "drlaw_search": _p("ordinance", "derived", "normal", 1, "업스트림 HTML에 OC가 포함될 수 있고 클라이언트가 제거함(may_expose_credential=false는 이 제거에 의존). HTML을 표로 재구성"),
    "trty_search": _p("treaty", "primary", "normal", 1),
    "trty_service": _p("treaty", "primary", "normal", 1, "측정 5KB~약 970KB(id 7297), 중앙값 약 50KB, 크기 제어 없음"),
    "prec_search": _p("precedent", "primary", "normal", 1),
    "prec_service": _p("precedent", "primary", "normal", 1, "전문 측정 10~30KB, sections=summary 3~7.5KB. 본문 미제공 판례는 NOT_FOUND"),
    "detc_search": _p("constitutional", "primary", "normal", 1),
    "detc_service": _p("constitutional", "primary", "normal", 1),
    "expc_search": _p("interpretation", "primary", "normal", 1),
    "expc_service": _p("interpretation", "primary", "normal", 1),
    "cgm_expc_search": _p("interpretation", "primary", "normal", 1),
    "cgm_expc_service": _p("interpretation", "primary", "normal", 1),
    "decc_search": _p("admin_appeal", "primary", "normal", 1),
    "decc_service": _p("admin_appeal", "primary", "normal", 1),
    "special_decc_search": _p("admin_appeal", "primary", "normal", 1),
    "special_decc_service": _p("admin_appeal", "primary", "normal", 1),
    "committee_search": _p("committee", "primary", "normal", 1),
    "committee_service": _p("committee", "primary", "normal", 1, "크기 제어 없음. 대부분 45KB 이하, 공정거래위원회 사건은 50~345KB"),
    "aiSearch": _p("knowledge", "primary", "normal", 1, "조문 전문 포함. 기본 측정 24~47KB(3개 질의), display=50은 174~351KB"),
    "aiRltLs_search": _p("knowledge", "primary", "normal", 1),
    "lstrm_ai_search": _p("knowledge", "primary", "normal", 1),
    "dlytrm_search": _p("knowledge", "primary", "normal", 1),
    "lstrm_rlt_search": _p("knowledge", "primary", "normal", 1),
    "dlytrm_rlt_search": _p("knowledge", "primary", "normal", 1, "대체로 40KB 내외(직접 측정 9~97KB), 공무원은 약 207KB. trm_rlt_cd로 일부 축소 가능"),
    "lstrm_rlt_jo_search": _p("knowledge", "primary", "large", 1, "크기 제어 없음. 측정 계약 9.8MB, 보증 2.7MB, 손해배상 2.0MB, 선의 181KB"),
    "jo_rlt_lstrm_search": _p("knowledge", "primary", "normal", 1, "대부분 3~30KB, 소득세법 제12조는 약 390KB"),
    "ls_rlt_search": _p("knowledge", "primary", "normal", 1, "측정 4~49KB(3개 질의), 질의에 따라 더 클 수 있음"),
    "lstrm_search": _p("knowledge", "primary", "normal", 1),
    "lstrm_service": _p("knowledge", "primary", "normal", 1),
    "law_as_of": _p("law_history", "primary", "normal", 5, "조문 지정 4~5회(법령ID 지정 시 4). 대형 법령은 이력 페이지 추가로 최대 7회(건축법 6, 소득세법 7). 기간 모드는 개정본 수에 비례(최대 12개), 16~18회 측정. 부칙 확인용 전체 법령 조회 약 1MB"),
    "law_amendment_summary": _p("law_history", "primary", "normal", 2, "통상 2회, 대형 법령은 이력 페이지 추가로 2~4회"),
    "article_amendment_diff": _p("law_history", "primary", "normal", 2, "두 버전 조문은 원문, 비교(diff)는 LexLink 계산 필드"),
    "oldAndNew_search": _p("law_history", "primary", "normal", 1),
    "oldAndNew_service": _p("law_history", "derived", "normal", 1, "가공물, 원문 대조는 eflaw_service/law_as_of"),
    "lsJoHstInf_search": _p("law_history", "primary", "normal", 1, "id/display/jo로 줄임. reg_dt만 주면 기본 display=20에서 측정 97~141KB, id+기간 지정 시 40KB"),
    "lsHstInf_search": _p("law_history", "primary", "normal", 1, "기본 29KB, display=50이면 72KB"),
    "delHst_search": _p("law_history", "primary", "normal", 1),
    "thdCmp_search": _p("law_compare", "primary", "normal", 1),
    "thdCmp_service": _p("law_compare", "derived", "normal", 1, "jo 없이 호출하면 측정 89~610KB. jo 지정 시 대개 2~17KB, 건축법 제2조 약 158KB. eflaw_service와 개정 표기·따옴표 문자가 다름(14개 조문 중 8개)"),
    "check_precedent_odds": _p("assist", "heuristic", "normal", 7, "주문 분포 추정, 승률 아님. 검색 최대 2회 + top_n건 본문 조회"),
    "legal_resolver": _p("assist", "heuristic", "normal", 8, "상황 -> 법령·판례·해석 묶음. 5~8회(조문 인용 포함)"),
    "simplify_article": _p("assist", "heuristic", "normal", 6, "본문은 바꾸지 않고 용어 사전만 추가. 측정 3~6회, 용어 20개면 최대 42회"),
    "chain_full_research": _p("chain", "heuristic", "normal", 16, "legal_resolver + check_precedent_odds 묶음, 측정 13~16회"),
    "chain_amendment_track": _p("chain", "primary", "normal", 5, "대형 법령은 이력 페이지 추가로 최대 7회(건축법 6, 소득세법 7)"),
    "chain_dispute_prep": _p("chain", "primary", "normal", 8, "4개 출처, 결과가 적으면 출처마다 본문 검색 1회 추가(5~8회)"),
    "chain_law_system": _p("chain", "primary", "normal", 3, "크기 제어 없음. 측정 8건 4~154KB(4, 4, 32, 61, 80, 89, 124, 154), 중앙값 약 70KB. 업스트림 응답은 최대 3.8MB"),
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
