"""
Argument guards and visible-filter helpers for the case-law, interpretation,
ordinance, delegation and knowledge-base tools.

The upstream (law.go.kr DRF) silently ignores or mis-applies several arguments:
``date`` on prec/detc/decc/special_decc, comma lists in ``nb``, agency names in
``inq``, unknown ``sort``/``search``/``cls``/``sections`` values, a ``display``
above 100, and ``page`` on aiSearch. A filter that does nothing must not look
applied, so each of these is either translated to the parameter that really
works, rejected with ``VALIDATION_ERROR``, or reported in the response
``warnings``. Pure functions; no network access.
"""

import json
import re
from typing import Callable, Optional

from ._helpers import ToolValidationError, validate_paging
from .law_extras import (
    MAX_DISPLAY, ascii_digits, validate_choice, validate_digits, validate_gana, validate_yyyymmdd,
)

# Verified against the open.law.go.kr guides (precListGuide, detcListGuide, expcListGuide,
# deccListGuide, specialDeccTtListGuide) and live (2026-11): unknown values are ignored upstream.
SEARCH_SCOPES = {
    "prec": {"1", "2", "3"},      # 1 판례명, 2 본문, 3 참조판례
    "detc": {"1", "2"},
    "expc": {"1", "2"},
    "decc": {"1", "2"},
    "special_decc": {"1", "2"},
}
CASE_SORTS = {"lasc", "ldes", "dasc", "ddes", "nasc", "ndes"}
CASE_SORTS_BY_TOOL = {
    "prec": CASE_SORTS, "expc": CASE_SORTS, "decc": CASE_SORTS, "special_decc": CASE_SORTS,
    "detc": CASE_SORTS | {"efasc", "efdes"},
}
# The `date` argument is ignored upstream; the guide's range parameter works (a one-day range
# is `D~D`, verified live: decc rslYd=20250819~20250819 returns only 2025.08.19 rows).
DATE_RANGE_PARAM = {
    "prec": "prnc_yd",       # 선고일자
    "detc": "ed_yd",         # 종국일자
    "decc": "rsl_yd",        # 의결일자
    "special_decc": "rsl_yd",
}
SECTIONS_VALUES = {"summary", "full"}

DISPLAY_CAPPED_WARNING = (
    "display_capped: 업스트림 최대값(100)을 넘는 display={d}는 100으로 제한했습니다. "
    "더 보려면 page를 올리세요"
)
DPA_YD_WARNING = (
    "dpa_yd_sparse: 업스트림의 처분일자(dpaYd) 필드는 대부분 비어 있어 "
    "(측정: decc 35,255건 중 7건, ttSpecialDecc 0건) 0건이어도 해당 기간 결정이 없다는 뜻이 아닙니다. "
    "의결일자 기준은 rsl_yd(또는 date)를 사용하세요"
)
NB_NUMERIC_WARNING = (
    "nb_substring: 숫자만 넣은 사건번호는 업스트림에서 부분일치로 처리되어 다른 연도·사건종류의 사건이 "
    "함께 나올 수 있습니다. 연도·사건부호·번호를 모두 넣어도 접두 일치라 확인이 필요합니다 (nb_prefix_match 참고)"
)
LM_NOT_SENT_NOTE = (
    "lm_not_sent: id로 조회하므로 lm은 업스트림에 보내지 않았습니다 (lm이 정확한 제목과 다르면 업스트림이 "
    "유효한 id도 '일치하는 … 없습니다'로 응답하기 때문). lm과의 일치 여부는 확인하지 않았습니다"
)


AI_PAGE_IGNORED_WARNING = (
    "page_ignored: aiSearch 업스트림은 page를 지원하지 않아 page>1도 1페이지와 같은 행을 돌려줍니다 "
    "(측정). 더 많은 결과가 필요하면 display를 늘리거나 (50/100/200 동작 확인) 질의를 바꾸세요"
)
LS_RLT_EXACT_NAME_HINT = (
    "ls_rlt_search는 정확한 법령명만 일치합니다 (부분 문자열·약칭·주제어는 0건): "
    "law_search로 정식 법령명을 확인한 뒤 그 이름으로 다시 검색하세요"
)


def add_notes(response: dict, *notes: Optional[str]) -> dict:
    """Append neutral, non-warning ``notes`` to an ok dict response."""
    new = [n for n in notes if n]
    if new and isinstance(response, dict) and response.get("status") == "ok":
        response["notes"] = list(response.get("notes") or []) + new
    return response


def add_warnings(response: dict, *warnings: Optional[str]) -> dict:
    """Append non-empty ``warnings`` to an ok dict response's ``warnings`` list."""
    new = [w for w in warnings if w]
    if new and isinstance(response, dict) and response.get("status") == "ok":
        response["warnings"] = list(response.get("warnings") or []) + new
    return response


def cap_display(page, display) -> tuple:
    """``(page, display, warning)`` with display capped at the upstream maximum of 100."""
    p, d = validate_paging(page, display)
    if d > MAX_DISPLAY:
        return p, MAX_DISPLAY, DISPLAY_CAPPED_WARNING.format(d=d)
    return p, d, None


def check_search_args(tool: str, search=None, sort=None, gana=None, cls=None) -> tuple:
    """Validate the enumerated search arguments; returns ``(search, sort, gana, cls)``.

    ``search`` is an int-like 1/2(/3), ``sort`` one of the guide's codes, ``gana`` a
    romanised initial, ``cls`` a numeric 재결구분코드 (decc/special_decc).
    """
    s = validate_choice(search, "search", SEARCH_SCOPES[tool]) if search is not None else None
    so = validate_choice(sort, "sort", CASE_SORTS_BY_TOOL[tool])
    g = validate_gana(gana)
    c = None
    if cls is not None and str(cls).strip() != "":
        c = ascii_digits(cls)
        if not re.fullmatch(r"[0-9]{3,10}", c):
            raise ToolValidationError(
                f"cls must be a numeric 재결구분코드 (e.g. '429022'), got: {cls!r}",
                hints=["검색 결과의 재결구분코드 값을 그대로 사용하세요. 업스트림은 알 수 없는 값도 오류 없이 받아 부분 결과를 돌려줍니다"],
            )
    return (int(s) if s is not None else None), so, g, c


def resolve_date_filter(tool: str, date, range_value: Optional[str]) -> tuple:
    """Translate the ignored upstream ``date`` into the working range parameter.

    Returns ``(range_value, applied)`` where ``applied`` is None or
    ``{"date": "YYYYMMDD", "applied_as": "prnc_yd=YYYYMMDD~YYYYMMDD"}`` for the response.
    A ``date`` that disagrees with an explicit range is a ``VALIDATION_ERROR``.
    """
    if date is None or str(date).strip() in ("", "0"):
        return range_value, None
    d = validate_yyyymmdd(date, "date")
    param = DATE_RANGE_PARAM[tool]
    one_day = f"{d}~{d}"
    if range_value and range_value != one_day:
        raise ToolValidationError(
            f"date와 {param}를 함께 쓸 수 없습니다 (date={d}, {param}={range_value}). 하나만 지정하세요",
            hints=[f"date는 업스트림이 무시하는 값이라 {param}={one_day}로 변환해 보냅니다"],
        )
    return one_day, {"date": d, "applied_as": f"{param}={one_day}"}


def attach_filters_applied(response: dict, applied: Optional[dict]) -> dict:
    """Show a translated filter in the response so it is visible that it was applied."""
    if applied and isinstance(response, dict) and response.get("status") == "ok":
        response["filters_applied"] = dict(response.get("filters_applied") or {}, **applied)
    return response


_CASE_NO_DASH_RE = re.compile(r"^[가-힣]+-(\d{4})-([가-힣]+)-(\d+)$")
_CASE_NO_TOKEN_RE = re.compile(r"(?:[가-힣]+-)?\d{2,4}-?[가-힣]+-?\d+")


def normalize_case_number(value, name: str = "nb") -> Optional[str]:
    """One 사건번호 as the upstream matches it (``2025두34754``).

    - A comma list returns 0 rows upstream even when every number exists (measured), so it
      is rejected; call once per number.
    - The display form ``대법원-2025-두-34754`` (국세 source rows) matches nothing upstream
      and is converted to ``2025두34754``.
    Returns None for empty input.
    """
    if value is None or str(value).strip() == "":
        return None
    s = ascii_digits(value)
    if re.search(r"[,，、;]", s):
        raise ToolValidationError(
            f"{name}에는 사건번호를 하나만 넣을 수 있습니다 (쉼표로 구분한 목록은 업스트림이 항상 0건으로 응답합니다): {value!r}",
            hints=["사건번호마다 따로 호출하세요 (예: nb='2023다287663')"],
        )
    tokens = s.split()
    if len(tokens) > 1 and sum(1 for t in tokens if _CASE_NO_TOKEN_RE.fullmatch(t)) >= 2:
        raise ToolValidationError(
            f"{name}에는 사건번호를 하나만 넣을 수 있습니다 (공백으로 이어 붙인 여러 번호는 하나의 번호로 합쳐져 "
            f"엉뚱한 값이 됩니다): {value!r}",
            hints=["사건번호마다 따로 호출하세요 (예: nb='2023다287663')"],
        )
    s = re.sub(r"\s+", "", s)
    m = _CASE_NO_DASH_RE.fullmatch(s)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else s


def check_nb_exactness(response: dict, nb: Optional[str]) -> dict:
    """The upstream matches ``nb`` as a prefix (``2010헌바1`` returned 109 rows, first 2010헌바125).

    If a returned row's 사건번호 is not exactly ``nb``: keep only the exact rows in
    ``ranked_data`` when exactly one row matches (``raw_content`` is left as returned and the
    warning says so), otherwise warn and leave the rows. Nothing happens when all rows are exact.
    """
    ranked = response.get("ranked_data") if isinstance(response, dict) else None
    if not nb or response.get("status") != "ok" or not isinstance(ranked, dict):
        return response
    key = next((k for k, v in ranked.items()
                if (isinstance(v, list) and v and isinstance(v[0], dict) and "사건번호" in v[0])
                or (isinstance(v, dict) and "사건번호" in v)), None)
    if key is None:
        return response
    rows = ranked[key] if isinstance(ranked[key], list) else [ranked[key]]

    def exact(row):
        value = str(row.get("사건번호", "")).strip()
        m = _CASE_NO_DASH_RE.fullmatch(value)
        return (f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else value) == nb

    hits = [r for r in rows if exact(r)]
    if len(hits) == len(rows):
        return response
    shown = ", ".join(str(r.get("사건번호", "")) for r in rows[:5])
    if len(hits) == 1:
        ranked[key] = hits
        ranked["totalCnt"] = "1"
        ranked.pop("numOfRows", None)
        return add_warnings(response, (
            f"nb_prefix_match: nb={nb}는 접두 일치라 업스트림이 {len(rows)}건 이상을 돌려줬고(예: {shown}) "
            f"ranked_data에는 정확히 일치하는 1건만 남겼습니다. raw_content는 업스트림 응답 그대로입니다"))
    return add_warnings(response, (
        f"nb_prefix_match: 반환된 행 중 사건번호가 nb={nb}와 정확히 일치하는 행이 "
        f"{'없습니다' if not hits else str(len(hits)) + '건뿐입니다'} (업스트림은 접두 일치, 예: {shown}). "
        f"행의 사건번호를 직접 확인하세요"))


def nb_year_form_hint(nb: Optional[str], response: dict) -> Optional[str]:
    """Judgments before 2000 are indexed with a two-digit year (``94므1713``); the four-digit form
    ``1994므1713`` finds nothing. Hint only when the four-digit pre-2000 form returned no rows."""
    m = re.fullmatch(r"(19)(\d{2})([가-힣]+\d+)", nb or "")
    if not m or not isinstance(response, dict) or response.get("status") != "ok":
        return None
    ranked = response.get("ranked_data")
    rows = [v for v in ranked.values() if isinstance(v, list)] if isinstance(ranked, dict) else []
    if any(rows[0] if rows else []):
        return None
    return (f"nb_year_form: 2000년 이전 사건은 두 자리 연도로 색인되어 있어 nb={nb}는 찾지 못할 수 있습니다. "
            f"nb='{m.group(2)}{m.group(3)}'로 다시 조회하세요")


def nb_numeric_warning(nb: Optional[str]) -> Optional[str]:
    return NB_NUMERIC_WARNING if nb and re.fullmatch(r"[0-9]+", nb) else None


def validate_inq(value) -> Optional[str]:
    """expc ``inq`` is a 질의기관코드 (digits). An agency name is silently mis-filtered
    upstream (measured: inq=국방부 returned 3,805 rows whose 질의기관 is empty), so names are rejected."""
    if value is None or str(value).strip() == "":
        return None
    s = ascii_digits(value)
    if not re.fullmatch(r"[0-9]{5,10}", s):
        raise ToolValidationError(
            f"inq must be a 질의기관코드 (digits, e.g. '1290000' for 국방부), got: {value!r}",
            hints=[
                "기관명은 지원되지 않습니다: 업스트림이 이름을 코드로 바꾸지 않고 전혀 다른 건을 돌려줍니다",
                "expc_search 결과의 질의기관코드/질의기관명 필드에서 코드를 확인하세요",
            ],
        )
    return s


def validate_sections(sections) -> Optional[str]:
    """``None`` / ``"summary"`` / ``"full"``; anything else would silently behave like full."""
    if sections is None or str(sections).strip() == "":
        return None
    return validate_choice(str(sections).strip().lower(), "sections", SECTIONS_VALUES)


def require_id(value, name: str = "id") -> str:
    """A service id must be a non-blank value (the upstream gets ``ID=`` otherwise)."""
    if value is None or str(value).strip() == "":
        raise ToolValidationError(f"{name} is required", hints=["검색 결과의 일련번호를 id로 전달하세요"])
    return str(value).strip()


# ---------- lsDelegated: client-side article filter ----------

def filter_delegated_by_jo(raw_content: str, jo_code: str) -> dict:
    """Keep only the ``위임조문정보`` entries of article ``jo_code`` (6-digit JO) in a JSON body.

    The upstream has no article parameter (건축법: 3.7 MB). Returns
    ``{"raw_content": <filtered JSON text>, "selection": {...}}`` where ``selection`` states
    how many article entries the law has and how many matched.
    """
    data = json.loads(raw_content)
    root = data.get("lsDelegated", data) if isinstance(data, dict) else {}
    law = root.get("법령") if isinstance(root, dict) else None
    if not isinstance(law, dict):
        raise ValueError("unexpected lsDelegated payload shape")
    items = law.get("위임조문정보")
    items = items if isinstance(items, list) else ([items] if items else [])
    want = (int(jo_code[:4]), int(jo_code[4:]))
    kept = []
    for item in items:
        unit = item.get("조정보") if isinstance(item, dict) and isinstance(item.get("조정보"), dict) else {}
        try:
            got = (int(str(unit.get("조문번호", "")).strip() or 0), int(str(unit.get("조문가지번호") or "").strip() or 0))
        except ValueError:
            continue
        if got == want:
            kept.append(item)
    law["위임조문정보"] = kept
    selection = {
        "jo": jo_code,
        "articles_with_delegation_in_law": len(items),
        "matched": len(kept),
        "original_bytes": len(raw_content.encode("utf-8")),
    }
    out = json.dumps(data, ensure_ascii=False)
    selection["filtered_bytes"] = len(out.encode("utf-8"))
    return {"raw_content": out, "selection": selection}


# ---------- ordin_service: 자치법규ID / 일련번호 collision ----------

_ORDIN_FIELDS = ("자치법규ID", "자치법규일련번호", "자치법규명", "지자체기관명")


def ordin_identity(raw_content: Optional[str], response_type: str = "JSON") -> Optional[dict]:
    """``{자치법규ID, 자치법규일련번호, 자치법규명, 지자체기관명}`` of an ordin body, or None."""
    if not isinstance(raw_content, str) or not raw_content.strip():
        return None
    if response_type.upper() == "JSON":
        try:
            data = json.loads(raw_content)
        except ValueError:
            return None
        root = next(iter(data.values()), None) if isinstance(data, dict) and data else None
        info = root.get("자치법규기본정보", root) if isinstance(root, dict) else None
        if not isinstance(info, dict):
            return None
        found = {k: str(info.get(k) or "").strip() for k in _ORDIN_FIELDS}
    elif response_type.upper() == "XML":
        found = {}
        for k in _ORDIN_FIELDS:
            m = re.search(rf"<{k}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{k}>", raw_content, re.S)
            found[k] = m.group(1).strip() if m else ""
    else:
        return None
    return found if found.get("자치법규ID") or found.get("자치법규일련번호") else None


def ordin_resolved(raw_content: Optional[str], response_type: str) -> dict:
    """The ``resolved`` block returned with every ok ordin_service response: what the lookup returned."""
    ident = ordin_identity(raw_content, response_type)
    if not ident:
        return {"available": False, "note": f"type={response_type}에서는 반환된 자치법규를 읽지 못했습니다 (JSON/XML에서 제공)"}
    return {
        "자치법규명": ident.get("자치법규명", ""),
        "지자체기관명": ident.get("지자체기관명", ""),
        "자치법규ID": ident.get("자치법규ID", ""),
        "자치법규일련번호": ident.get("자치법규일련번호", ""),
    }


def ordin_id_collision(requested_id: str, main: Optional[dict], probe: Optional[dict]) -> Optional[str]:
    """Neutral note when ``requested_id`` is the 자치법규ID of one ordinance and also the
    자치법규일련번호 of a different one; None when there is no collision."""
    if not probe or probe.get("자치법규일련번호") != requested_id:
        return None
    if main and main.get("자치법규ID") == probe.get("자치법규ID"):
        return None
    desc = lambda i: f"'{i.get('자치법규명', '')}' ({i.get('지자체기관명', '')}, 자치법규ID {i.get('자치법규ID', '')}, 일련번호 {i.get('자치법규일련번호', '')})"
    if main:
        return (
            f"id_collision: {requested_id}는 두 자치법규에 모두 해당합니다. 자치법규ID로는 {desc(main)}, "
            f"자치법규일련번호로는 {desc(probe)}. 이 응답의 본문은 id를 자치법규ID로 조회한 결과"
            f"({main.get('자치법규명', '')})입니다. 다른 쪽이 필요하면 mst={requested_id}로 조회하세요"
        )
    return (
        f"id_is_serial_number: {requested_id}는 자치법규ID로는 조회되지 않고 {desc(probe)}의 "
        f"자치법규일련번호입니다. mst={requested_id}로 조회하세요"
    )


def check_ordin_id_collision(
    response: dict, requested_id: str, response_type: str, probe: Callable[[], Optional[dict]],
) -> dict:
    """``verify_id=True``: probe ``mst=<requested_id>`` and report an id/일련번호 collision.

    ``probe`` returns the JSON-form upstream response dict (or None). Anything that cannot be
    determined (HTML body, failed probe) is reported, because silence would read as "no collision".
    """
    ok = response.get("status") == "ok"
    main = ordin_identity(response.get("raw_content"), response_type) if ok else None
    if ok and main is None:
        return add_warnings(response, (
            f"id_check_undetermined: type={response_type}에서는 반환된 자치법규를 읽지 못해 "
            "id와 일련번호의 충돌 여부를 판단할 수 없습니다 (type=JSON 또는 XML로 다시 확인하세요)"))
    try:
        probed = probe()
    except Exception:  # best effort; the warning below says the check did not run
        probed = None
    if probed is None or (probed.get("status") != "ok" and probed.get("error_code") != "NOT_FOUND"):
        return add_warnings(response, "id_check_undetermined: mst 조회가 실패해 id와 일련번호의 충돌 여부를 확인하지 못했습니다")
    other = ordin_identity(probed.get("raw_content"), "JSON") if probed.get("status") == "ok" else None
    msg = ordin_id_collision(requested_id, main, other)
    if not msg:
        return response
    if ok:
        return add_warnings(response, msg)
    response = dict(response)
    response["hints"] = list(response.get("hints") or []) + [msg]
    return response
