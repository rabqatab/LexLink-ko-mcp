"""
Helpers for the history / comparison / appendix / dictionary tools
(oldAndNew, lsJoHstInf, lsHstInf, delHst, lsAbrv, licbyl, thdCmp, lstrm).

These upstream endpoints answer wrong or out-of-range requests with a silent
"0 results" (bad dates, unknown codes, a missing required date) or with a
payload that hides structure (one row is a dict, repeated entries become
parallel arrays), so this module validates arguments before the call and
normalizes the payload after it. Pure functions; no network access.
"""

import datetime
import html
import json
import re
import xml.etree.ElementTree as ET
from typing import Optional

from ._helpers import ToolValidationError

MAX_DISPLAY = 100

# 법령 제개정 종류 (rrClsCd)
RR_CLS_CODES = {
    "300201": "제정", "300202": "일부개정", "300203": "전부개정", "300204": "폐지",
    "300205": "폐지제정", "300206": "일괄개정", "300207": "일괄폐지", "300208": "기타",
    "300209": "타법개정", "300210": "타법폐지",
}
LIST_SORTS = {"lasc", "ldes", "dasc", "ddes", "nasc", "ndes", "efasc", "efdes"}
DEL_HST_KINDS = {"1": "법령", "2": "행정규칙", "3": "자치법규", "13": "학칙공단"}
LICBYL_KINDS = {"1": "별표", "2": "서식", "3": "별지", "4": "별도", "5": "부록"}
LICBYL_SEARCH = {"1": "별표서식명", "2": "관련 법령명", "3": "별표 본문"}
LSTRM_SORTS = {"lasc", "ldes", "rasc", "rdes"}
LSTRM_DIC_KINDS = {"010101": "법령", "010102": "행정규칙"}
THDCMP_KINDS = {"1": "인용조문", "2": "위임조문"}

_KIND_ALIASES = {"인용조문": "1", "위임조문": "2"}


_FULLWIDTH_DIGITS = {ord("０") + i: str(i) for i in range(10)}
GANA_INITIALS = {"ga", "na", "da", "ra", "ma", "ba", "sa", "ah", "ja", "cha", "ka", "ta", "pa", "ha", "etc"}
_KND_CODE_RE = re.compile(r"[A-Z][0-9]{4}")  # 법종구분코드, e.g. A0002 법률, A0007 대통령령


def ascii_digits(value) -> str:
    """Trimmed text with the full-width digits ０-９ folded to ASCII (nothing else is folded).

    Every numeric validator goes through this, so "２０２５０４０１" is "20250401"; other
    look-alikes ("①", Arabic-Indic digits) stay as they are and fail the [0-9] checks.
    Nothing relies on str.isdigit() or \\d, which accept non-ASCII digits."""
    return ("" if value is None else str(value)).translate(_FULLWIDTH_DIGITS).strip()


def _bad(message: str, hints: Optional[list] = None) -> ToolValidationError:
    return ToolValidationError(message, hints=hints)


def as_list(value) -> list:
    """Upstream gives one row as a dict and no row as a missing key: always a list."""
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def validate_yyyymmdd(value, name: str) -> str:
    """A real calendar date as 8 digits (YYYYMMDD); the upstream silently returns 0 rows otherwise."""
    s = ascii_digits(value)
    try:
        if not re.fullmatch(r"[0-9]{8}", s):
            raise ValueError
        datetime.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        raise _bad(
            f"{name} must be a real date in format YYYYMMDD (e.g., '20250401'), got: {value!r}",
            hints=["하이픈 없이 8자리 숫자, 존재하는 날짜여야 합니다 (업스트림은 잘못된 날짜를 0건으로 응답합니다)"],
        ) from None
    return s


def validate_ymd_range(value, name: str) -> str:
    """YYYYMMDD~YYYYMMDD with two real dates and start <= end."""
    s = ascii_digits(value)
    parts = s.split("~")
    if len(parts) != 2:
        raise _bad(f"{name} must be in format YYYYMMDD~YYYYMMDD (e.g., '20240101~20241231'), got: {value!r}")
    start = validate_yyyymmdd(parts[0], name)
    end = validate_yyyymmdd(parts[1], name)
    if start > end:
        raise _bad(f"{name} start date must be <= end date, got: {start} > {end}")
    return f"{start}~{end}"


def validate_digits(value, name: str, *, allow_empty: bool = True) -> Optional[str]:
    """Numeric identifier (법령ID, MST, 공포번호 ...)."""
    if value is None or str(value).strip() == "":
        if allow_empty:
            return None
        raise _bad(f"{name} is required")
    s = ascii_digits(value)
    if not re.fullmatch(r"[0-9]{1,12}", s):
        raise _bad(
            f"{name} must be numeric, got: {value!r}",
            hints=["검색 도구 결과의 법령ID(예: 001706) 또는 일련번호(MST)를 그대로 사용하세요"],
        )
    return s


def validate_choice(value, name: str, allowed, *, upper: bool = False) -> Optional[str]:
    """One of ``allowed`` (mapping or set); None/'' passes through as None."""
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip()
    if upper:
        s = s.upper()
    if s not in allowed:
        raise _bad(
            f"{name} must be one of {sorted(allowed)}, got: {value!r}",
            hints=["업스트림은 알 수 없는 값을 조용히 무시하거나 0건으로 응답합니다"],
        )
    return s


def validate_gana(value) -> Optional[str]:
    """사전식 검색 초성 code: ga, na, da, ra, ma, ba, sa, ah (ㅇ), ja, cha, ka, ta, pa, ha, etc.

    Anything else is silently ignored by the upstream (the filter is dropped and every
    row comes back), so it is rejected."""
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip().lower()
    if s not in GANA_INITIALS:
        raise _bad(
            f"gana must be one of {sorted(GANA_INITIALS)}, got: {value!r}",
            hints=["한글 초성이 아니라 로마자 코드(예: 가 -> ga)를 사용하세요. 업스트림은 알 수 없는 값을 무시하고 전체를 반환합니다"],
        )
    return s


def validate_law_kind(value) -> Optional[str]:
    """법령종류 code in the 법종구분코드 form: a letter and 4 digits (A0001 헌법, A0002 법률, A0007 대통령령, A0009 총리령, A0011 부령 ...).

    The upstream does not publish the full code list; other shapes give 0 rows."""
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip().upper()
    if not _KND_CODE_RE.fullmatch(s):
        raise _bad(
            f"knd must be a 법령종류 code like 'A0002' (법률) or 'A0007' (대통령령), got: {value!r}",
            hints=["업스트림은 알 수 없는 코드를 0건으로 응답합니다"],
        )
    return s


def validate_org(value, name: str = "org") -> Optional[str]:
    """소관부처코드, one or several separated by commas."""
    if value is None or str(value).strip() == "":
        return None
    s = ascii_digits(value).replace(" ", "")
    if not re.fullmatch(r"[0-9]{3,10}(,[0-9]{3,10})*", s):
        raise _bad(
            f"{name} must be a 소관부처코드 (digits, e.g. '1270000'; several separated by commas), got: {value!r}",
        )
    return s


def validate_display(page, display) -> tuple:
    """(page, display) as ints, display capped at the upstream maximum of 100."""
    from ._helpers import validate_paging
    p, d = validate_paging(page, display)
    return p, min(d, MAX_DISPLAY)


def validate_list_type(type_: str, allowed=("JSON", "XML", "HTML"), tool: str = "") -> str:
    t = str(type_ or "").strip().upper()
    if t not in allowed:
        raise _bad(
            f"type must be one of {list(allowed)} for this tool, got: {type_!r}",
            hints=[f"{tool}: 업스트림은 {'/'.join(allowed)}만 지원합니다" if tool else "지원하지 않는 응답 형식입니다"],
        )
    return t


def validate_law_list_filters(
    *, sort, ef_yd, anc_yd, date, nb, anc_no, rr_cls_cd, org, knd, gana,
) -> dict:
    """Filters shared by the oldAndNew and thdCmp lists (same upstream parameter set).

    Returns the cleaned snake_case params (only the ones that were given)."""
    out: dict = {}
    sort = validate_choice(sort, "sort", LIST_SORTS)
    if sort:
        out["sort"] = sort
    if ef_yd not in (None, ""):
        out["ef_yd"] = validate_ymd_range(ef_yd, "ef_yd")
    if anc_yd not in (None, ""):
        out["anc_yd"] = validate_ymd_range(anc_yd, "anc_yd")
    if date not in (None, ""):
        out["date"] = validate_yyyymmdd(date, "date")
    nb = validate_digits(nb, "nb")
    if nb:
        out["nb"] = nb
    if anc_no not in (None, ""):
        s = ascii_digits(anc_no)
        if not re.fullmatch(r"[0-9]{1,9}(~[0-9]{1,9})?", s):
            raise _bad(f"anc_no must be a 공포번호 or a range like 10000~20000, got: {anc_no!r}")
        out["anc_no"] = s
    rr = validate_choice(rr_cls_cd, "rr_cls_cd", RR_CLS_CODES)
    if rr:
        out["rr_cls_cd"] = rr
    org = validate_org(org)
    if org:
        out["org"] = org
    knd = validate_law_kind(knd)
    if knd:
        out["knd"] = knd
    gana = validate_gana(gana)
    if gana:
        out["gana"] = gana
    return out


def normalize_ranked_rows(response: dict, key: str) -> dict:
    """Make ``ranked_data[key]`` always a list (a single upstream row is a bare dict; none is absent)."""
    ranked = response.get("ranked_data") if isinstance(response, dict) else None
    if isinstance(ranked, dict):
        ranked[key] = as_list(ranked.get(key))
    return response


def normalize_jo_info(response: dict, key: str = "law") -> dict:
    """lsJoHstInf rows: ``조문정보.jo`` is a dict for one article, a list for several, "" for none."""
    ranked = response.get("ranked_data") if isinstance(response, dict) else None
    if not isinstance(ranked, dict):
        return response
    for row in as_list(ranked.get(key)):
        if isinstance(row, dict):
            info = row.get("조문정보")
            jo = info.get("jo") if isinstance(info, dict) else None
            row["조문정보"] = {"jo": as_list(jo)}
    return response


def total_count(response: dict) -> Optional[int]:
    ranked = response.get("ranked_data") if isinstance(response, dict) else None
    if isinstance(ranked, dict):
        try:
            return int(str(ranked.get("totalCnt")).strip())
        except (TypeError, ValueError):
            return None
    return None


# ----------------------------------------------------------------------
# thdCmp (3단 비교) body
# ----------------------------------------------------------------------

def normalize_thdcmp_knd(knd) -> str:
    """1 / 2 / '인용조문' / '위임조문' -> '1' / '2'. Required: the upstream returns an empty body without it."""
    if knd is None or str(knd).strip() == "":
        raise _bad(
            "knd is required: 1 (인용조문) or 2 (위임조문)",
            hints=["knd=2(위임조문)는 법률 조문과 그 시행령·시행규칙 위임 조문을 나란히 보여 줍니다",
                   "knd=1(인용조문)은 시행령·시행규칙이 인용하는 법률 조문을 보여 줍니다"],
        )
    s = str(knd).strip()
    s = _KIND_ALIASES.get(s, s)
    if s not in THDCMP_KINDS:
        raise _bad(f"knd must be 1 (인용조문) or 2 (위임조문), got: {knd!r}")
    return s


def thdcmp_anchor(root: dict) -> dict:
    """Identity of the law the 3단 비교 is anchored to (the upstream does not echo the request)."""
    info = root.get("기본정보") if isinstance(root, dict) else None
    if not isinstance(info, dict):
        return {}
    anchor = {
        "law_id": str(info.get("법령ID", "") or ""),
        "law_name": str(info.get("법령명", "") or info.get("기준법령명", "") or ""),
    }
    if info.get("법령일련번호"):
        anchor["mst"] = str(info["법령일련번호"])
    if info.get("삼단비교기준"):
        anchor["basis"] = str(info["삼단비교기준"])
    if info.get("기준법령명"):
        anchor["base_law_name"] = str(info["기준법령명"])
    return anchor


def thdcmp_mismatch(anchor: dict, req_id: Optional[str], req_mst: Optional[str]) -> Optional[str]:
    """Warning text when the returned anchor is not the requested law, else None."""
    if req_id and anchor.get("law_id") and anchor["law_id"].lstrip("0") != req_id.lstrip("0"):
        return (f"요청한 법령ID {req_id}와 응답의 기준 법령ID {anchor['law_id']}({anchor.get('law_name', '')})가 다릅니다. "
                "3단 비교는 시행령·시행규칙 ID를 주면 그 모법을 기준으로 응답합니다")
    if req_mst and anchor.get("mst") and anchor["mst"] != req_mst:
        return (f"요청한 MST {req_mst}와 응답의 기준 법령일련번호 {anchor['mst']}({anchor.get('law_name', '')})가 다릅니다. "
                "3단 비교는 시행령·시행규칙 MST를 주면 그 모법을 기준으로 응답합니다")
    base = anchor.get("base_law_name")
    if base and anchor.get("law_name") and base != anchor["law_name"]:
        return (f"요청한 {anchor['law_name']}는 시행령·시행규칙이고, 응답의 조문 행은 기준 법령 {base}의 3단 비교입니다")
    if anchor.get("basis") not in (None, "", "L"):
        return (f"삼단비교기준이 {anchor['basis']}입니다(L이 아님). 요청한 id/mst가 시행령·시행규칙이면 "
                f"응답은 그 모법({anchor.get('law_name', '')}) 기준입니다. anchor를 확인하세요")
    return None


def _article_lists(section) -> list:
    """The row lists (법률조문 / 시행령조문 / 시행규칙조문 ...) inside a 3단 비교 section."""
    found = []
    if isinstance(section, dict):
        for key, value in section.items():
            rows = as_list(value)
            if rows and any(isinstance(r, dict) and "조번호" in r for r in rows):
                found.append(key)
    return found


_HEADING_RE = re.compile(r"제\s*[0-9]+\s*(?:편|장|절|관)")
_HANG_HEADING_RE = re.compile(r"제\s*[0-9]+\s*항\s")


_BASE_ROW_KEYS = {"조제목", "조가지번호", "조내용", "조번호"}


def _has_children(row: dict) -> bool:
    """A 3단 비교 row carries delegated 시행령/시행규칙 articles as extra keys."""
    return any(k not in _BASE_ROW_KEYS and v for k, v in row.items())


def has_heading_text(row: dict) -> bool:
    """The row's own 조내용 is a chapter/section heading, not article text."""
    content = str(row.get("조내용", "") or "").strip()
    return bool(_HEADING_RE.match(content)) or (not row.get("조제목") and bool(_HANG_HEADING_RE.match(content)))


def is_heading_row(row: dict) -> bool:
    """Chapter/section heading rows ("제1편 총칙", "제2장 ...") share a 조번호 with real articles.

    A real article may have no 조제목 (e.g. content "제5조 삭제 <2010.3.31>"), so headings are
    recognized by their content, not by an empty title. A row that carries delegated
    시행령/시행규칙 children is not a plain heading: for some laws the upstream fills a
    knd=2 row's 조내용 with the enclosing chapter heading and still attaches the real
    delegated articles (measured: 소득세법), so such a row is kept (see thdcmp_heading_only)."""
    return has_heading_text(row) and not _has_children(row)


def thdcmp_heading_only(new_root: dict) -> bool:
    """True when every row kept by select_thdcmp_article has a heading as its own text."""
    rows = []
    for sec_key in ("인용조문삼단비교", "위임조문삼단비교"):
        section = new_root.get(sec_key)
        for list_key in _article_lists(section):
            rows.extend(r for r in as_list(section[list_key]) if isinstance(r, dict))
    return bool(rows) and all(has_heading_text(r) for r in rows)


def select_thdcmp_article(root: dict, jo_code: str) -> tuple:
    """Keep only rows of one article in the 3단 비교 section.

    ``jo_code`` is the 6-digit code (4 digits article + 2 digits branch). Chapter/section
    heading rows never match; rows without a 조번호 never match. Every row list in
    the section is filtered, none is left whole. Returns
    ``(new_root, matched_rows, total_rows)``; the article may have several
    rows (one per delegated 시행령 article)."""
    number, branch = jo_code[:4], jo_code[4:]
    new_root = dict(root)
    matched = total = 0
    for sec_key in ("인용조문삼단비교", "위임조문삼단비교"):
        section = root.get(sec_key)
        if not isinstance(section, dict):
            continue
        new_section = dict(section)
        for list_key in _article_lists(section):
            rows = as_list(section[list_key])
            keep = [r for r in rows
                    if isinstance(r, dict) and r.get("조번호") not in (None, "") and not is_heading_row(r)
                    and ascii_digits(r["조번호"]).zfill(4) == number
                    and ascii_digits(r.get("조가지번호") or "00").zfill(2) == branch]
            total += len(rows)
            matched += len(keep)
            new_section[list_key] = keep
        new_root[sec_key] = new_section
    return new_root, matched, total


def thdcmp_has_no_comparison(root: dict) -> bool:
    info = root.get("기본정보") if isinstance(root, dict) else None
    return isinstance(info, dict) and str(info.get("삼단비교존재여부", "")).strip().upper() == "N"


def oldnew_has_none(root: dict) -> bool:
    return isinstance(root, dict) and str(root.get("신구법존재여부", "")).strip().upper() == "N"


def oldnew_versions(root: dict) -> dict:
    """The old (구조문) and new (신조문) law revision a 신구법 body compares."""
    out = {}
    for label, key in (("old", "구조문_기본정보"), ("new", "신조문_기본정보")):
        info = root.get(key) if isinstance(root, dict) else None
        if isinstance(info, dict):
            out[label] = {
                "law_id": str(info.get("법령ID", "") or ""),
                "mst": str(info.get("법령일련번호", "") or ""),
                "law_name": str(info.get("법령명", "") or ""),
                "effective_date": str(info.get("시행일자", "") or ""),
                "promulgation_date": str(info.get("공포일자", "") or ""),
            }
    return out


def parse_json_root(raw: str):
    """(root_key, root_dict) of a JSON body, or (None, None) when it is not a JSON object."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None, None
    if isinstance(data, dict) and len(data) == 1:
        key = next(iter(data))
        if isinstance(data[key], dict):
            return key, data[key]
    return None, None


# ----------------------------------------------------------------------
# lstrm (법령용어 사전) body
# ----------------------------------------------------------------------

# only well-formed entities ending in ";": html.unescape would also turn "AT&reg" into "AT®"
_ENTITY_RE = re.compile(r"&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_LSTRM_FIELDS = {
    "법령용어일련번호": "term_id",
    "법령용어명_한글": "name_ko",
    "법령용어명_한자": "name_hanja",
    "법령용어코드": "dict_code",
    "법령용어코드명": "dict_name",
    "출처": "source",
    "용례": "example",
    "법령용어정의": "definition",
}


def parse_lstrm_xml(raw: str) -> list:
    """Entries of a ``lawService target=lstrm`` XML body.

    The XML lists entries as flat repeated children (일련번호, 한글명, ..., 정의);
    the JSON form collapses them into parallel arrays and leaves 출처/용례 as
    bare scalars that cannot be tied to an entry, so only XML is used. An entry
    starts at each 법령용어일련번호. Missing fields are None (never "")."""
    root = ET.fromstring(raw)
    entries: list = []
    current: Optional[dict] = None
    for child in root:
        if child.tag == "법령용어일련번호":
            current = {name: None for name in _LSTRM_FIELDS.values()}
            entries.append(current)
        if current is None or child.tag not in _LSTRM_FIELDS:
            continue
        text = "".join(child.itertext()).strip()          # nested tags must not cut the text
        if child.tag in ("법령용어정의", "용례"):
            text = _ENTITY_RE.sub(lambda m: html.unescape(m.group(0)), text)   # CDATA keeps &middot; literal
        field = _LSTRM_FIELDS[child.tag]
        if not text:
            continue
        # a repeated tag (several 출처 ...) is kept, one per line, never last-wins
        current[field] = text if current[field] is None else current[field] + "\n" + text
    return entries


# ----------------------------------------------------------------------
# lsAbrv (법령 약칭) local filter
# ----------------------------------------------------------------------

def _squash(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def filter_abbreviations(rows: list, query: Optional[str]) -> list:
    """Rows whose 법령명한글 or 법령약칭명 contains the query (spaces and case ignored).

    The upstream ignores ``query`` and returns every row (about 2.3 MB)."""
    q = _squash(query)
    if not q or q == "*":
        return list(rows)
    return [r for r in rows
            if q in _squash(r.get("법령명한글")) or q in _squash(r.get("법령약칭명"))]
