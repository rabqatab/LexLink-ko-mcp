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


REPEAL_KINDS = ("폐지", "타법폐지", "일괄폐지")


def is_repeal(row: dict) -> bool:
    """Exact repeal kinds only: '폐지제정' (repeal-and-re-enact) means enacted that day."""
    return (row.get("제개정구분명", "") or "").strip() in REPEAL_KINDS


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
        "law_name": row.get("법령명한글", ""),
        "effective_date": c["effective_date"],
        "announced_date": row.get("공포일자", ""),
        "announcement_no": row.get("공포번호", ""),
        "revision_type": row.get("제개정구분명", ""),
        "status": row.get("현행연혁코드", ""),
    }


# ---------------------------------------------------------------------------
# 삭제 articles
# ---------------------------------------------------------------------------

_DELETED_RE = re.compile(r"^\s*제\d+조(?:의\d+)?\s*(?:\([^)]*\)\s*)?삭제(?:\s*<[^>]*>)?\s*$")


def is_deleted_article(text: str) -> bool:
    """True when the article body is just '제N조 삭제 <date>' (a 삭제 placeholder)."""
    return bool(text) and bool(_DELETED_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# 부칙: article-level staged enforcement ("제55조제2항의 개정규정은 … 2021년 1월 1일부터")
# ---------------------------------------------------------------------------

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_KDATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_NEW_CHUNK_RE = re.compile(rf"^\s*(?:[{_CIRCLED}]|제\d+조(?:의\d+)?\s*[\(\s]|부칙)")


def _flatten_lines(content: Any) -> list[str]:
    """부칙내용 is a list of lists of strings, or its repr, or plain text."""
    if isinstance(content, str):
        text = content.strip()
        if text[:1] in "[(":
            import ast
            try:
                return _flatten_lines(ast.literal_eval(text))
            except (ValueError, SyntaxError):
                pass
        return [ln for ln in text.splitlines() if ln.strip()]
    if isinstance(content, (list, tuple)):
        out: list[str] = []
        for item in content:
            out.extend(_flatten_lines(item))
        return out
    return []


def bupchik_units(data: dict) -> list[dict]:
    """The 부칙단위 entries of a parsed lawService body ([] when absent)."""
    law = data.get("법령") if isinstance(data.get("법령"), dict) else data
    bup = law.get("부칙") if isinstance(law, dict) else None
    units = bup.get("부칙단위") if isinstance(bup, dict) else None
    if isinstance(units, dict):
        units = [units]
    return [u for u in (units or []) if isinstance(u, dict)]


_DATE_PATTERNS = (
    re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
    re.compile(r"(?<!\d)(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"),
)
_RANGE_RE = re.compile(r"제(\d+)조(?:의(\d+))?\s*부터\s*제(\d+)조(?:의(\d+))?\s*까지")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=시행하고,)\s*|(?<=시행하며,)\s*|(?<=시행하되,)\s*")
_SENT_SPLIT_RE =re.compile(r"(?<=다)\.\s+|(?:^|\s)다만,?\s*")


def _dates_in(text: str) -> set[str]:
    text = re.sub(r"<[^>]*>", " ", text)  # drop "<개정 2018.3.20>" style annotations
    found = set()
    for pat in _DATE_PATTERNS:
        for y, mo, dd in pat.findall(text):
            try:
                found.add(date(int(y), int(mo), int(dd)).strftime("%Y%m%d"))
            except ValueError:
                pass
    return found


def _names_article(sentence: str, article: int, branch: int, at_chunk_start: bool) -> bool:
    """True when ``sentence`` refers to this law's 제N조[의B] (alone or inside a 부터…까지 range)."""
    def other_law(prefix: str) -> bool:
        prefix = prefix.rstrip()
        if prefix.endswith(("」", "』", "부칙")):
            return True
        return prefix.endswith(("법", "법률", "령", "규칙")) and not prefix.endswith("이 법")

    for m in _RANGE_RE.finditer(sentence):
        if other_law(sentence[:m.start()]):
            continue
        lo = (int(m.group(1)), int(m.group(2) or 0))
        hi = (int(m.group(3)), int(m.group(4) or 0))
        if lo <= (article, branch) <= hi:
            return True
    ref = re.compile(rf"제{article}조" + (rf"의{branch}(?!\d)" if branch else r"(?!\d)(?!의\d)"))
    for m in ref.finditer(sentence):
        if at_chunk_start and m.start() == 0 and re.match(r"[\s(]", sentence[m.end():m.end() + 1] or " "):
            continue  # "제1조(시행일)": the 부칙's own article number
        if other_law(sentence[:m.start()]):
            continue
        return True
    return False


def scan_bupchik(units: list[dict], article: int, branch: int, d: str, limit: int = 5) -> list[dict]:
    """부칙 clauses that tie ``제N조[의B]`` of this law to a 시행 date later than ``d``.

    A chunk is one 항-sized passage (starts at ①.., 제N조, or a 부칙 header). Within it the
    sentence naming the article (alone or in a "제A조부터 제C조까지" range; not another law's
    article such as 「…법」 제4조, not the 부칙's own 제N조(...)) must contain '시행'. Only dates
    of that sentence count; when it says "각 호" the following item lines belong to it.
    Relative dates ("공포 후 6개월이 경과한 날") are not evaluated. Returns quoted text only.
    """
    hits: list[dict] = []
    for unit in units:
        lines = _flatten_lines(unit.get("부칙내용"))
        header = lines[0].strip() if lines and lines[0].lstrip().startswith("부칙") else ""
        chunks: list[list[str]] = []
        for ln in lines:
            if not chunks or _NEW_CHUNK_RE.match(ln):
                chunks.append([ln])
            else:
                chunks[-1].append(ln)
        for chunk in chunks:
            if "다음과 같이 개정한다" in "".join(chunk):
                continue
            for li, line in enumerate(chunk):
                sentences = [seg for sent_ in _SENT_SPLIT_RE.split(line.strip())
                             for seg in _CLAUSE_SPLIT_RE.split(sent_)]  # "…시행하고, …시행하며, …시행한다"
                for sent in sentences:
                    if "시행" not in sent or not _names_article(sent, article, branch, at_chunk_start=(li == 0)):
                        continue
                    clause = sent + ("\n" + "\n".join(s.strip() for s in chunk[li + 1:]) if "각 호" in sent else "")
                    later = sorted(x for x in _dates_in(clause) if x > d)
                    if later:
                        hits.append({"bupchik": header or unit.get("부칙공포번호", ""),
                                     "announced_date": unit.get("부칙공포일자", ""),
                                     "text": clause[:600], "later_dates": later})
                        if len(hits) >= limit:
                            return hits
    return hits


def expired_unknown(cands: list[dict]) -> bool:
    """True when upstream lists no 현행 / 시행예정 row and the last version is not a repeal.

    Such a law (한시법 expiry, partial data, ...) is not known to be in force today.
    """
    if not cands:
        return False
    statuses = {c["row"].get("현행연혁코드", "") for c in cands}
    return not (statuses & {"현행", "시행예정"}) and not is_repeal(cands[-1]["row"])
