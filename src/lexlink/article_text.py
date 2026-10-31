"""
Article text extraction and law-version selection helpers (Phase 8/9).

Upstream shapes this module understands (verified against law.go.kr, 2026-10):

* ``lawService.do?target=law&MST=…&JO=003505`` (JSON) →
  ``{"법령": {"기본정보": {...}, "조문": {"조문단위": {...}}}}``
  where ``조문단위`` is a dict for a single article and a list for the whole law.
  ``조문내용`` holds only the heading (``제35조의5(저작물의 공정한 이용)``) when the
  article has paragraphs; the body lives in ``항`` → ``항내용`` / ``호`` → ``호내용``
  / ``목`` → ``목내용``. Articles without paragraphs carry the body inside
  ``조문내용`` itself. ``항`` may be a dict (single paragraph) or a list, and a
  paragraph can hold ``호`` without any ``항내용`` (definition-style articles).
  The same structure is returned as XML with ``type=XML``.

* ``lawSearch.do?target=eflaw`` rows carry ``현행연혁코드`` (현행/연혁/시행예정),
  ``법령일련번호`` (MST), ``법령ID``, ``공포일자``, ``공포번호``, ``시행일자``,
  ``제개정구분명``, ``법령구분명``. One MST may appear several times with different
  ``시행일자`` (staggered effective dates).

* ``lawService.do?target=lsJoHstInf&ID=…&JO=…`` → ``{"LawService": {"law": [...]}}``
  with per-article change history (``조문변경일``, ``변경사유``, ``법령일련번호``).

Nothing in here performs network I/O; the tools in ``server.py`` feed it the
``raw_content`` strings they get from the client.
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable, Optional, Union

from ._helpers import ToolValidationError, compact_limit
from .validation import format_article_number

__all__ = [
    "ArticleNotFoundError",
    "normalize_article",
    "article_label",
    "article_jo",
    "parse_law_payload",
    "find_article_units",
    "select_article_unit",
    "article_unit_text",
    "extract_article",
    "extract_article_text",
    "law_rows",
    "select_law_rows",
    "pick_current_version",
    "dedupe_versions",
    "revision_record",
    "previous_version",
    "parse_article_history",
    "today_str",
    "end_of_current_year",
    "strip_html",
    "compact_delegation_tree",
]

STATUS_CURRENT = "현행"
STATUS_HISTORY = "연혁"
STATUS_PENDING = "시행예정"

# Which row represents an MST when the same MST shows up with several 시행일자.
_DEDUPE_STATUS_RANK = {STATUS_CURRENT: 0, STATUS_PENDING: 1, STATUS_HISTORY: 2}

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)


class ArticleNotFoundError(ToolValidationError):
    """Raised when a law payload has no article text to extract."""


# ---------------------------------------------------------------------------
# Article number handling
# ---------------------------------------------------------------------------

def normalize_article(article: Union[int, str], article_branch: Union[int, str, None] = 0) -> tuple[int, int]:
    """Normalize an article reference to ``(article, branch)`` integers.

    Accepts ``35``, ``"35"``, ``"35의5"``, ``"제35조의5"``, ``"35-5"``, ``"003505"``
    (6-digit JO code) and a separate ``article_branch`` (int or str).
    """
    branch = _to_int(article_branch, "article_branch") if article_branch not in (None, "") else 0

    if isinstance(article, bool):  # bool is an int subclass; reject explicitly
        raise ValueError(f"Invalid article number: {article!r}")
    if isinstance(article, int):
        number = article
    else:
        text = str(article).strip()
        if not text:
            raise ValueError("Article number is empty")
        text = text.replace(" ", "")
        if re.fullmatch(r"\d{6}", text):
            number, code_branch = int(text[:4]), int(text[4:])
            branch = branch or code_branch
        else:
            m = re.fullmatch(r"(?:제)?(\d+)(?:조)?(?:(?:의|-)(\d+))?", text)
            if not m:
                raise ValueError(
                    f"Invalid article reference: {article!r} "
                    "(expected e.g. 35, '35의5', '제35조의5', '003505')"
                )
            number = int(m.group(1))
            if m.group(2):
                parsed_branch = int(m.group(2))
                if branch and branch != parsed_branch:
                    raise ValueError(
                        f"Conflicting branch numbers: {article!r} vs article_branch={branch}"
                    )
                branch = parsed_branch

    if not (1 <= number <= 9999):
        raise ValueError(f"Article number must be 1-9999, got: {number}")
    if not (0 <= branch <= 99):
        raise ValueError(f"Branch number must be 0-99, got: {branch}")
    return number, branch


def _to_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name}: {value!r}")
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError(f"Invalid {name}: {value!r}")
    return int(text)


def article_label(article: int, branch: int = 0) -> str:
    """``(35, 5)`` → ``제35조의5``; ``(35, 0)`` → ``제35조``."""
    return f"제{article}조" if not branch else f"제{article}조의{branch}"


def article_jo(article: Union[int, str], article_branch: Union[int, str, None] = 0) -> str:
    """Return the 6-digit JO code (``003505``) for any accepted article reference."""
    number, branch = normalize_article(article, article_branch)
    return format_article_number(number, branch)


# ---------------------------------------------------------------------------
# Payload parsing (JSON / XML → dict)
# ---------------------------------------------------------------------------

def parse_law_payload(raw: Union[str, bytes, dict, None], response_type: str = "JSON") -> dict:
    """Parse a ``lawService.do`` response body into a dict.

    ``raw`` may already be a dict (pass-through). XML is converted into the same
    nested shape the JSON API uses (repeated tags become lists).
    Returns ``{}`` for empty / unparsable input.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    text = raw.strip()
    if not text:
        return {}

    fmt = (response_type or "JSON").upper()
    if fmt != "XML" and text[0] in "{[":
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    if text.startswith("<"):
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return {}
        return {root.tag: _element_to_dict(root)}
    return {}


def _element_to_dict(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        text = (element.text or "").strip()
        if element.attrib:
            out: dict = dict(element.attrib)
            if text:
                out["content"] = text
            return out
        return text
    result: dict = dict(element.attrib)
    for child in children:
        value = _element_to_dict(child)
        if child.tag in result:
            existing = result[child.tag]
            if isinstance(existing, list):
                existing.append(value)
            else:
                result[child.tag] = [existing, value]
        else:
            result[child.tag] = value
    return result


# ---------------------------------------------------------------------------
# Locating and flattening 조문단위
# ---------------------------------------------------------------------------

def _as_list(value: Any) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def find_article_units(data: Any) -> list[dict]:
    """Return every ``조문단위`` dict found in a parsed law payload (possibly empty)."""
    units: list[dict] = []
    _collect_units(data, units, depth=0)
    return units


def _collect_units(obj: Any, out: list[dict], depth: int) -> None:
    if depth > 12:
        return
    if isinstance(obj, dict):
        if "조문단위" in obj:
            for unit in _as_list(obj["조문단위"]):
                if isinstance(unit, dict):
                    out.append(unit)
            return
        if "조문내용" in obj or "조문번호" in obj:
            out.append(obj)
            return
        for value in obj.values():
            if isinstance(value, (dict, list)):
                _collect_units(value, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _collect_units(item, out, depth + 1)


def select_article_unit(
    units: Iterable[dict],
    article: Optional[int] = None,
    branch: Optional[int] = None,
) -> Optional[dict]:
    """Pick the 조문단위 for ``article``/``branch`` (or the first real article)."""
    candidates = [u for u in units if isinstance(u, dict)]
    real = [u for u in candidates if u.get("조문여부", "조문") != "전문"] or candidates
    if article is None:
        return real[0] if real else None
    want_branch = int(branch or 0)
    for unit in real:
        if _unit_number(unit) == (int(article), want_branch):
            return unit
    return None


def _unit_number(unit: dict) -> tuple[Optional[int], int]:
    number = str(unit.get("조문번호", "")).strip()
    branch = str(unit.get("조문가지번호") or "").strip()
    try:
        n = int(number) if number else None
    except ValueError:
        n = None
    try:
        b = int(branch) if branch else 0
    except ValueError:
        b = 0
    return n, b


def _norm(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, list):
        return "\n".join(_norm(t) for t in text if _norm(t))
    if isinstance(text, dict):
        return _norm(text.get("content", ""))
    return _WS_RE.sub(" ", str(text)).strip()


def article_unit_text(unit: dict) -> str:
    """Flatten one 조문단위 into newline-separated text (heading, 항, 호, 목 in order)."""
    lines: list[str] = []

    def add(text: Any) -> None:
        for line in _norm(text).split("\n"):
            if line:
                lines.append(line)

    add(unit.get("조문내용"))
    for hang in _as_list(unit.get("항")):
        if not isinstance(hang, dict):
            add(hang)
            continue
        add(hang.get("항내용"))
        for ho in _as_list(hang.get("호")):
            if not isinstance(ho, dict):
                add(ho)
                continue
            add(ho.get("호내용"))
            for mok in _as_list(ho.get("목")):
                add(mok.get("목내용") if isinstance(mok, dict) else mok)
    # Some payloads hang 호 directly on the 조문단위.
    for ho in _as_list(unit.get("호")):
        if not isinstance(ho, dict):
            add(ho)
            continue
        add(ho.get("호내용"))
        for mok in _as_list(ho.get("목")):
            add(mok.get("목내용") if isinstance(mok, dict) else mok)
    return "\n".join(lines)


def _law_meta(data: dict) -> dict:
    """Pull 기본정보 fields (law name, MST dates) from a parsed payload."""
    info: dict = {}
    root = data.get("법령") if isinstance(data, dict) else None
    if not isinstance(root, dict):
        root = data if isinstance(data, dict) else {}
    basic = root.get("기본정보") if isinstance(root.get("기본정보"), dict) else {}
    if basic:
        info["law_name"] = _norm(basic.get("법령명_한글") or basic.get("법령명한글"))
        info["law_id"] = _norm(basic.get("법령ID"))
        info["announced"] = _norm(basic.get("공포일자"))
        info["announcement_no"] = _norm(basic.get("공포번호"))
        info["effective"] = _norm(basic.get("시행일자"))
        info["revision_type"] = _norm(basic.get("제개정구분"))
        law_type = basic.get("법종구분")
        info["law_type"] = _norm(law_type.get("content") if isinstance(law_type, dict) else law_type)
    return {k: v for k, v in info.items() if v}


def extract_article(
    raw: Union[str, bytes, dict, None],
    response_type: str = "JSON",
    article: Union[int, str, None] = None,
    article_branch: Union[int, str, None] = 0,
) -> dict:
    """Extract one article from a ``lawService.do`` payload.

    Returns ``{"text", "heading", "title", "article", "lines", "effective",
    "changed", "reference", "law": {...}}``.

    Raises ``ArticleNotFoundError`` (a ``ToolValidationError`` with hints) when the
    payload is empty, has no 조문단위, or the requested article is missing.
    """
    data = parse_law_payload(raw, response_type)
    wanted = normalize_article(article, article_branch) if article is not None else None
    label = article_label(*wanted) if wanted else "조문"

    if not data:
        raise ArticleNotFoundError(
            f"{label} 응답이 비어 있습니다 (upstream returned '{{}}' or non-JSON).",
            hints=[
                "MST(법령일련번호)가 올바른지, JO가 6자리(예: 003505)인지 확인하세요.",
                "한글 파라미터는 percent-encoding 되어야 합니다.",
                "lawService.do?target=law&MST=…&JO=… 형식을 사용하세요 (eflaw 본문 API는 미신청).",
            ],
        )

    units = find_article_units(data)
    meta = _law_meta(data)
    if not units:
        law_desc = meta.get("law_name", "")
        raise ArticleNotFoundError(
            f"{law_desc + ' ' if law_desc else ''}{label}: 이 법령 버전(MST)에 해당 조문이 없습니다.",
            hints=[
                "조문이 신설되기 전 버전이거나 삭제된 조문일 수 있습니다.",
                "law_amendment_summary로 다른 MST를 확인하거나 조문 번호/가지번호를 확인하세요.",
            ],
        )

    unit = select_article_unit(units, *(wanted or (None, None)))
    if unit is None:
        available = sorted({article_label(n, b) for n, b in (_unit_number(u) for u in units) if n})
        raise ArticleNotFoundError(
            f"{label}을(를) 응답에서 찾을 수 없습니다.",
            hints=[f"응답에 포함된 조문: {', '.join(available[:20])}"] if available else None,
        )

    text = article_unit_text(unit)
    if not text:
        raise ArticleNotFoundError(
            f"{label}의 본문이 비어 있습니다.",
            hints=["조문내용/항내용/호내용 키가 모두 비어 있습니다. 업스트림 응답을 확인하세요."],
        )

    number, branch = _unit_number(unit)
    return {
        "text": text,
        "heading": _norm(unit.get("조문내용")),
        "title": _norm(unit.get("조문제목")),
        "article": article_label(number, branch) if number else label,
        "lines": text.count("\n") + 1,
        "effective": _norm(unit.get("조문시행일자")),
        "changed": _norm(unit.get("조문변경여부")),
        "reference": _norm(unit.get("조문참고자료")),
        "law": meta,
    }


def extract_article_text(
    raw: Union[str, bytes, dict, None],
    response_type: str = "JSON",
    article: Union[int, str, None] = None,
    article_branch: Union[int, str, None] = 0,
) -> str:
    """Full article text (heading + 항 + 호 + 목), one unit per line."""
    return extract_article(raw, response_type, article, article_branch)["text"]


# ---------------------------------------------------------------------------
# Law search rows: law-id selection, version selection, de-duplication
# ---------------------------------------------------------------------------

def law_rows(search_result: Any) -> list[dict]:
    """Extract the ``law`` rows from a ``run_search`` result / parsed payload."""
    if not search_result:
        return []
    data = search_result
    if isinstance(data, dict) and "ranked_data" in data:
        data = data["ranked_data"]
    if isinstance(data, dict) and "LawSearch" in data:
        data = data["LawSearch"]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("law", "Law"):
        if key in data:
            return [r for r in _as_list(data[key]) if isinstance(r, dict)]
    return []


def _squash(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def select_law_rows(rows: Iterable[dict], law_name: str) -> list[dict]:
    """Return the rows belonging to the single law that best matches ``law_name``.

    Preference: exact ``법령명한글`` match → name containment; within the match
    set 법률 beats 시행령/시행규칙 unless the user named the 시행령/시행규칙
    themselves. All rows (every 연혁/현행/시행예정 version) of the chosen
    ``법령ID`` are returned, newest 공포일자 first.
    """
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return []
    target = _squash(law_name)
    wants_sub = target.endswith(("시행령", "시행규칙", "규칙", "령"))

    exact = [r for r in rows if _squash(r.get("법령명한글", "")) == target]
    if not exact:
        exact = [r for r in rows if target and (target in _squash(r.get("법령명한글", "")) or _squash(r.get("법령명한글", "")) in target)]
    if not exact:
        exact = [r for r in rows if _squash(r.get("법령약칭명", "")) == target]
    pool = exact or rows

    def rank(row: dict) -> tuple:
        name = _squash(row.get("법령명한글", ""))
        kind = row.get("법령구분명", "")
        is_statute = 0 if kind == "법률" else 1
        if wants_sub:
            is_statute = 0 if kind != "법률" else 1
        return (0 if name == target else 1, is_statute, len(name))

    best = sorted(pool, key=rank)[0]
    law_id = best.get("법령ID")
    if law_id:
        chosen = [r for r in rows if r.get("법령ID") == law_id]
    else:
        chosen = [r for r in rows if _squash(r.get("법령명한글", "")) == _squash(best.get("법령명한글", ""))]
    return sorted(chosen, key=_version_sort_key, reverse=True)


def _version_sort_key(row: dict) -> tuple:
    return (row.get("공포일자", "") or "", row.get("공포번호", "") or "", row.get("시행일자", "") or "")


def pick_current_version(rows: Iterable[dict]) -> Optional[dict]:
    """현행 first, else the latest 연혁 (by 시행일자), else the nearest 시행예정."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return None
    current = [r for r in rows if r.get("현행연혁코드") == STATUS_CURRENT]
    if current:
        return max(current, key=lambda r: (r.get("시행일자", ""), _version_sort_key(r)))
    history = [r for r in rows if r.get("현행연혁코드") == STATUS_HISTORY]
    if history:
        return max(history, key=lambda r: (r.get("시행일자", ""), _version_sort_key(r)))
    pending = [r for r in rows if r.get("현행연혁코드") == STATUS_PENDING]
    if pending:
        return min(pending, key=lambda r: (r.get("시행일자", "99999999"), _version_sort_key(r)))
    return rows[0]


def dedupe_versions(rows: Iterable[dict]) -> list[dict]:
    """One row per 법령일련번호, newest 공포일자 first.

    When an MST appears with several 시행일자, the representative row is the one
    whose status ranks highest (현행 > 시행예정 > 연혁) and then the latest
    시행일자. Every 시행일자 seen is kept under ``effective_dates``.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mst = str(row.get("법령일련번호", "") or "")
        if not mst:
            continue
        if mst not in groups:
            groups[mst] = []
            order.append(mst)
        groups[mst].append(row)

    result = []
    for mst in order:
        group = groups[mst]
        rep = dict(min(
            group,
            key=lambda r: (
                _DEDUPE_STATUS_RANK.get(r.get("현행연혁코드", ""), 9),
                -int(r.get("시행일자", "0") or 0),
            ),
        ))
        rep["effective_dates"] = sorted({r.get("시행일자", "") for r in group if r.get("시행일자")})
        result.append(rep)
    return sorted(result, key=_version_sort_key, reverse=True)


def revision_record(row: dict) -> dict:
    """Map an eflaw row to the ``law_amendment_summary`` revision schema."""
    rec = {
        "date": row.get("공포일자", ""),
        "effective_date": row.get("시행일자", ""),
        "type": row.get("제개정구분명", ""),
        "announcement_no": row.get("공포번호", ""),
        "mst": str(row.get("법령일련번호", "") or ""),
        "status": row.get("현행연혁코드", ""),
        "law_type": row.get("법령구분명", ""),
    }
    dates = row.get("effective_dates")
    if dates and len(dates) > 1:
        rec["effective_dates"] = list(dates)
    return rec


def previous_version(versions: list[dict], mst: str) -> Optional[dict]:
    """Given versions sorted newest-first, return the one right before ``mst``."""
    mst = str(mst)
    for i, v in enumerate(versions):
        if str(v.get("mst") or v.get("법령일련번호") or "") == mst:
            return versions[i + 1] if i + 1 < len(versions) else None
    return None


# ---------------------------------------------------------------------------
# Per-article change history (lsJoHstInf)
# ---------------------------------------------------------------------------

def parse_article_history(raw: Union[str, bytes, dict, None], response_type: str = "JSON") -> list[dict]:
    """Parse ``lawService.do?target=lsJoHstInf`` into change entries, newest first.

    Each entry: ``{"mst", "change_date", "reason", "date", "announcement_no",
    "effective_date", "type", "law_type"}``. Returns ``[]`` when nothing usable.
    """
    data = parse_law_payload(raw, response_type)
    if not data:
        return []
    root = data.get("LawService") if isinstance(data.get("LawService"), dict) else data
    rows = _as_list(root.get("law")) if isinstance(root, dict) else []
    entries = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        jo = row.get("조문정보") if isinstance(row.get("조문정보"), dict) else {}
        law = row.get("법령정보") if isinstance(row.get("법령정보"), dict) else {}
        mst = str(law.get("법령일련번호") or "")
        if not mst:
            m = re.search(r"MST=(\d+)", str(jo.get("조문링크", "")))
            mst = m.group(1) if m else ""
        if not mst:
            continue
        entries.append({
            "mst": mst,
            "change_date": _norm(jo.get("조문변경일")),
            "reason": _norm(jo.get("변경사유")),
            "date": _norm(law.get("공포일자")),
            "announcement_no": _norm(law.get("공포번호")),
            "effective_date": _norm(law.get("시행일자")),
            "type": _norm(law.get("제개정구분명")),
            "law_type": _norm(law.get("법령구분명")),
        })
    entries.sort(key=lambda e: (e["change_date"], e["date"], e["announcement_no"]), reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Dates / text cleanup
# ---------------------------------------------------------------------------

def today_str(today: Optional[_dt.date] = None) -> str:
    return (today or _dt.date.today()).strftime("%Y%m%d")


def end_of_current_year(today: Optional[_dt.date] = None) -> str:
    """``YYYY1231`` for the current (or given) year — replaces hardcoded defaults."""
    return f"{(today or _dt.date.today()).year:04d}1231"


def strip_html(text: Any) -> str:
    """Drop ``<br/>`` and other tags from upstream prose, keeping line breaks."""
    if text is None:
        return ""
    if isinstance(text, list):
        return "\n".join(strip_html(t) for t in text)
    s = str(text)
    s = _BR_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    lines = [_WS_RE.sub(" ", line).strip() for line in s.split("\n")]
    return "\n".join(line for line in lines if line)


# ---------------------------------------------------------------------------
# lsDelegated compaction
# ---------------------------------------------------------------------------

def compact_delegation_tree(raw: Union[str, bytes, dict, None], response_type: str = "JSON", max_entries: Optional[int] = None) -> dict:
    """Turn the 168KB ``lsDelegated`` payload into a compact structure.

    Returns ``{"law": {...}, "entries": [{"article", "title", "kind", "target",
    "target_id", "references": [...]}], "entry_count", "by_kind", "targets",
    "truncated"}``. Unknown shapes yield ``{"entries": [], "note": ...}``.
    ``max_entries=None`` (default) keeps every entry; ``references`` are capped
    at 3 per entry only under ``SLIM_RESPONSE``.
    """
    data = parse_law_payload(raw, response_type)
    if not data:
        return {"entries": [], "entry_count": 0, "note": "lsDelegated 응답이 비어 있습니다."}
    root = data.get("lsDelegated", data)
    law = root.get("법령", root) if isinstance(root, dict) else {}
    if not isinstance(law, dict):
        return {"entries": [], "entry_count": 0, "note": "알 수 없는 lsDelegated 응답 형식입니다."}

    info = law.get("법령정보") if isinstance(law.get("법령정보"), dict) else {}
    out_law = {
        "law_name": _norm(info.get("법령명")),
        "law_id": _norm(info.get("법령ID")),
        "mst": _norm(info.get("법령일련번호")),
        "effective": _norm(info.get("시행일자")),
    }

    entries: list[dict] = []
    by_kind: dict[str, int] = {}
    targets: dict[str, str] = {}
    for item in _as_list(law.get("위임조문정보")):
        if not isinstance(item, dict):
            continue
        jo = item.get("조정보") if isinstance(item.get("조정보"), dict) else {}
        n, b = _unit_number(jo)
        art = article_label(n, b) if n else _norm(jo.get("조문번호"))
        for w in _as_list(item.get("위임정보")):
            if not isinstance(w, dict):
                continue
            kinds = [_norm(k) for k in _as_list(w.get("위임구분")) if _norm(k)]
            kind = kinds[0] if kinds else ""
            title = ""
            target_id = ""
            refs: list[str] = []
            for key, value in w.items():
                if key.endswith("제목") and not title:
                    title = _norm(value)
                elif key.endswith("일련번호") and not target_id:
                    target_id = _norm(value)
                elif key.endswith("조문정보"):
                    for ref in _as_list(value):
                        if not isinstance(ref, dict):
                            continue
                        if not title:
                            for rk, rv in ref.items():
                                if rk.endswith("제목") and "조문" not in rk and _norm(rv):
                                    title = _norm(rv)
                                    break
                        if not target_id:
                            for rk, rv in ref.items():
                                if rk.endswith("일련번호") and "조문" not in rk and _norm(rv):
                                    target_id = _norm(rv)
                                    break
                        link = _norm(ref.get("링크텍스트"))
                        where = _norm(ref.get("조항호목"))
                        label = f"{where}: {link}" if where and link else (link or where)
                        if label and label not in refs:
                            refs.append(label)
            by_kind[kind or "기타"] = by_kind.get(kind or "기타", 0) + 1
            if title:
                targets.setdefault(title, target_id)
            entries.append({
                "article": art,
                "title": _norm(jo.get("조문제목")),
                "kind": kind,
                "target": title,
                "target_id": target_id,
                "references": refs[:compact_limit(3)],
            })

    truncated = max_entries is not None and len(entries) > max_entries
    return {
        "law": out_law,
        "entries": entries[:max_entries],
        "entry_count": len(entries),
        "by_kind": by_kind,
        "targets": [{"name": k, "id": v} for k, v in targets.items()],
        "truncated": truncated,
        **({"note": f"{len(entries)}건 중 {max_entries}건만 표시"} if truncated else {}),
    }
