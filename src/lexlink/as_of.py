"""Pure helpers for ``law_as_of``: date normalization and 'version in force on D'.

law.go.kr has no 'in force on day D' query. ``eflaw`` lists one row per
(법령일련번호 MST, 시행일자); a single MST can carry several 시행일자 (staged
enforcement) and ``lawService target=eflaw`` returns a different body per
(MST, efYd) pair. The version in force on D is therefore the candidate with the
largest 시행일자 <= D (ties: latest 공포일자 / 공포번호 / MST).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Iterable, Optional, Union

_DATE_RE = re.compile(
    r"^\s*(\d{4})\s*(?:[-./]|년)\s*(\d{1,2})\s*(?:[-./]|월)\s*(\d{1,2})\s*(?:일)?\s*\.?\s*$"
)


def normalize_as_of(value: Union[str, int, None]) -> str:
    """Return ``YYYYMMDD`` for 2016-05-03, 2016.5.3., 2016/5/3, 20160503, 2016년 5월 3일.

    Raises ValueError for anything else, including impossible dates (20160231).
    """
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        raise ValueError("as_of (기준일) is required, e.g. '2016-05-03' or '20160503'.")
    text = str(value).strip()
    if re.fullmatch(r"\d{8}", text):
        y, m, d = int(text[:4]), int(text[4:6]), int(text[6:])
    else:
        mt = _DATE_RE.match(text)
        if not mt:
            raise ValueError(
                f"Invalid as_of date: {value!r} (expected YYYYMMDD, YYYY-MM-DD or YYYY.M.D.)"
            )
        y, m, d = (int(g) for g in mt.groups())
    try:
        parsed = date(y, m, d)
    except ValueError:
        raise ValueError(f"Invalid as_of date: {value!r} (no such calendar date)") from None
    if parsed.year < 1900:
        raise ValueError(f"as_of year must be >= 1900, got {value!r}")
    return parsed.strftime("%Y%m%d")


def day_before(yyyymmdd: str) -> str:
    return (date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:])) - timedelta(days=1)).strftime("%Y%m%d")


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _order_key(c: dict) -> tuple:
    row = c["row"]
    return (c["effective_date"], row.get("공포일자", "") or "", _int(row.get("공포번호")), _int(c["mst"]))


def build_candidates(rows: Iterable[dict]) -> list[dict]:
    """One candidate per distinct (MST, 시행일자), oldest first."""
    seen: dict[tuple, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        mst = str(row.get("법령일련번호", "") or "")
        eff = str(row.get("시행일자", "") or "")
        if not mst or not re.fullmatch(r"\d{8}", eff):
            continue
        seen.setdefault((mst, eff), {"mst": mst, "effective_date": eff, "row": row})
    return sorted(seen.values(), key=_order_key)


def is_repeal(row: dict) -> bool:
    return "폐지" in (row.get("제개정구분명", "") or "")


def select_as_of(cands: list[dict], d: str) -> dict:
    """Pick the candidate in force on ``d`` (YYYYMMDD).

    Returns ``{"outcome", "selected", "same_day", "previous", "next"}`` with outcome one of
    ``in_force`` | ``before_first_version`` | ``repealed``.
    """
    if not cands:
        return {"outcome": "before_first_version", "selected": None, "same_day": [], "previous": None, "next": None}
    past = [c for c in cands if c["effective_date"] <= d]
    if not past:
        return {"outcome": "before_first_version", "selected": None, "same_day": [],
                "previous": None, "next": cands[0]}
    selected = past[-1]
    same_day = [c for c in past if c["effective_date"] == selected["effective_date"] and c is not selected]
    idx = cands.index(selected)
    after = [c for c in cands[idx + 1:] if c["effective_date"] > selected["effective_date"]]
    before = [c for c in cands[:idx] if c["effective_date"] < selected["effective_date"]]
    outcome = "repealed" if is_repeal(selected["row"]) else "in_force"
    return {
        "outcome": outcome,
        "selected": selected,
        "same_day": same_day,
        "previous": before[-1] if before else None,
        "next": after[0] if after else None,
    }


def describe(c: Optional[dict]) -> Optional[dict]:
    """Compact version record for a candidate."""
    if not c:
        return None
    row = c["row"]
    return {
        "mst": c["mst"],
        "effective_date": c["effective_date"],
        "announced_date": row.get("공포일자", ""),
        "announcement_no": row.get("공포번호", ""),
        "revision_type": row.get("제개정구분명", ""),
        "status": row.get("현행연혁코드", ""),
    }
