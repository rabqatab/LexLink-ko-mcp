"""
Relevance ranking for search results from law.go.kr API.

The law.go.kr API returns results in various orders (often alphabetical),
which doesn't prioritize exact matches or relevance. This module provides
ranking logic to reorder results by relevance to the search query.
"""

from typing import List, Dict, Any


def rank_search_results(
    results: List[Dict[str, Any]],
    query: str,
    name_field: str
) -> List[Dict[str, Any]]:
    """
    Rank search results by relevance to query.

    Prioritizes results in this order:
    1. Exact matches (e.g., "민법" matches "민법")
    2. Starts with query (e.g., "민법" matches "민법 시행령")
    3. Contains query as whole word (with word boundaries)
    4. Contains query as substring (lowest priority)

    Within each priority level, results are sorted by length (shorter = more specific).

    Args:
        results: List of result dictionaries from API
        query: Search query string
        name_field: Field name to check for relevance (e.g., '법령명한글', '사건명')

    Returns:
        Re-ranked list of results with exact matches first

    Examples:
        Query "민법" returns:
        1. "민법" (exact match) - highest priority
        2. "민법 시행령" (starts with) - high priority
        3. "행정기본법 시행령" (contains as word) - medium priority
        4. "난민법" (alphabetical but not relevant) - lowest priority

        >>> results = [
        ...     {'법령명한글': '난민법'},
        ...     {'법령명한글': '민법'},
        ...     {'법령명한글': '민법 시행령'}
        ... ]
        >>> ranked = rank_search_results(results, "민법", "법령명한글")
        >>> [r['법령명한글'] for r in ranked]
        ['민법', '민법 시행령', '난민법']
    """
    if not results or not query:
        return results

    def calculate_score(result: Dict[str, Any]) -> tuple:
        """
        Calculate relevance score for a single result.

        Returns a tuple for sorting where lower values = higher priority.
        Python sorts tuples lexicographically (element by element).
        """
        name = result.get(name_field, '').strip()
        if not name:
            # Empty names go to the end
            return (999, 999, 999, 999, len(name))

        query_lower = query.lower().strip()
        name_lower = name.lower()

        # Score 1: Exact match (highest priority)
        # 0 = exact match, 1 = not exact match
        exact_match = 0 if name_lower == query_lower else 1

        # Score 2: Starts with query
        # 0 = starts with query, 1 = doesn't start with
        starts_with = 0 if name_lower.startswith(query_lower) else 1

        # Score 3: Query is a complete word/segment
        # For Korean, check if query appears at word boundaries
        if query_lower in name_lower:
            idx = name_lower.find(query_lower)
            # Check if it's at the start or has space before it
            is_word_boundary = (idx == 0 or name_lower[idx-1] == ' ')
            word_match = 0 if is_word_boundary else 1
        else:
            word_match = 1

        # Score 4: Contains query anywhere
        # 0 = contains query, 1 = doesn't contain
        contains = 0 if query_lower in name_lower else 1

        # Score 5: Length penalty (prefer shorter, more specific names)
        # Shorter names are generally more specific
        length_penalty = len(name)

        # Return tuple for sorting (all negated so lower = better)
        # Priority order: exact > starts > word > contains > shorter
        return (exact_match, starts_with, word_match, contains, length_penalty)

    # Sort by relevance score
    ranked_results = sorted(results, key=calculate_score)
    return ranked_results


def detect_query_language(query: str) -> str:
    """
    Detect if query is in Korean or English.

    Args:
        query: Search query string

    Returns:
        "korean" if query contains Korean characters (Hangul),
        "english" otherwise

    Examples:
        >>> detect_query_language("민법")
        'korean'
        >>> detect_query_language("insurance")
        'english'
        >>> detect_query_language("가정폭력방지")
        'korean'
    """
    if not query:
        return "english"

    # Check if any character is Hangul (Korean)
    # Hangul Unicode range: 0xAC00-0xD7A3 (syllables)
    # Also check Hangul Jamo: 0x1100-0x11FF, 0x3130-0x318F
    for char in query:
        code = ord(char)
        if (0xAC00 <= code <= 0xD7A3 or  # Hangul syllables
            0x1100 <= code <= 0x11FF or  # Hangul Jamo
            0x3130 <= code <= 0x318F):   # Hangul Compatibility Jamo
            return "korean"

    return "english"


def should_apply_ranking(query: str) -> bool:
    """
    Determine if ranking should be applied for a given query.

    Ranking is most useful for keyword searches. For wildcard or
    very short queries, alphabetical ordering may be acceptable.

    Args:
        query: Search query string

    Returns:
        True if ranking should be applied, False otherwise

    Examples:
        >>> should_apply_ranking("민법")
        True
        >>> should_apply_ranking("*")
        False
        >>> should_apply_ranking("a")  # Too short
        False
    """
    if not query or query.strip() == "":
        return False

    # Don't rank wildcard queries
    if query.strip() == "*":
        return False

    # Don't rank very short queries (1 character)
    # These may be intentionally broad searches
    if len(query.strip()) < 2:
        return False

    return True
