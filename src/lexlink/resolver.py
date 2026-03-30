"""
Law name resolution for LexLink.

Dynamically resolves Korean law abbreviations and aliases to canonical names.
Unlike hardcoded alias tables, this resolver builds its knowledge from
actual API responses — learning new abbreviations as they appear.

Features:
- Seed aliases from SERVER_INSTRUCTIONS embedded law IDs
- Dynamic learning from eflaw_search/law_search response 법령약칭명 field
- Typo correction (common Korean input errors)
- Partial matching for short queries
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# Common Korean typo corrections in legal context
TYPO_CORRECTIONS = {
    # Keyboard layout errors (ㅂ/ㅃ, ㅈ/ㅉ, etc.)
    "벚": "법",
    "셰": "세",
    "괸": "관",
    "겅": "경",
    "곤": "공",
    "겨": "경",
    # Common misspellings
    "기본법": "기본법",  # identity — just for completeness
}

# Seed abbreviations (from SERVER_INSTRUCTIONS + common usage)
# Format: abbreviation → full name
SEED_ALIASES = {
    # 6-code laws from SERVER_INSTRUCTIONS
    "민법": "민법",
    "형법": "형법",
    "상법": "상법",
    "헌법": "대한민국헌법",
    "민소법": "민사소송법",
    "형소법": "형사소송법",
    "행소법": "행정소송법",
    "행절법": "행정절차법",
    "국기법": "국세기본법",
    "소득세법": "소득세법",
    "법인세법": "법인세법",
    "근기법": "근로기준법",
    "근로기준법": "근로기준법",
    "건축법": "건축법",
    "자본시장법": "자본시장과 금융투자업에 관한 법률",
    "자통법": "자본시장과 금융투자업에 관한 법률",
    "국토계획법": "국토의 계획 및 이용에 관한 법률",
    "도교법": "도로교통법",
    "도로교통법": "도로교통법",
    "개보법": "개인정보 보호법",
    "개인정보보호법": "개인정보 보호법",
    "부동산공시법": "부동산 가격공시에 관한 법률",
    "민집법": "민사집행법",
    "특가법": "특정범죄 가중처벌 등에 관한 법률",
    # Common additional abbreviations
    "산안법": "산업안전보건법",
    "중대재해법": "중대재해 처벌 등에 관한 법률",
    "전금법": "전자금융거래법",
    "정통망법": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "전상법": "전자상거래 등에서의 소비자보호에 관한 법률",
    "약관법": "약관의 규제에 관한 법률",
    "여전법": "여신전문금융업법",
    "전서법": "전자서명법",
    "화관법": "화학물질관리법",
    "화평법": "화학물질의 등록 및 평가 등에 관한 법률",
    "주임법": "주택임대차보호법",
    "상임법": "상가건물 임대차보호법",
    "가사소송법": "가사소송법",
    "부정경쟁방지법": "부정경쟁방지 및 영업비밀보호에 관한 법률",
    "독점규제법": "독점규제 및 공정거래에 관한 법률",
    "공정거래법": "독점규제 및 공정거래에 관한 법률",
    "대외무역법": "대외무역법",
    "관세법": "관세법",
    "외환법": "외국환거래법",
    "외국환거래법": "외국환거래법",
    "전기통신사업법": "전기통신사업법",
    "병역법": "병역법",
    "군형법": "군형법",
    "의료법": "의료법",
    "약사법": "약사법",
    "식품위생법": "식품위생법",
    "환경법": "환경정책기본법",
    "AI기본법": "인공지능산업 육성 및 신뢰 기반 조성 등에 관한 법률",
}


class LawNameResolver:
    """Resolves law abbreviations and aliases to canonical names.

    Combines seed aliases with dynamically learned mappings from API responses.
    """

    def __init__(self):
        # abbreviation → full_name (lowercase keys for matching)
        self._aliases: dict[str, str] = {}
        # full_name → law_id (for direct ID lookup)
        self._name_to_id: dict[str, str] = {}
        # Load seed aliases
        for abbrev, full in SEED_ALIASES.items():
            self._aliases[abbrev.lower().strip()] = full

    def resolve(self, query: str) -> str:
        """Resolve a query to its canonical law name.

        Returns the resolved name if found, otherwise returns the original query.

        Args:
            query: Law name or abbreviation (e.g., "자통법", "개보법", "민법")

        Returns:
            Canonical law name (e.g., "자본시장과 금융투자업에 관한 법률")
        """
        if not query or query.strip() == "*":
            return query

        q = query.strip()

        # Step 1: Apply typo corrections
        corrected = self._correct_typos(q)

        # Step 2: Exact alias match (case-insensitive)
        key = corrected.lower()
        if key in self._aliases:
            resolved = self._aliases[key]
            if resolved != corrected:
                logger.debug(f"Resolved alias: '{query}' → '{resolved}'")
            return resolved

        # Step 3: Check if query ends with common suffixes and try without
        # e.g., "근기법 시행령" → resolve "근기법" then append " 시행령"
        for suffix in (" 시행령", " 시행규칙", " 시행세칙"):
            if q.endswith(suffix):
                base = q[:-len(suffix)]
                base_key = base.lower().strip()
                if base_key in self._aliases:
                    resolved = self._aliases[base_key] + suffix
                    logger.debug(f"Resolved with suffix: '{query}' → '{resolved}'")
                    return resolved

        # No resolution found — return original
        return q

    def get_law_id(self, name: str) -> Optional[str]:
        """Get law ID for a resolved name, if known."""
        return self._name_to_id.get(name.strip())

    def learn_from_results(self, results: list[dict]) -> int:
        """Learn new abbreviations from API search results.

        Each result may contain 법령약칭명 (official abbreviation) and
        법령명한글 (full name). This method adds them to the alias map.

        Args:
            results: List of law dicts from search API

        Returns:
            Number of new aliases learned
        """
        learned = 0
        for law in results:
            full_name = law.get("법령명한글", "").strip()
            abbrev = law.get("법령약칭명")
            law_id = law.get("법령ID", "")

            if not full_name:
                continue

            # Learn full_name → ID mapping
            if law_id:
                self._name_to_id[full_name] = law_id

            # Learn abbreviation → full_name
            if abbrev and abbrev.strip() and abbrev != "None":
                abbrev = abbrev.strip()
                key = abbrev.lower()
                if key not in self._aliases:
                    self._aliases[key] = full_name
                    learned += 1
                    logger.debug(f"Learned alias: '{abbrev}' → '{full_name}'")

            # Also learn the full name as self-alias (for exact match)
            full_key = full_name.lower()
            if full_key not in self._aliases:
                self._aliases[full_key] = full_name

        if learned > 0:
            logger.info(f"Learned {learned} new law aliases (total: {len(self._aliases)})")
        return learned

    def _correct_typos(self, text: str) -> str:
        """Apply common Korean typo corrections."""
        result = text
        for wrong, right in TYPO_CORRECTIONS.items():
            if wrong in result:
                result = result.replace(wrong, right)
        return result

    @property
    def alias_count(self) -> int:
        return len(self._aliases)

    def stats(self) -> dict:
        return {
            "total_aliases": len(self._aliases),
            "seed_aliases": len(SEED_ALIASES),
            "learned_aliases": len(self._aliases) - len(SEED_ALIASES),
            "known_law_ids": len(self._name_to_id),
        }


# Global singleton
_resolver = LawNameResolver()


def get_resolver() -> LawNameResolver:
    """Get the global law name resolver instance."""
    return _resolver
