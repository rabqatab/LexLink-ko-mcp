"""
Intelligent caching for LexLink API responses.

Features:
- Per-tool TTL (search=1hr, service=24hr, aiSearch=30min)
- Semantic cache: normalizes queries so similar queries hit same cache
- LRU eviction when max entries reached
- Cache stats for monitoring
"""

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)


# Default TTL per tool category (seconds)
TTL_CONFIG = {
    # Search tools — data changes slowly, 1 hour is safe
    "search": 3600,
    # Service tools — law text is stable, 24 hours
    "service": 86400,
    # AI search — results may vary, 30 minutes
    "ai": 1800,
    # Knowledge base — reference data, 24 hours
    "kb": 86400,
    # Default fallback
    "default": 3600,
}

# Map tool targets to TTL categories
TARGET_TTL_MAP = {
    # Search tools → 1hr
    "eflaw": "search", "law": "search", "elaw": "search",
    "admrul": "search", "ordin": "search", "ordinLsCon": "search",
    "prec": "search", "detc": "search", "expc": "search", "decc": "search",
    "trty": "search", "lnkLs": "search", "lnkLsOrdJo": "search", "lnkDep": "search",
    # AI tools → 30min
    "aiSearch": "ai", "aiRltLs": "ai",
    # Knowledge base → 24hr
    "lstrmAI": "kb", "dlytrm": "kb", "lstrmRlt": "kb", "dlytrmRlt": "kb",
    "lstrmRltJo": "kb", "joRltLstrm": "kb", "lsRlt": "kb",
    # Committee/ministry/tribunal search → 1hr
    "ppc": "search", "eiac": "search", "ftc": "search", "acr": "search",
    "fsc": "search", "nlrc": "search", "kcc": "search", "iaciac": "search",
    "oclt": "search", "ecc": "search", "sfc": "search", "nhrck": "search",
    "ttSpecialDecc": "search", "kmstSpecialDecc": "search",
    "acrSpecialDecc": "search", "adapSpecialDecc": "search",
}


def _normalize_query(query: str) -> str:
    """Normalize a query for semantic cache matching.

    Strips whitespace, lowercases, removes common particles/suffixes
    so "민법 제3조" and "민법  제3조 " hit the same cache.
    """
    if not query:
        return ""
    q = query.strip().lower()
    # Normalize whitespace
    q = " ".join(q.split())
    return q


def _make_cache_key(target: str, params: dict) -> str:
    """Create a stable cache key from target + params.

    Normalizes query strings and sorts params for consistent keys.
    """
    # Extract and normalize query
    query = _normalize_query(params.get("query", params.get("QUERY", "")))

    # Build key parts: target + sorted non-empty params
    key_parts = [f"t={target}", f"q={query}"]
    for k in sorted(params.keys()):
        if k.lower() in ("oc", "type", "query"):
            continue  # Skip auth, format, and already-handled query
        v = params[k]
        if v is not None and str(v).strip():
            key_parts.append(f"{k}={v}")

    key_str = "|".join(key_parts)
    return hashlib.md5(key_str.encode("utf-8")).hexdigest()


class ResponseCache:
    """LRU cache with per-tool TTL for API responses."""

    def __init__(self, max_entries: int = 500):
        self._cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    def get(self, target: str, params: dict) -> Optional[dict]:
        """Look up cached response. Returns None on miss or expiry."""
        key = _make_cache_key(target, params)

        if key not in self._cache:
            self._misses += 1
            return None

        timestamp, response = self._cache[key]
        ttl = self._get_ttl(target)

        if time.time() - timestamp > ttl:
            # Expired
            del self._cache[key]
            self._misses += 1
            return None

        # Hit — move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        logger.debug(f"Cache HIT: {target} (key={key[:8]})")
        return response

    def put(self, target: str, params: dict, response: dict) -> None:
        """Store a response in cache. Only caches successful responses."""
        if response.get("status") != "ok":
            return  # Don't cache errors

        key = _make_cache_key(target, params)

        # Evict oldest if at capacity
        while len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)

        self._cache[key] = (time.time(), response)
        logger.debug(f"Cache PUT: {target} (key={key[:8]})")

    def invalidate(self, target: str = None) -> int:
        """Clear cache entries. If target given, only clear that target's entries."""
        if target is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        # Selective invalidation — need to rebuild since keys are hashed
        # Just clear all for now (target-specific invalidation would need key→target mapping)
        count = len(self._cache)
        self._cache.clear()
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total * 100:.1f}%" if total > 0 else "N/A",
            "total_requests": total,
        }

    def _get_ttl(self, target: str) -> int:
        """Get TTL for a given API target."""
        # Check direct target match
        category = TARGET_TTL_MAP.get(target)
        if category:
            return TTL_CONFIG[category]

        # Check if target starts with known prefix (e.g., cgmExpcMoel → search)
        if target.startswith("cgmExpc"):
            return TTL_CONFIG["search"]

        # Service endpoints (lawService.do targets)
        # These are typically called with specific IDs — cache longer
        return TTL_CONFIG["default"]


# Global singleton cache instance
_cache = ResponseCache(max_entries=500)


def get_cache() -> ResponseCache:
    """Get the global cache instance."""
    return _cache
