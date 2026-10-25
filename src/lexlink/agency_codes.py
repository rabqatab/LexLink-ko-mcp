"""
Agency code tables and pure helpers for ministry interpretations (중앙부처 1차 해석,
``{code}CgmExpc``) and special administrative appeals (특별행정심판, ``{code}SpecialDecc``).

Kept separate from server.py so the target-name construction and display
truncation logic can be unit-tested offline.

Upstream facts (verified 2026-10-25 against law.go.kr/DRF):
- List:  ``lawSearch.do?target=moelCgmExpc``  → root ``CgmExpc``, list key ``cgmExpc``,
  title field ``안건명``, serial field ``법령해석일련번호``.
- Text:  ``lawService.do?target=moelCgmExpc&ID=…`` → root ``CgmExpcService``.
- 재정경제부(Moef) and 국세청(Nts) expose the list API only; their full-text
  endpoint returns the upstream "미신청된 목록/본문" HTML page, and their list
  items link to taxlaw.nts.go.kr via ``법령해석상세링크``.
- Special appeals: ``lawSearch.do?target=ttSpecialDecc`` → root ``Decc``,
  list key ``decc``, title field ``사건명``.
"""

import json
from typing import Any, Optional

# Ministry name → target code (target = f"{code.lower()}CgmExpc").
# Names follow the current 정부조직 as listed in the law.go.kr Open API guide.
MINISTRY_CODES: dict[str, str] = {
    "고용노동부": "Moel", "국토교통부": "Molit", "재정경제부": "Moef",
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

# Former ministry names still accepted as input (→ canonical name).
MINISTRY_ALIASES: dict[str, str] = {
    "기획재정부": "재정경제부",
    "환경부": "기후에너지환경부",
    "산업통상자원부": "산업통상부",
    "여성가족부": "성평등가족부",
    "통계청": "국가데이터처",
    "특허청": "지식재산처",
    "문화재청": "국가유산청",
}

# Ministries whose full-text (Info) API is not provided upstream — list only.
MINISTRIES_LIST_ONLY: frozenset[str] = frozenset({"재정경제부", "국세청"})

# cgmExpc response shape
CGM_EXPC_LIST_KEY = "cgmExpc"
CGM_EXPC_TITLE_FIELD = "안건명"

# Special tribunal name → target code (target = f"{code}SpecialDecc").
TRIBUNAL_CODES: dict[str, str] = {
    "조세심판원": "tt",
    "해양안전심판원": "kmst",
    "국민권익위원회": "acr",
    "인사혁신처 소청심사위원회": "adap",
}

# specialDecc response shape
SPECIAL_DECC_LIST_KEY = "decc"
SPECIAL_DECC_TITLE_FIELD = "사건명"


def resolve_ministry(name: str) -> Optional[str]:
    """Return the canonical ministry name for ``name`` (accepts old names), or None."""
    if not name:
        return None
    name = name.strip()
    if name in MINISTRY_CODES:
        return name
    return MINISTRY_ALIASES.get(name)


def valid_ministry_names() -> str:
    """Comma-separated list of accepted canonical ministry names."""
    return ", ".join(MINISTRY_CODES.keys())


def cgm_expc_target(code: str) -> str:
    """Build the upstream target for a ministry code: ``Moel`` → ``moelCgmExpc``."""
    return f"{code.lower()}CgmExpc"


def special_decc_target(code: str) -> str:
    """Build the upstream target for a tribunal code: ``tt`` → ``ttSpecialDecc``."""
    return f"{code}SpecialDecc"


def _find_key(d: dict, key: str) -> Optional[str]:
    for k in d:
        if k.lower() == key.lower():
            return k
    return None


def enforce_display(response: dict, display: int, list_key: str) -> dict:
    """Guarantee a search response never carries more than ``display`` items.

    ``run_search`` over-fetches 100 rows for re-ranking. If ranking produced
    ``ranked_data`` this makes ``raw_content`` consistent with it; if ranking
    did not run (list key not found, etc.) it truncates the raw JSON list to
    ``display`` and exposes it as ``ranked_data``. XML/HTML bodies and error
    responses are returned unchanged.
    """
    if not isinstance(response, dict) or response.get("status") != "ok":
        return response
    raw = response.get("raw_content")
    if not isinstance(raw, str) or not raw.lstrip().startswith("{"):
        return response
    try:
        data = json.loads(raw)
    except ValueError:
        return response
    if not isinstance(data, dict) or not data:
        return response

    root_key = next(iter(data))
    root = data[root_key]
    if not isinstance(root, dict):
        return response

    display = max(int(display), 0)
    ranked = response.get("ranked_data")

    if isinstance(ranked, dict):
        # Ranking already trimmed; make raw_content agree with it.
        k = _find_key(ranked, list_key)
        if k is not None:
            items = ranked[k]
            if isinstance(items, dict):
                items = [items]
            if isinstance(items, list) and len(items) > display:
                ranked[k] = items[:display]
            ranked["display"] = str(display)
        response["raw_content"] = json.dumps({root_key: ranked}, ensure_ascii=False)
        return response

    # No ranked_data: truncate the raw list ourselves.
    k = _find_key(root, list_key)
    if k is None:
        return response
    items: Any = root[k]
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return response
    if len(items) > display:
        root[k] = items[:display]
        root["display"] = str(display)
        response["raw_content"] = json.dumps({root_key: root}, ensure_ascii=False)
    response["ranked_data"] = root
    return response
