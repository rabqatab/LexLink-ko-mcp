"""Pure helpers and orchestration for ``prec_status`` (has a later decision overruled this one?).

law.go.kr has no citator. What the data does give us: the *overruling* decision (a 전원합의체
판결) lists the overruled case in its ``참조판례`` field with a ``(변경)`` marker, and its text
often says "... 판결은 이 판결의 견해에 배치되는 범위 내에서 변경한다". The old decision never names
its overruler, so the direction is always: search for LATER decisions that mention the old case
number, then read those decisions.

Approach (bounded, every step is reported in ``searched_scope``):

1. resolve the target (``prec_search nb=`` or ``prec_service`` by id) to get its date;
2. ``prec_search query=<case number> search=2`` (full-text search, newest first) lists the decisions
   that quote the number; keep the later 전원합의체 ones (only the full bench can change a
   precedent), at most ``max_scan`` of them;
3. ``prec_service`` each and look for the case number in 참조판례 / 판시사항 / 판결요지 / 판례내용.

Evidence levels (never a bare "overruled"):

* ``explicit_marker``: 참조판례 entry for the case followed by ``(변경)``/``(폐기)``.
* ``explicit_sentence``: one sentence names the case number and says it is changed (변경/폐기).
* lead only (``possible_overruling_needs_review``): the later 전원합의체 decision cites the case and
  contains a generic "... 변경한다" sentence without naming it. Not a finding.

Absence of evidence is reported as ``no_overruling_found_in_searched_set`` together with the
scope; it never means "not overruled".
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

OVERRULED_FOUND = "overruled_found"
POSSIBLE = "possible_overruling_needs_review"
NONE_FOUND = "no_overruling_found_in_searched_set"
INCOMPLETE = "incomplete_search"      # something that could hold the answer was not read
CASE_NOT_FOUND = "case_not_found"     # the case itself is not in the 판례 index: nothing can be said

DEFAULT_MAX_SCAN = 5
MAX_SCAN_LIMIT = 10
SEARCH_PAGE_SIZE = 100
MAX_SEARCH_PAGES = 3
QUOTE_MAX = 400

# ---------------------------------------------------------------------------
# case numbers
# ---------------------------------------------------------------------------

_KINDS = (
    # two/three-letter kinds first so they win over their prefixes (민상.. are 단기 연호 era kinds)
    "민재항|민상|민재|민항|형상|형비상|행상|"
    "재다|재누|재두|재도|재나|재가|재므|재스|재마|재초|초기|초재|초보|헌가|헌나|헌다|헌마|헌바|헌사|헌아|"
    "감도|감노|전도|전노|다카|다단|가합|가단|가소|나단|구합|구단|고합|고단|고정|고약|드합|드단|느합|느단|"
    "카합|카단|카기|카담|카확|카불|카정|"
    "가|나|다|라|마|바|사|아|자|차|카|타|파|하|거|너|더|러|머|버|서|어|저|고|노|도|로|모|보|소|오|조|초|코|토|포|호|"
    "구|누|두|루|무|부|수|우|주|추|쿠|투|푸|후|그|느|드|르|므|브|스|으|즈|츠|크|트|프|흐"
)
# year (2 or 4 digits) + kind + number, no spaces; optional ", 1720" style joined numbers
CASE_RE = re.compile(
    rf"(?<!\d)(\d{{4}}|\d{{2}})({_KINDS})(\d{{1,6}})(?![\d가-힣])"
    r"((?:\s*[,，、·ㆍ]\s*\d{1,6}(?![\d가-힣.]))*)"
)
_NUM_RE = re.compile(r"\d{1,6}")


def norm_year(y: str) -> int:
    n = int(y)
    if len(y) == 4:
        return n
    return 1900 + n if n >= 50 else 2000 + n


CaseKey = tuple  # (year, kind, number)


def civil_year(y: int) -> int:
    """단기 years (4292형상242 = 1959) to 서기."""
    return y - 2333 if y >= 4200 else y


def parse_case_numbers(text: str) -> list[CaseKey]:
    """Case keys named in ``text`` (joined "94므1713, 1720" expands to both)."""
    keys: list[CaseKey] = []
    for m in CASE_RE.finditer(text or ""):
        year, kind = norm_year(m.group(1)), m.group(2)
        for n in [m.group(3)] + _NUM_RE.findall(m.group(4) or ""):
            keys.append((year, kind, int(n)))
    return keys


def case_mentions(text: str, key: CaseKey) -> list[tuple[int, int]]:
    """(start, end) spans of every mention of ``key`` in ``text`` (including joined numbers)."""
    spans = []
    for m in CASE_RE.finditer(text or ""):
        year, kind = norm_year(m.group(1)), m.group(2)
        nums = [int(m.group(3))] + [int(n) for n in _NUM_RE.findall(m.group(4) or "")]
        if (year, kind) == (key[0], key[1]) and key[2] in nums:
            spans.append((m.start(), m.end()))
    return spans


def format_case_key(key: CaseKey) -> str:
    return f"{key[0]}{key[1]}{key[2]}"


class BodyUnreadable(Exception):
    """A candidate's 200 response could not be parsed as a 판례 body."""


def case_number_forms(key: CaseKey, indexed: Optional[str] = None, original: Optional[str] = None) -> list[str]:
    """Spellings to search for: the index's own 사건번호 when the case was found, else both year forms
    for pre-2000 cases ('94므1713' is how the index and later decisions write it; '1994므1713' is how
    a citation or a user may write it)."""
    if indexed:
        found = parse_case_numbers(indexed)
        if found:
            return [re.sub(r"\s+", "", indexed.split(",")[0])]
    two = f"{key[0] % 100:02d}{key[1]}{key[2]}"
    four = f"{key[0]}{key[1]}{key[2]}"
    if 1948 <= key[0] < 2000:
        return [two, four]
    return [four]


def format_case_no(key: CaseKey, original: Optional[str] = None) -> str:
    """'94므1713' style when the original used 2-digit years, else 4-digit."""
    if original and re.match(r"\d{2}[^\d]", original.strip()):
        return f"{key[0] % 100:02d}{key[1]}{key[2]}"
    return format_case_key(key)


def parse_target(case_number: str) -> tuple[CaseKey, list[CaseKey]]:
    """Primary case key and joined co-numbers from free text like
    '94므1713', '94므1713, 1720', '대법원 1995. 5. 23. 선고 94므1713 판결'."""
    keys = parse_case_numbers(case_number or "")
    if not keys:
        raise ValueError(
            f"사건번호를 해석할 수 없습니다: {case_number!r} (예: '94므1713', '2013므2250', '2018다248909')")
    return keys[0], keys[1:]


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<br\s*/?>|</?p\s*/?>", re.I)


def clean(text: Any) -> str:
    """Upstream prose with <br/> removed and whitespace collapsed (characters otherwise unchanged)."""
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


_ENTRY_RE = re.compile(
    r"(?:대법원|헌법재판소|[가-힣]{2,10}(?:지방법원|고등법원|법원|지원))\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.")
_MARKER_RE = re.compile(r"\(\s*(변경|폐기)\s*\)")
_SENT_END_RE = re.compile(r"다\.(?=\s|$)")
# explicit wording: measured on 180 en banc decisions, 135 of 137 case-naming sentences that match it sit
# next to a (변경) marker for the same case (the 2 others look like genuine omissions of the marker)
_CHANGE_RE = re.compile(r"(?:변경|폐기)\s*(?:하기로|한다|하고|하며)")
# softer wording ("변경함이 상당하다", "변경하는 것이 타당하다", "폐기된다"): zero occurrences in those 180
# decisions, so its precision is unmeasured; a sentence naming the case with it is a lead, not evidence
_SOFT_CHANGE_RE = re.compile(
    r"(?:변경|폐기)\s*함이\s*(?:상당|타당)하다|(?:변경|폐기)\s*하는\s*것이\s*(?:상당|타당)하다"
    r"|(?:변경|폐기)\s*(?:된다|되어야\s*한다)")
# the deciding court's own declaration ("... 변경한다", "... 변경하기로 한다"), not a narrative about another
# decision ("위 전원합의체 판결은 ... 변경하였다", "... 폐기함으로써")
_DECLARE_RE = re.compile(
    r"(?:변경|폐기)\s*(?:하기로\s*한다|한다)"
    # an implicit change: 2018다248909 never says "88다카16867을 변경한다" but "위와 같은 견해는 더 이상 유지하기 어렵다"
    r"|더\s*이상\s*(?:유지하기\s*어렵|유지할\s*수\s*없|유지될\s*수\s*없)")

# 다수의견 / 별개의견 / 반대의견 / 보충의견 headings: "[대법관 X의 반대의견]", "대법관 X의 별개의견은",
# "다수의견에 대한 대법관 X의 보충의견". The text after a minority heading is a minority opinion until a
# "[다수의견]" heading.
_NAME = r"대법관\s*[가-힣]{2,4}(?:\s*(?:[,，ㆍ·]|와|과|및)\s*[가-힣]{2,4})*"
_OPINION_HEAD_RE = re.compile(
    r"[\[【]\s*(?P<b>[^\]】]{0,60}?(?:다수|반대|별개|보충)\s*의견[^\]】]{0,30}?)\s*[\]】]"
    rf"|(?P<n>(?:다수\s*의견에\s*대한\s*)?{_NAME}의\s*(?:반대|별개|보충)\s*의견)"
    r"|(?P<s>다수\s*의견에\s*대한\s*보충\s*의견)")


def opinion_role(text: str, pos: int) -> str:
    """'majority' or 'minority' for the text at ``pos`` (default majority when no heading precedes)."""
    role = "majority"
    for m in _OPINION_HEAD_RE.finditer(text, 0, pos):
        b = m.group("b")
        if b is not None:
            role = "majority" if ("다수" in b and not re.search(r"반대|별개|보충", b)) else "minority"
        else:
            role = "minority"
    return role


_LIST_FILLER_RE = re.compile(
    r"대법원|헌법재판소|\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.|선고|자|판결|결정|전원합의체|등|및|와|과|또는|각|[,，·ㆍ()\s]"
    r"|공\d{2,4}[상하]?[,\s\d]*|집\d[\d\-①②]*")


def change_ties_to_case(text: str, hs: int, he: int, change_start: int) -> bool:
    """Is the 변경 wording at ``change_start`` about the case mentioned at ``hs:he``?

    When another case number sits between them, it counts as a list ("A 판결, B 판결은 변경한다")
    only if nothing but citation filler separates the case numbers; otherwise the wording belongs to
    the later case ("A 판결은 유지하되 B 판결은 변경한다").
    """
    mid = text[he:change_start]
    others = [m for m in CASE_RE.finditer(mid)]
    if not others:
        return True
    rest = mid
    for m in reversed(others):
        rest = rest[:m.start()] + " " + rest[m.end():]
    rest = _LIST_FILLER_RE.sub("", rest)
    return rest in ("", "은", "는", "을", "를", "도")      # the subject/object particle of the last case in the list
_NEGATED_RE = re.compile(r"(변경|폐기)\s*(?:할\s*필요가?\s*없|하지\s*(?:아니|않)|할\s*수\s*없|할\s*이유가?\s*없|(?:하고\s*있는|한|하는)\s*것(?:이|은)\s*아니)")
_GENERIC_RE = re.compile(r"(?:대법원|판결|판례|견해|결정|선례|법리)")


def reference_entries(ref: str) -> list[tuple[int, int]]:
    """Spans of the individual entries of a 참조판례 string (split at 'court date.' starts)."""
    starts = [m.start() for m in _ENTRY_RE.finditer(ref)]
    if not starts:
        return [(0, len(ref))] if ref else []
    if starts[0] > 0:
        starts.insert(0, 0)  # leading entry without a court prefix ("2006. 6. 22. 자 2004스42 ...")
    return list(zip(starts, starts[1:] + [len(ref)]))


def _sentence_around(text: str, start: int, end: int) -> tuple[int, int]:
    s = 0
    for m in _SENT_END_RE.finditer(text, 0, start):
        s = m.end()
    m = _SENT_END_RE.search(text, end)
    e = m.end() if m else len(text)
    return s, e


def _quote(text: str, s: int, e: int, hit: Optional[tuple[int, int]] = None) -> str:
    seg = text[s:e].strip()
    if len(seg) <= QUOTE_MAX:
        return seg
    # keep a verbatim window around the case-number mention
    if hit:
        lo = max(s, hit[0] - QUOTE_MAX // 3)
        return ("…" if lo > s else "") + text[lo:lo + QUOTE_MAX].strip() + "…"
    return seg[:QUOTE_MAX] + "…"


def find_evidence(fields: dict, key: CaseKey) -> dict:
    """Evidence that the decision whose fields are given changes the case ``key``.

    ``fields`` maps 참조판례 / 판시사항 / 판결요지 / 판례내용 to the upstream strings.
    Returns ``{"explicit": [...], "cited": [...], "generic_change": [...]}`` where every item has
    ``field`` and a verbatim ``quote``.
    """
    explicit: list[dict] = []
    cited: list[dict] = []
    soft: list[dict] = []
    seen: set = set()

    ref = clean(fields.get("참조판례"))
    for hs, he in case_mentions(ref, key):
        for es, ee in reference_entries(ref):
            if es <= hs < ee:
                entry = ref[es:ee]
                tail = entry[hs - es:]
                # the marker must follow this case's own text, before another case number begins
                after = tail[(he - hs):]
                other = CASE_RE.search(after)
                limit = other.start() if other else len(after)
                mk = _MARKER_RE.search(after[:limit])
                item = {"field": "참조판례", "quote": entry.strip().rstrip(",").strip()}
                if mk:
                    item["marker"] = f"({mk.group(1)})"
                    explicit.append({**item, "evidence": "explicit_marker"})
                else:
                    cited.append(item)
                break

    generic: list[dict] = []
    for field in ("판시사항", "판결요지", "판례내용"):
        text = clean(fields.get(field))
        if not text:
            continue
        for hs, he in case_mentions(text, key):
            s, e = _sentence_around(text, hs, he)
            sent = text[s:e]
            # "(… 판결 등 참조)" cites a case as support; a bare "(… 판결 등)" after "…입장을 견지하여
            # 왔다" cites the position being departed from
            tail = text[he:he + 300]
            close = tail.find(")")
            supportive = "참조" in (tail[:close + 1] if close >= 0 else tail[:60])
            # the change wording must come after the case number in the same sentence and be about
            # this case, not a later one in the same sentence
            change_after = next((c for c in _CHANGE_RE.finditer(text, he, e)
                                 if change_ties_to_case(text, hs, he, c.start())), None)
            role = opinion_role(text, hs)
            soft_after = next((c for c in _SOFT_CHANGE_RE.finditer(text, he, e)
                               if change_ties_to_case(text, hs, he, c.start())), None)
            if change_after and not supportive and not _NEGATED_RE.search(sent) and role == "majority":
                q = _quote(text, s, e, (hs, he))
                if (field, s) not in seen:
                    seen.add((field, s))
                    explicit.append({"field": field, "quote": q, "evidence": "explicit_sentence"})
            elif soft_after and not supportive and not _NEGATED_RE.search(sent) and role == "majority":
                soft.append({"field": field, "quote": _quote(text, s, e, (hs, he))})
            else:
                cited.append({"field": field, "quote": _quote(text, s, e, (hs, he)), "supporting": supportive,
                              "opinion": role, "change_wording_in_minority_opinion": bool(change_after and role == "minority")})
        if not generic:
            for m in _DECLARE_RE.finditer(text):
                s, e = _sentence_around(text, m.start(), m.end())
                sent = text[s:e]
                if (_NEGATED_RE.search(sent) or not _GENERIC_RE.search(sent) or parse_case_numbers(sent)
                        or opinion_role(text, m.start()) != "majority"):
                    continue
                generic.append({"field": field, "quote": _quote(text, s, e, (m.start(), m.end()))})
                break
    return {"explicit": explicit, "cited": cited, "generic_change": generic, "soft": soft}


# ---------------------------------------------------------------------------
# list rows
# ---------------------------------------------------------------------------

def _rows(parsed: dict) -> list[dict]:
    pr = parsed.get("prec", []) if isinstance(parsed, dict) else []
    if isinstance(pr, dict):
        pr = [pr]
    return [r for r in pr if isinstance(r, dict)]


def normalize_date(d: Any) -> str:
    return re.sub(r"\D", "", str(d or ""))[:8]


def is_en_banc(row: dict) -> bool:
    return "전원합의체" in (row.get("판결유형") or "")


def row_key(row: dict) -> Optional[CaseKey]:
    ks = parse_case_numbers(row.get("사건번호") or "")
    return ks[0] if ks else None


def brief(row: dict) -> dict:
    return {"case_number": row.get("사건번호", ""), "id": str(row.get("판례일련번호", "")),
            "decision_date": normalize_date(row.get("선고일자")), "decision_type": row.get("판결유형", ""),
            "court": row.get("법원명", ""), "case_name": clean(row.get("사건명"))}


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

SearchFn = Callable[[dict], dict]    # params -> {"total": int, "rows": [row, ...]}
ServiceFn = Callable[[str], Optional[dict]]  # 판례일련번호 -> PrecService fields (None = body unavailable)


def check_status(
    *,
    key: CaseKey,
    co_keys: list,
    case_text: str,
    search: SearchFn,
    service: ServiceFn,
    target_row: Optional[dict] = None,
    max_scan: int = DEFAULT_MAX_SCAN,
    max_pages: int = MAX_SEARCH_PAGES,
) -> dict:
    """Run the bounded scan. ``target_row`` is the list row of the target when already resolved.

    ``search``/``service`` count their own upstream calls; exceptions propagate (an upstream
    failure is never turned into "no overruling found").
    """
    max_scan = max(1, min(int(max_scan), MAX_SCAN_LIMIT))
    target_date = normalize_date(target_row.get("선고일자")) if target_row else ""
    own_keys = {key, *co_keys}
    if target_row:
        own_keys |= set(parse_case_numbers(target_row.get("사건번호") or ""))

    forms = case_number_forms(key, (target_row or {}).get("사건번호"), case_text)
    # Quoted = phrase match. Unquoted, short numbers ("70도29") match on their parts: 6,403 rows
    # instead of 3. A joined "94므1713, 1720" citation still matches the phrase "94므1713".
    listed: list[dict] = []
    total = 0
    pages = 0
    query = forms[0]
    for qi, query in enumerate(forms):
        listed, total = [], 0
        for page in range(1, max_pages + 1):
            res = search({"query": f'"{query}"', "search": 2, "display": SEARCH_PAGE_SIZE, "page": page, "sort": "ddes"})
            pages += 1
            total = int(res.get("total") or 0)
            listed += res.get("rows") or []
            if len(listed) >= total or not res.get("rows"):
                break
        if total:
            break           # the other year form (94므1713 / 1994므1713) is tried only when this one finds nothing
    truncated_list = len(listed) < total

    def later(row: dict) -> bool:
        d = normalize_date(row.get("선고일자"))
        if target_date:
            return bool(d) and d > target_date
        rk = row_key(row)
        return bool(rk) and civil_year(rk[0]) >= civil_year(key[0])

    seen_cases: set = set()
    en_banc: list[dict] = []
    other_later: list[dict] = []
    for row in listed:
        rk = row_key(row)
        if rk in own_keys or (rk and rk in seen_cases):
            continue
        if rk:
            seen_cases.add(rk)
        if (row.get("법원명") or "대법원") != "대법원" or not later(row):
            continue
        (en_banc if is_en_banc(row) else other_later).append(row)

    # same case-kind (letter) first, then oldest first: the nearest overruler is the likeliest
    en_banc.sort(key=lambda r: ((row_key(r) or (0, "", 0))[1] != key[1], normalize_date(r.get("선고일자"))))
    to_scan, not_scanned = en_banc[:max_scan], en_banc[max_scan:]

    evidence: list[dict] = []
    leads: list[dict] = []
    cited_only: list[dict] = []
    scanned: list[dict] = []
    unscannable: list[dict] = []
    unreadable: list[dict] = []
    for row in to_scan:
        info = brief(row)
        try:
            fields = service(info["id"])
        except BodyUnreadable as e:
            unreadable.append({**info, "reason": str(e)})
            continue
        if fields is None:
            unscannable.append({**info, "reason": "body not served by the API (NOT_FOUND)"})
            continue
        scanned.append(info)
        found = find_evidence(fields, key)
        for ev in found["explicit"]:
            evidence.append({**ev, "source": info,
                             "confidence": "high" if ev["evidence"] == "explicit_marker" else "medium"})
        if not found["explicit"] and found["soft"]:
            leads.append({"source": info, "cited_as": found["soft"][0], "wording": "soft_change_wording",
                          "generic_change": None})
        elif not found["explicit"] and (found["cited"] or found["generic_change"]):
            departed = [c for c in found["cited"] if c["field"] != "참조판례" and not c.get("supporting")]
            if found["generic_change"] and departed:
                leads.append({"source": info, "cited_as": departed[0], "generic_change": found["generic_change"][0]})
            else:
                cited_only.append({"source": info, "cited_as": found["cited"][0] if found["cited"] else None})

    target_unresolved = target_row is None
    incomplete = bool(truncated_list or not_scanned or unscannable or unreadable)
    if evidence:
        status = OVERRULED_FOUND
    elif leads:
        status = POSSIBLE
    elif target_unresolved:
        status = CASE_NOT_FOUND
    elif incomplete:
        status = INCOMPLETE
    else:
        status = NONE_FOUND

    scope = {
        "method": "prec_search(query=사건번호, search=2 본문 전문검색, 선고일 내림차순) -> 이후 대법원 전원합의체 판결만 prec_service로 본문 확인",
        "query": query,
        "search_rows_total": total,
        "search_rows_listed": len(listed),
        "search_pages_fetched": pages,
        "search_list_truncated": truncated_list,
        "later_en_banc_candidates": len(en_banc),
        "scanned": scanned,
        "not_scanned_en_banc": [brief(r) for r in not_scanned],
        "unscannable": unscannable,
        "unreadable": unreadable,
        "incomplete": incomplete,
        "target_resolved": not target_unresolved,
        "later_non_en_banc_citing_count": len(other_later),
        "later_non_en_banc_citing_not_scanned": [brief(r) for r in other_later[:5]],
        "target_date_known": bool(target_date),
        "max_scan": max_scan,
    }
    return {
        "overruling_status": status,
        "evidence": evidence,
        "leads": leads,
        "cited_without_change_marker": cited_only,
        "searched_scope": scope,
    }


def _incomplete_reasons(scope: dict) -> list[str]:
    reasons = []
    if scope.get("search_list_truncated"):
        reasons.append(f"인용 판결 목록 {scope['search_rows_total']}건 중 {scope['search_rows_listed']}건만 조회")
    if scope.get("not_scanned_en_banc"):
        reasons.append("읽지 않은 후보 전원합의체 판결 " + ", ".join(
            f"{c['case_number']}({c['decision_date']})" for c in scope["not_scanned_en_banc"][:5]))
    if scope.get("unscannable"):
        reasons.append("본문이 제공되지 않은 후보 " + ", ".join(c["case_number"] for c in scope["unscannable"]))
    if scope.get("unreadable"):
        reasons.append("본문을 해석하지 못한 후보 " + ", ".join(c["case_number"] for c in scope["unreadable"]))
    return reasons


def statement(status: str, label: str, scope: dict, n_decisions: int) -> str:
    """``n_decisions`` = number of distinct decisions behind the evidence (not evidence items)."""
    scanned = len(scope["scanned"])
    partial = _incomplete_reasons(scope)
    tail = (" 일부만 확인한 결과입니다: " + "; ".join(partial) + ".") if partial else ""
    if status == OVERRULED_FOUND:
        return (f"{label}: 이후 전원합의체 판결 {n_decisions}건이 이 판례를 변경한다고 표시한 근거가 있습니다(evidence 참조). "
                "인용된 원문을 확인하세요." + tail)
    if status == POSSIBLE:
        return (f"{label}: 이 판례를 명시적으로 변경한다는 표지는 찾지 못했지만, 이를 인용하면서 일반적인 '변경한다' 문장을 둔 "
                "이후 전원합의체 판결이 있습니다(leads). 변경 여부는 확인 필요입니다." + tail)
    if status == CASE_NOT_FOUND:
        return (f"{label}: 법제처 판례 목록에서 이 사건번호를 찾지 못했습니다(색인에 없는 판결이거나 결합사건의 뒤 번호일 수 있습니다; "
                "결합사건이면 첫 번호로 다시 조회). 변경 여부를 확인할 수 없습니다 — 확인 필요."
                + (f" (이 번호를 인용한 판결 {scope['search_rows_total']}건 중 이후 전원합의체 {scanned}건을 읽었지만 변경 표시는 없었습니다.)"
                   if scope["search_rows_total"] else " (이 번호를 인용한 판결도 찾지 못했습니다.)"))
    if status == INCOMPLETE:
        return (f"{label}: 검색이 완전하지 않아 변경 여부를 판단할 수 없습니다 — 확인 필요." + tail)
    return (f"{label}: 검색 범위 내(이 판례를 인용한 이후 대법원 전원합의체 판결 {scope['later_en_banc_candidates']}건 중 "
            f"본문 확인 {scanned}건)에서 변경 표시를 찾지 못했습니다. 변경되지 않았다는 뜻이 아닙니다 — 확인 필요.")


def parse_prec_service(raw: str) -> Optional[dict]:
    """PrecService fields from a prec_service raw_content (JSON); None when not parseable."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    root = next(iter(data.values())) if isinstance(data, dict) and data else None
    return root if isinstance(root, dict) else None


# ---------------------------------------------------------------------------
# wiring used by the MCP tool (kept here so server.py only holds a thin wrapper)
# ---------------------------------------------------------------------------

CAVEATS = [
    "법제처에는 판례 변경을 알려주는 API가 없습니다. 이 도구는 '이후의 대법원 전원합의체 판결이 해당 사건번호를 인용하고 "
    "변경 표시((변경)/(폐기) 또는 같은 문장의 변경한다)를 한 경우'만 찾습니다.",
    "검색은 사건번호 문자열 본문 검색(search=2)에 의존합니다. 인용 표기가 다르거나 결합사건의 뒤 번호만 인용한 경우, "
    "목록에 없는 판결, 본문이 제공되지 않는 판결은 놓칠 수 있습니다.",
    "하급심의 파기·취소, 헌법재판소 결정, 법령 개정으로 인한 판례의 실효·약화는 다루지 않습니다.",
    "no_overruling_found_in_searched_set은 '변경되지 않았다'는 뜻이 아닙니다. 중요한 인용은 직접 확인하세요.",
]


class UpstreamFailure(Exception):
    """Carries the error response of a failed upstream call out of the scan."""

    def __init__(self, response: dict):
        super().__init__(str(response.get("message", "upstream error")))
        self.response = response


def run_prec_status(*, get_client, oc: str, case_number: Optional[str], prec_id: Optional[str],
                    max_scan: int = DEFAULT_MAX_SCAN) -> dict:
    """Resolve the target, run :func:`check_status` and shape the tool response."""
    from ._helpers import ToolValidationError, run_service
    from .cache import get_cache
    from .errors import ErrorCode
    from .params import map_params_to_upstream

    if not case_number and not prec_id:
        raise ToolValidationError("case_number (사건번호) 또는 id (판례일련번호) 중 하나가 필요합니다.",
                                  hints=["예: case_number='94므1713' 또는 id='111970'"])
    calls = {"n": 0}
    cache = get_cache()
    holder: list = []

    def client():
        if not holder:
            holder.append(get_client())
        return holder[0]

    def search(params: dict) -> dict:
        snake = {"oc": oc, "target": "prec", "type": "JSON", **params}
        up = map_params_to_upstream(snake)
        resp = cache.get("prec", up)
        if resp is None:
            calls["n"] += 1
            resp = client().get("/DRF/lawSearch.do", up, "JSON")
            cache.put("prec", up, resp)
        if resp.get("status") != "ok":
            raise UpstreamFailure(resp)
        try:
            body = json.loads(resp.get("raw_content") or "{}")
        except ValueError:
            raise UpstreamFailure({"status": "error", "error_code": ErrorCode.UPSTREAM_ERROR,
                                   "message": "prec_search 응답을 해석할 수 없습니다."})
        root = next(iter(body.values())) if isinstance(body, dict) and body else {}
        root = root if isinstance(root, dict) else {}
        return {"total": root.get("totalCnt") or 0, "rows": _rows(root)}

    def service(prec_id_: str) -> Optional[dict]:
        snake = {"oc": oc, "target": "prec", "id": str(prec_id_), "type": "JSON"}
        res = run_service(get_client=client, target="prec", snake_params=snake, response_type="JSON")
        calls["n"] += 1
        if res.get("status") != "ok":
            if res.get("error_code") == ErrorCode.NOT_FOUND:
                return None
            raise UpstreamFailure(res)
        fields = parse_prec_service(res.get("raw_content", ""))
        if fields is None:
            raise BodyUnreadable(f"판례일련번호 {prec_id_}: 응답(200)을 판례 본문으로 해석하지 못함")
        return fields

    def parse_or_fail(text: str):
        try:
            return parse_target(text)
        except ValueError as e:
            raise ToolValidationError(str(e), hints=["예: '94므1713', '대법원 1995. 5. 23. 선고 94므1713 판결', '2013므2250'"])

    prec_id = str(prec_id).strip() if prec_id not in (None, "") else None
    if prec_id and not re.fullmatch(r"\d{1,12}", prec_id):
        raise ToolValidationError(f"id는 숫자인 판례일련번호여야 합니다: {prec_id!r}",
                                  hints=["판례일련번호는 prec_search 결과의 판례일련번호입니다(행 번호 아님)."])
    try:
        target_row: Optional[dict] = None
        if prec_id:
            try:
                target_fields = service(prec_id)
            except BodyUnreadable as e:
                return {"status": "error", "error_code": ErrorCode.UPSTREAM_ERROR, "message": str(e)}
            if target_fields is None:
                return {"status": "error", "error_code": ErrorCode.NOT_FOUND,
                        "message": f"판례일련번호 {prec_id}의 본문을 찾을 수 없습니다.",
                        "hints": ["판례일련번호는 prec_search 결과의 판례일련번호입니다(행 번호 아님)."]}
            case_text = target_fields.get("사건번호") or ""
            key, co_keys = parse_or_fail(case_text)
            target_row = {"사건번호": case_text, "선고일자": target_fields.get("선고일자"),
                          "판례일련번호": prec_id, "판결유형": target_fields.get("판결유형"),
                          "법원명": target_fields.get("법원명"), "사건명": target_fields.get("사건명")}
        else:
            case_text = case_number or ""
            key, co_keys = parse_or_fail(case_text)
            # the index writes pre-2000 numbers with two-digit years (94므1713); a citation or a user
            # may write 1994므1713, so both spellings are tried (the second only if the first finds nothing)
            for form in case_number_forms(key):
                res = search({"nb": form, "display": 20})
                exact = [r for r in res["rows"] if key in parse_case_numbers(r.get("사건번호") or "")]
                if exact:
                    target_row = exact[0]
                    break

        out = check_status(key=key, co_keys=co_keys, case_text=case_text, search=search, service=service,
                           target_row=target_row, max_scan=max_scan)
    except UpstreamFailure as f:
        resp = dict(f.response)
        resp.setdefault("status", "error")
        resp["message"] = (f"{resp.get('message', '')} (prec_status 중단: 업스트림 오류는 '변경 없음'으로 처리하지 않습니다.)")
        return resp

    label = (target_row or {}).get("사건번호") or case_number_forms(key)[0]
    caveats = list(CAVEATS)
    if target_row is None:
        caveats.insert(0, f"사건번호 {label}는 법제처 판례 목록(nb 검색, 두 자리·네 자리 연도 모두)에서 찾지 못해 선고일을 알 수 없습니다. "
                          f"결합사건의 뒤 번호이면 첫 번호로 조회하세요. 사건번호 연도 {key[0]}년 이후의 결정만 후보로 삼았습니다.")
    if co_keys:
        caveats.append("결합사건 번호가 함께 입력되었습니다: " + ", ".join(format_case_key(k) for k in co_keys)
                       + ". 첫 번호 기준으로 검색하고, 인용문에서는 결합 번호도 같은 사건으로 보았습니다.")
    scope = out["searched_scope"]
    if scope["search_list_truncated"]:
        caveats.append(f"인용 판결 목록 {scope['search_rows_total']}건 중 {scope['search_rows_listed']}건만 조회했습니다.")
    if scope["not_scanned_en_banc"]:
        caveats.append(f"후보 전원합의체 판결 {scope['later_en_banc_candidates']}건 중 "
                       f"{len(scope['scanned']) + len(scope['unscannable']) + len(scope['unreadable'])}건만 본문을 확인했습니다"
                       "(not_scanned_en_banc 참조). max_scan을 늘려 다시 조회할 수 있습니다.")
    if scope["unreadable"]:
        caveats.append("후보 판결의 응답을 해석하지 못했습니다: " + ", ".join(c["case_number"] for c in scope["unreadable"]))
    n_decisions = len({e["source"]["id"] for e in out["evidence"]})
    target = brief(target_row) if target_row else {"case_number": label, "id": "", "decision_date": "",
                                                     "decision_type": "", "court": "", "case_name": ""}
    target["found_in_index"] = target_row is not None
    return {
        "status": "ok",
        "overruling_status": out["overruling_status"],
        "statement": statement(out["overruling_status"], label, scope, n_decisions),
        "target": target,
        "evidence": out["evidence"],
        "leads": out["leads"],
        "cited_without_change_marker": out["cited_without_change_marker"],
        "searched_scope": scope,
        "upstream_calls": calls["n"],
        "caveats": caveats,
        "evidence_note": "quote는 업스트림 본문을 그대로 옮긴 것입니다(<br/> 제거, 공백만 정리).",
    }
