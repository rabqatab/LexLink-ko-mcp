"""prec_search / prec_service helpers: case-number query routing, case-type post-filter,
duplicate-judgment grouping and decision-date sanity warnings.

The law.go.kr precedent index (checked live 2026-11-20) has no case-type parameter (unknown
parameters are ignored), lists the same judgment several times under different 판례일련번호
(same 사건번호, 선고일자, 법원명) and carries a few impossible dates. Each helper makes that visible
instead of hiding it: upstream rows in ``raw_content`` are never rewritten except by the explicit
``case_type`` filter, and no upstream value is ever altered. Pure functions; no network access.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ._helpers import ToolValidationError
from .precedent_status import CASE_RE, civil_year

# 사건종류명 -> 사건종류코드 as seen in live rows (2026-11-20; the 6 values below covered ~1,000 rows
# of 10 unrelated keyword searches). Other codes may exist.
CASE_TYPES = {
    "민사": "400101", "형사": "400102", "가사": "400103",
    "특허": "400106", "일반행정": "400107", "세무": "400108",
}
CASE_TYPE_ALIASES = {"행정": "일반행정", "조세": "세무", "세금": "세무", "가정": "가사", "지식재산": "특허"}
_CODE_TO_NAME = {v: k for k, v in CASE_TYPES.items()}


_CONSTITUTIONAL_KIND_RE = re.compile(r"\d{2,4}(헌가|헌바|헌마|헌라|헌사|헌아|헌나|헌다)\d")


def is_constitutional_case_number(query: str) -> bool:
    """헌재 사건번호 (헌가/헌바/헌마/헌라/헌사/헌아...): not in the court precedent index; use detc_search."""
    return bool(_CONSTITUTIONAL_KIND_RE.fullmatch((query or "").strip()))


_DETC_SOLE_RE = re.compile(r"(\d{2,4})\s*(헌가|헌바|헌마|헌라|헌사|헌아|헌나|헌다)\s*(\d{1,6})")


def sole_constitutional_case_number(query: str) -> Optional[str]:
    """``2013헌바1`` when ``query`` is exactly one 헌재 사건번호 (spaces such as ``2013 헌바 1`` are removed,
    full-width digits become ASCII), else None. Quoted phrases and mixed text are not case numbers here."""
    from .law_extras import ascii_digits
    m = _DETC_SOLE_RE.fullmatch(ascii_digits(query or "").strip())
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else None


def sole_case_number(query: str) -> Optional[str]:
    """``query`` when it is exactly one case number (``63다131``, ``2013다61381``, ``4294민상1350``),
    else None. Mixed text (``63다131 손해배상``), quoted phrases and joined numbers
    (``94므1713, 1720``) are not case numbers here."""
    s = (query or "").strip()
    m = CASE_RE.fullmatch(s)
    if not m or (m.group(4) or "").strip() or is_constitutional_case_number(s):
        return None
    return s


def normalize_case_type(value) -> Optional[tuple]:
    """``(사건종류명, 코드 or None, warning or None)`` for a ``case_type`` argument, None when empty.

    Accepts a name (가사), an alias (행정), or a 6-digit 사건종류코드. A name or code not seen in live rows is
    still applied as an exact match, with a warning, because the list of values is not published."""
    if value is None or str(value).strip() == "":
        return None
    s = re.sub(r"\s+", "", str(value))
    if re.fullmatch(r"\d{6}", s):
        name = _CODE_TO_NAME.get(s)
        return (name or s, s, None if name else
                f"case_type_unknown: 사건종류코드 {s}는 확인된 값(" + ", ".join(f"{n}={c}" for n, c in CASE_TYPES.items()) + ")이 아닙니다. 코드가 일치하는 행만 남깁니다")
    s = CASE_TYPE_ALIASES.get(s, s)
    if s in CASE_TYPES:
        return s, CASE_TYPES[s], None
    return s, None, (f"case_type_unknown: '{s}'는 확인된 사건종류명(" + ", ".join(CASE_TYPES) + ")이 아닙니다. 사건종류명이 정확히 일치하는 행만 남깁니다")


def _store_rows(ranked: dict, rows: list, was_dict: bool) -> None:
    """Write ``rows`` back; a single-row dict stays a dict (the shape the upstream/parser gave)."""
    ranked["prec"] = rows[0] if (was_dict and len(rows) == 1) else rows


def _prec_rows(response: dict):
    """``(ranked_data, rows_list)`` for a prec response, or ``(None, None)``."""
    ranked = response.get("ranked_data") if isinstance(response, dict) else None
    if not isinstance(ranked, dict) or "prec" not in ranked:
        return None, None
    rows = ranked["prec"]
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return None, None
    return ranked, rows


_CT_SCOPE = ("한 번에 업스트림 100행(page = 100행 단위 쪽)을 받아 그 안에서만 거릅니다. 업스트림에는 사건종류 검색 변수가 없어 "
             "totalCnt는 거르기 전 전체 건수이고, 남은 행 수가 아닙니다. 다음 쪽(page+1)에 더 있을 수 있습니다. display는 이때 무시됩니다")


def apply_case_type_filter(response: dict, case_type: tuple) -> dict:
    """Keep only rows of the requested 사건종류 (post-filter of one upstream window).

    Applies to ``ranked_data`` and, when present, to the JSON ``raw_content`` (so both agree).
    Reports ``case_type_filter`` with the counts. Not a search over the whole index: a page of upstream
    rows is filtered, so a rare type can leave few or no rows on a page while later pages still have them."""
    name, code, warn = case_type
    ranked, rows = _prec_rows(response)
    if ranked is None:
        if response.get("status") == "ok":
            response["case_type_filter"] = {"case_type": name, "code": code, "rows_before_filter": 0,
                                            "rows_after_filter": 0, "scope": _CT_SCOPE}
        return response

    def match(row):
        if not isinstance(row, dict):
            return False
        if code:
            return str(row.get("사건종류코드", "")).strip() == code or str(row.get("사건종류명", "")).strip() == name
        return str(row.get("사건종류명", "")).strip() == name

    kept = [r for r in rows if match(r)]
    _store_rows(ranked, kept, isinstance(ranked["prec"], dict))
    raw = response.get("raw_content")
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            root_key = next(iter(data)) if isinstance(data, dict) and len(data) == 1 else None
            if root_key and isinstance(data[root_key], dict) and "prec" in data[root_key]:
                orig = data[root_key]["prec"]
                kept_raw = [r for r in _as_list(orig) if match(r)]
                data[root_key]["prec"] = kept_raw[0] if (isinstance(orig, dict) and len(kept_raw) == 1) else kept_raw
                response["raw_content"] = json.dumps(data, ensure_ascii=False)
        except ValueError:
            pass
    info = {
        "case_type": name, "code": code,
        "rows_before_filter": len(rows), "rows_after_filter": len(kept),
        "upstream_total": ranked.get("totalCnt"),
        "scope": _CT_SCOPE,
    }
    response["case_type_filter"] = info
    return response


def _as_list(v):
    return v if isinstance(v, list) else ([v] if v else [])


def _norm_case_no(v) -> str:
    return re.sub(r"\s+", "", str(v or ""))


_COURT_OWN_SOURCES = ("대법원", "법원도서관", "헌법재판소")
_DIFF_FIELDS = ("데이터출처명", "판결유형", "사건종류명", "사건명")


def _source_rank(row: dict) -> int:
    """0 = the court's own source, 1 = unknown/empty, 2 = a copy from a tax/pension/compensation system."""
    src = str(row.get("데이터출처명") or "").strip()
    if not src or src in _COURT_OWN_SOURCES:
        return 0 if src else 1
    return 2


def _pick_representative(members: list) -> dict:
    """Court's own source first, then a row whose 판시사항 is known to be non-empty (only when the search row
    carries the field), else upstream order (``min`` keeps the first of equal keys)."""
    def key(row):
        has_head = 0 if str(row.get("판시사항") or "").strip() else (1 if "판시사항" in row else 0)
        return (_source_rank(row), has_head)
    return min(members, key=key)


def group_duplicate_rows(response: dict) -> dict:
    """Group rows with the same 사건번호 + 선고일자 + 법원명 (different 판례일련번호).

    These are NOT guaranteed to be the same text: live groups differ in 데이터출처명 (대법원 vs 지방세법령정보시스템),
    사건종류, 판결유형 and in whether 판시사항 is filled. ``ranked_data["prec"]`` keeps one row per group (preferring the
    court's own 데이터출처명 ``대법원``, then a row with a non-empty 판시사항 when the row shows it, else upstream order)
    and gives it ``same_case_ids``. ``duplicate_groups`` lists every member with 데이터출처명/판결유형/사건종류명/사건명
    and ``differs_from_representative``, so nothing is lost when ``raw_content`` is dropped. ``rows_before_grouping`` is the
    count before grouping; ``rank`` can have gaps and the page can hold fewer rows than ``display``. ``raw_content`` is untouched."""
    ranked, rows = _prec_rows(response)
    if ranked is None or len(rows) < 2:
        return response
    groups: dict = {}
    order: list = []  # one entry per row or group, in first-seen order: ("row", row) | ("group", key)
    for row in rows:
        if not isinstance(row, dict):
            order.append(("row", row))
            continue
        key = (_norm_case_no(row.get("사건번호")), str(row.get("선고일자", "")).strip(), str(row.get("법원명", "")).strip())
        if not key[0] or not key[1]:
            order.append(("row", row))
            continue
        if key in groups:
            groups[key].append(row)
        else:
            groups[key] = [row]
            order.append(("group", key))
    if not any(len(v) > 1 for v in groups.values()):
        return response
    summary = []
    out = []
    for kind, val in order:
        if kind == "row":
            out.append(val)
            continue
        members = groups[val]
        if len(members) == 1:
            out.append(members[0])
            continue
        rep = _pick_representative(members)
        ids = [str(m.get("판례일련번호", "")) for m in members]
        rep_id = str(rep.get("판례일련번호", ""))
        rep["same_case_ids"] = [i for i in ids if i != rep_id]
        out.append(rep)
        detail = []
        for m in members:
            entry = {"판례일련번호": str(m.get("판례일련번호", ""))}
            for f in _DIFF_FIELDS:
                entry[f] = m.get(f)
            if m is not rep:
                entry["differs_from_representative"] = [f for f in _DIFF_FIELDS if m.get(f) != rep.get(f)]
            detail.append(entry)
        summary.append({"사건번호": val[0], "선고일자": val[1], "법원명": val[2],
                        "representative": rep_id, "판례일련번호": ids, "members": detail})
    _store_rows(ranked, out, isinstance(ranked["prec"], dict))
    response["rows_before_grouping"] = len(rows)
    response["duplicate_groups"] = summary
    response["duplicate_groups_note"] = (
        "사건번호·선고일자·법원명이 같은 행을 묶었습니다. 데이터출처가 다른 사본일 수 있어(예: 대법원 vs 지방세법령정보시스템) "
        "본문·판시사항·판결유형·사건종류가 서로 다를 수 있습니다(members 참조). ranked_data에는 그룹당 한 행(대법원 출처 우선)만 두고 "
        "나머지 번호를 same_case_ids에 적었습니다. 어느 판례일련번호를 읽었는지 기록하세요. rank에 빈 번호가 생기고 한 쪽이 "
        "display보다 적을 수 있으며 묶기 전 행 수는 rows_before_grouping입니다. raw_content(있으면)는 업스트림 행 그대로입니다")
    return response


# --- decision-date sanity ---------------------------------------------------------

def case_number_year(case_no) -> Optional[int]:
    """Calendar year in a 사건번호 (``2024므14761``, ``63다131`` = 1963, ``4294민상1350`` = 1961), None when unparsable."""
    m = CASE_RE.search(str(case_no or ""))
    if not m:
        return None
    y = int(m.group(1))
    if len(m.group(1)) == 2:
        y += 1900  # two-digit years were used only up to 1999; 4-digit years start in 2000
    return civil_year(y)


def _date_parts(s) -> Optional[tuple]:
    digits = re.sub(r"\D", "", str(s or ""))
    if len(digits) == 8:
        return int(digits[:4]), int(digits[4:6]), int(digits[6:])
    return None


def date_warning(case_no, decision_date) -> Optional[str]:
    """Warning when the decision year is earlier than the year in the case number (impossible: the case
    cannot be decided before it was filed). Never alters the upstream value."""
    cy = case_number_year(case_no)
    parts = _date_parts(decision_date)
    if cy is None or parts is None or cy < 1948 or parts[0] >= cy:
        return None
    return (f"date_before_case_year: 선고일자 {parts[0]}년이 사건번호({str(case_no).strip()})의 연도 {cy}년보다 앞섭니다. "
            f"업스트림 데이터 오류일 수 있으니 판결문의 선고일을 직접 확인하세요(값은 바꾸지 않았습니다)")


def add_row_date_warnings(response: dict) -> dict:
    """Add ``date_warning`` to ranked rows with an impossible 선고일자, and a ``date_warnings`` count note."""
    ranked, rows = _prec_rows(response)
    if ranked is None:
        return response
    n = 0
    for row in rows:
        if isinstance(row, dict):
            w = date_warning(row.get("사건번호"), row.get("선고일자"))
            if w:
                row["date_warning"] = w
                n += 1
    if n:
        response["date_warning_rows"] = n
    return response


_WONSIM_RE = re.compile(r"【원심판결】(.{0,200}?)(?:【|$)", re.S)
_DATE_IN_TEXT_RE = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.")


def service_date_warnings(response: dict) -> list:
    """Warnings for a prec_service result: decision year before the case-number year, and a decision date
    earlier than the date of the 원심판결 named in the body (first date after 【원심판결】). Never raises."""
    try:
        raw = response.get("raw_content") if isinstance(response, dict) else None
        if not isinstance(raw, str):
            return []
        data = json.loads(raw)
        root = next(iter(data.values())) if isinstance(data, dict) and data else None
        if not isinstance(root, dict):
            return []
        out = []
        w = date_warning(root.get("사건번호"), root.get("선고일자"))
        if w:
            out.append(w)
        parts = _date_parts(root.get("선고일자"))
        body = root.get("판례내용")
        if parts and isinstance(body, str):
            m = _WONSIM_RE.search(body)
            d = _DATE_IN_TEXT_RE.search(m.group(1)) if m else None
            if d:
                lower = (int(d.group(1)), int(d.group(2)), int(d.group(3)))
                if lower > parts:
                    out.append(f"date_before_lower_court: 선고일자 {parts[0]}.{parts[1]}.{parts[2]}가 판결문의 원심판결 선고일 "
                               f"{lower[0]}.{lower[1]}.{lower[2]}보다 앞섭니다. 업스트림 데이터 오류일 수 있으니 판결문의 선고일을 직접 확인하세요(값은 바꾸지 않았습니다)")
        return out
    except Exception:
        return []
