"""Constitutional Court (헌재) decisions on one statute article, for ``law_constitutional_check``.

``law_as_of`` reads eflaw 시행일 data, which does not show an article that 헌재 struck down (e.g.
형법 제241조, 2015-02-26). This module finds the 헌재 decisions that deal with the article and reads
the outcome from the 주문. It is a lead generator: the 주문 of a decision that decides several
provisions is attributed to the article clause by clause, and the legal effect (소급효, 헌법불합치의
잠정적용 시한, later amendment) is not computed.

Pipeline (bounded):

1. resolve ``law_name`` to the official name (``law_search``; abbreviations such as 가족관계등록법
   work, an unknown name is an error, never a clean result);
2. one ``detc_search`` full-text list (quoted phrase ``"<법령명> 제N조"``, one page of 100, newest first);
3. candidates = rows whose 사건명 names the law and the article, then rows whose 사건명 names the law
   (``민법 제1112조 등 위헌제청`` can decide 제1118조) and that the quoted-phrase list returned;
4. ``detc_service`` for up to ``max_scan`` candidates, classify the 주문; a candidate found only through
   its 사건명 naming the law must name the article in its 주문 or 심판대상조문, otherwise it is dropped.

Anything not read (list truncated, candidates beyond ``max_scan``, body not served) makes the result
``incomplete_search``, never a clean "no adverse decision".
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

ADVERSE = ("위헌", "헌법불합치", "한정위헌")
DEFAULT_MAX_SCAN = 8
MAX_SCAN_LIMIT = 12
SEARCH_PAGE_SIZE = 100

ADVERSE_FOUND = "adverse_decision_found"
NEEDS_REVIEW = "needs_review"
INCOMPLETE = "incomplete_search"
NONE_FOUND = "no_adverse_decision_in_searched_set"

_WS = re.compile(r"[\s　]+")


def _sq(text: Any) -> str:
    return _WS.sub("", str(text or ""))


def _law_rx(law_name: str) -> str:
    return r"\s*".join(re.escape(ch) for ch in _sq(law_name))


def _article_rx(article: int, branch: int) -> str:
    return rf"제\s*{article}\s*조" + (rf"\s*의\s*{branch}(?!\d)" if branch else r"(?!\s*의\s*\d|\d)")


def law_article_pattern(law_name: str, article: int, branch: int) -> re.Pattern:
    """'<법령명>[(개정사항)] 제N조[의B]' (not inside a longer name such as 군형법; optional 구 prefix)."""
    return re.compile(rf"(?<![가-힣])(?:구\s*)?{_law_rx(law_name)}\s*(?:\([^)]*\)\s*)?{_article_rx(article, branch)}")


def title_names_article(title: str, law_name: str, article: int, branch: int) -> bool:
    """Does a 사건명 such as '민법 제847조 제1항 위헌소원' name this law's article?

    '구 형법', '구 민법(…)' prefixes are accepted; 제241조 must not match 제241조의2 or 제1241조,
    and 민법 must not match 민법 시행령.
    """
    if not _sq(law_name):
        return False
    return law_article_pattern(law_name, article, branch).search(title or "") is not None


def title_names_law(title: str, law_name: str) -> bool:
    """사건명 names the law itself (any article, e.g. '민법 제1112조 등 위헌제청'), not its 시행령/시행규칙."""
    if not _sq(law_name):
        return False
    return re.search(rf"(?<![가-힣])(?:구\s*)?{_law_rx(law_name)}(?!\s*시행|[가-힣])", title or "") is not None


_ORDER_RE = re.compile(r"[\[【]\s*주\s*문\s*[\]】](.*?)[\[【]\s*이\s*유\s*[\]】]", re.S)
# Older 전문 texts have no brackets: "주           문이 사건 심판청구를 각하한다.이           유기록에 ..."
_ORDER_SPACED_RE = re.compile(r"주\s{2,}문(.*?)이\s{2,}유", re.S)
_OUTCOME_RULES = (
    # (label, regex); on overlapping matches the earlier rule wins
    ("헌법불합치", re.compile(r"헌법에\s*합치되지\s*아니(?:한다|하나|하고|하며)")),
    ("한정위헌", re.compile(r"(?:해석(?:하는|되는)?\s*한|범위\s*내에서|범위에서)[^.]{0,80}헌법에\s*위반(?:된다|됨)|한정\s*위헌")),
    ("위헌", re.compile(r"헌법에\s*위반된다|위헌임을\s*확인")),
    ("합헌", re.compile(r"헌법에\s*위반되지\s*아니(?:한다|하나|하고|하며)")),
    ("각하", re.compile(r"각하한다|각하\s*결정")),
    ("기각", re.compile(r"기각한다")),
)
_ANY_ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+)(?!\d))?")


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", str(text or ""))).strip()


def extract_order(fields: dict) -> str:
    """The 주문 text of a detc_service body ('' when the 전문 has no recognizable 주문 section)."""
    text = str(fields.get("전문") or "")
    m = _ORDER_RE.search(text) or _ORDER_SPACED_RE.search(text)
    return _clean(m.group(1)) if m else ""


def _outcome_matches(sentence: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for label, rx in _OUTCOME_RULES:
        for m in rx.finditer(sentence):
            if not any(m.start() < e and s < m.end() for s, e, _ in found):
                found.append((m.start(), m.end(), label))
    return sorted(found)


def classify_order(order: str, article: int, branch: int, law_name: Optional[str] = None) -> dict:
    """Outcomes of the 주문 that belong to ``제N조[의B]``.

    Inside a sentence every outcome ("…은 헌법에 위반된다") belongs to the article reference(s) just
    before it, so "제1조는 합헌이나 제2조는 위헌" gives 제1조 합헌 and 제2조 위헌, and
    "제2조 및 제3조는 위헌" gives both. Outcomes with no article before them ("이 사건 심판청구를
    각하한다", "위 법률조항은 …") are ``unattributed``. ``outcomes`` is what is attributed to this
    article; an adverse unattributed outcome only sets ``needs_review``.
    """
    if not order:
        return {"outcomes": [], "unattributed": [], "article_specific": False, "needs_review": False}
    # 주문 sentences end in "…다."; dates such as "1958. 2. 22. 법률 제471호" must not split a sentence
    sentences = [s.strip() for s in re.split(r"(?<=다)\.\s*", order) if s.strip()]
    law_pat = law_article_pattern(law_name, article, branch) if law_name else None
    mine: list[dict] = []
    unattributed: list[dict] = []
    for s in sentences:
        events: list[tuple[int, str, Any]] = []
        for m in _ANY_ARTICLE_RE.finditer(s):
            events.append((m.start(), "ref", (int(m.group(1)), int(m.group(2) or 0))))
        for st, _en, label in _outcome_matches(s):
            events.append((st, "out", label))
        events.sort(key=lambda e: (e[0], e[1] == "out"))
        other_law = ("시행령" in s or "시행규칙" in s) and not (law_pat and law_pat.search(s))
        group: list[tuple[int, int]] = []
        for _pos, kind, val in events:
            if kind == "ref":
                group.append(val)
                continue
            rec = {"outcome": val, "sentence": s[:400]}
            if not group:
                unattributed.append(rec)
            elif (article, branch) in group and not other_law:
                mine.append(rec)
            group = []
    adverse_unattributed = [u for u in unattributed if u["outcome"] in ADVERSE]
    if mine:
        return {"outcomes": mine, "unattributed": unattributed, "article_specific": True,
                "needs_review": bool(adverse_unattributed)}
    return {"outcomes": unattributed, "unattributed": unattributed, "article_specific": False,
            "needs_review": bool(adverse_unattributed)}


def names_article(text: str, law_name: str, article: int, branch: int) -> bool:
    """Does a 주문 / 심판대상조문 text name this law's article (law-aware when the law is spelled out)?"""
    if law_article_pattern(law_name, article, branch).search(text or ""):
        return True
    # bare "제1118조" in a text that spelled the law out earlier ("민법(…) 제1112조 … 제1118조")
    return bool(re.search(_article_rx(article, branch), text or "")
                and re.search(rf"(?<![가-힣])(?:구\s*)?{_law_rx(law_name)}(?!\s*시행|[가-힣])", text or ""))


def decision_record(row: dict, fields: dict, article: int, branch: int, law_name: str) -> dict:
    order = extract_order(fields)
    cls = classify_order(order, article, branch, law_name)
    labels = [o["outcome"] for o in cls["outcomes"]]
    adverse = [o for o in labels if o in ADVERSE] if cls["article_specific"] else []
    return {
        "case_number": fields.get("사건번호") or row.get("사건번호", ""),
        "id": str(row.get("헌재결정례일련번호") or fields.get("헌재결정례일련번호") or ""),
        "decision_date": re.sub(r"\D", "", str(fields.get("종국일자") or row.get("종국일자") or ""))[:8],
        "case_name": _clean(fields.get("사건명") or row.get("사건명")),
        "target_provisions": _clean(fields.get("심판대상조문")),
        "outcomes": cls["outcomes"],
        "outcome": ("/".join(dict.fromkeys(labels)) if labels else "불명"),
        "article_specific": cls["article_specific"],
        "adverse": bool(adverse),
        # a decision whose 주문 could not be read (outcome 불명) must never read as clean
        "needs_review": bool((cls["needs_review"] or not labels) and not adverse),
        "needs_review_reason": ("주문을 읽지 못했거나 결과를 분류하지 못했습니다(outcome 불명)"
                                if not labels and not adverse else None),
        "order": order[:500],
        "holding_note": _clean(fields.get("판시사항"))[:300],
    }


SearchFn = Callable[[dict], dict]       # params -> {"total": int, "rows": [row, ...]}
ServiceFn = Callable[[str], Optional[dict]]  # 헌재결정례일련번호 -> fields (None = body not served)


def _date_key(row: dict) -> str:
    return re.sub(r"\D", "", str(row.get("종국일자") or ""))


def check_article(*, law_name: str, article: int, branch: int, search: SearchFn, service: ServiceFn,
                  max_scan: int = DEFAULT_MAX_SCAN, alias: Optional[str] = None) -> dict:
    max_scan = max(1, min(int(max_scan), MAX_SCAN_LIMIT))
    label = f"제{article}조" + (f"의{branch}" if branch else "")
    phrase = f"{law_name} {label}"
    q_phrase = search({"query": f'"{phrase}"', "search": 2, "display": SEARCH_PAGE_SIZE, "page": 1, "sort": "ddes"})
    # the unquoted words list adds nothing (same 사건명 matches in 7 of 7 articles compared) and is mostly noise
    lists = [q_phrase]
    truncated = any(len(r.get("rows") or []) < int(r.get("total") or 0) for r in lists)

    def names(row_title: str, art=True) -> bool:
        ok = title_names_article(row_title, law_name, article, branch)
        if not ok and alias:
            ok = title_names_article(row_title, alias, article, branch)
        return ok

    seen: set = set()
    tier1: list[dict] = []
    tier2: list[dict] = []
    for r in q_phrase.get("rows") or []:
        rid = str(r.get("헌재결정례일련번호"))
        if rid in seen:
            continue
        seen.add(rid)
        if names(r.get("사건명", "")):
            tier1.append(r)
    tier1_ids = {str(x.get("헌재결정례일련번호")) for x in tier1}
    for r in q_phrase.get("rows") or []:
        rid = str(r.get("헌재결정례일련번호"))
        if rid not in tier1_ids and (
                title_names_law(r.get("사건명", ""), law_name) or (alias and title_names_law(r.get("사건명", ""), alias))):
            tier2.append(r)
    tier1.sort(key=_date_key, reverse=True)
    tier2.sort(key=_date_key, reverse=True)
    cands = [(r, 1) for r in tier1] + [(r, 2) for r in tier2]
    to_scan, rest = cands[:max_scan], cands[max_scan:]

    records, unscannable, dropped = [], [], []
    for r, tier in to_scan:
        fields = service(str(r.get("헌재결정례일련번호")))
        if fields is None:
            unscannable.append({"case_number": r.get("사건번호", ""), "id": str(r.get("헌재결정례일련번호", "")),
                                "case_name": r.get("사건명", "")})
            continue
        if tier == 2 and not (names_article(extract_order(fields), law_name, article, branch)
                              or names_article(fields.get("심판대상조문") or "", law_name, article, branch)):
            dropped.append({"case_number": r.get("사건번호", ""), "case_name": _clean(r.get("사건명"))})
            continue
        rec = decision_record(r, fields, article, branch, law_name)
        rec["found_via"] = "사건명" if tier == 1 else "본문 검색 + 주문/심판대상조문"
        records.append(rec)
    adverse = [x for x in records if x["adverse"]]
    review = [x for x in records if x["needs_review"]]
    incomplete = bool(truncated or rest or unscannable)
    if adverse:
        status = ADVERSE_FOUND
    elif review:
        status = NEEDS_REVIEW
    elif incomplete:
        status = INCOMPLETE
    else:
        status = NONE_FOUND
    return {
        "article": f"{law_name} {label}",
        "decisions": records,
        "adverse_decisions": adverse,
        "needs_review_decisions": review,
        "decision_status": status,
        "searched_scope": {
            "query": f'"{phrase}" (detc_search search=2, quoted phrase)',
            "search_rows_total": int(q_phrase.get("total") or 0),
            "search_rows_listed": len(q_phrase.get("rows") or []),
            "title_matches": len(tier1),
            "law_title_matches_from_phrase_search": len(tier2),
            "scanned": len(records),
            "dropped_no_article_in_order": dropped,
            "unscannable": unscannable,
            "not_scanned": [{"case_number": r.get("사건번호", ""), "id": str(r.get("헌재결정례일련번호", "")),
                             "decision_date": _date_key(r), "case_name": r.get("사건명", "")} for r, _ in rest],
            "list_truncated": truncated,
            "incomplete": incomplete,
            "max_scan": max_scan,
        },
    }


CAVEATS = [
    "단서(lead)입니다. law_as_of의 in_force는 바꾸지 않습니다. 인용 전에 헌재 결정 원문(주문)과 이후 법령 개정을 확인하세요.",
    "현행 조문은 결정 이후 개정(헌법불합치에 따른 개선입법, 위헌 조문의 삭제 등)되었을 수 있습니다. 결정일 이후의 조문은 "
    "law_as_of / law_amendment_summary로 확인하세요(각 결정의 판단 대상은 결정 당시 조문입니다).",
    "후보는 사건명에 법령명(과 조문)이 있는 결정, 그리고 본문 검색(\"법령명 제N조\")에서 나온 결정 중 주문·심판대상조문에 조문이 "
    "있는 결정입니다. 사건명에 법령명이 없는 결정, 구법 명칭으로만 쓰인 결정은 놓칠 수 있습니다.",
    "여러 조항을 함께 판단한 결정의 주문은 조문 앞 문맥으로 연결합니다. 조문을 지목하지 못한 위헌·헌법불합치 주문은 "
    "needs_review로 표시하며 이 조문의 결과로 단정하지 않습니다.",
    "위헌결정의 효력 시점(소급효: 형벌조항은 직전 합헌결정 다음 날), 헌법불합치의 잠정적용·개선입법 시한은 계산하지 않습니다.",
    "no_adverse_decision_in_searched_set은 헌재에서 위헌 판단을 받지 않았다는 뜻이 아닙니다.",
]


def parse_detc_service(raw: str) -> Optional[dict]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    root = next(iter(data.values())) if isinstance(data, dict) and data else None
    return root if isinstance(root, dict) else None


def resolve_official_name(name: str, rows: list) -> Optional[tuple]:
    """(official 법령명, how) from law_search rows: exact name first, then 법령약칭명; None if neither."""
    sq = _sq(name)
    for r in rows:
        if _sq(r.get("법령명한글")) == sq:
            return r.get("법령명한글"), "exact"
    for r in rows:
        if _sq(r.get("법령약칭명")) == sq:
            return r.get("법령명한글"), "abbreviation"
    return None


def run_constitutional_check(*, get_client, oc: str, law_name: str, article, article_branch=0,
                             max_scan: int = DEFAULT_MAX_SCAN) -> dict:
    """Wire :func:`check_article` to law_search / detc_search / detc_service and shape the tool response."""
    from ._helpers import ToolValidationError, run_service
    from .article_text import normalize_article
    from .cache import get_cache
    from .errors import ErrorCode
    from .params import map_params_to_upstream
    from .precedent_status import UpstreamFailure
    from .resolver import get_resolver

    name = (law_name or "").strip()
    if not name:
        raise ToolValidationError("law_name (법령명)이 필요합니다.", hints=["예: law_name='형법', article=241"])
    if article in (None, ""):
        raise ToolValidationError("article (조문)이 필요합니다.", hints=["예: article=241 또는 '제241조'"])
    num, branch = normalize_article(article, article_branch)
    calls = {"n": 0}
    cache = get_cache()
    holder: list = []

    def client():
        if not holder:
            holder.append(get_client())
        return holder[0]

    def fetch(target: str, params: dict) -> dict:
        up = map_params_to_upstream({"oc": oc, "target": target, "type": "JSON", **params})
        resp = cache.get(target, up)
        if resp is None:
            calls["n"] += 1
            resp = client().get("/DRF/lawSearch.do", up, "JSON")
            cache.put(target, up, resp)
        if resp.get("status") != "ok":
            raise UpstreamFailure(resp)
        try:
            body = json.loads(resp.get("raw_content") or "{}")
        except ValueError:
            raise UpstreamFailure({"status": "error", "error_code": ErrorCode.UPSTREAM_ERROR,
                                   "message": f"{target} 검색 응답을 해석할 수 없습니다."})
        root = next(iter(body.values())) if isinstance(body, dict) and body else {}
        return root if isinstance(root, dict) else {}

    def search(params: dict) -> dict:
        root = fetch("detc", params)
        rows = root.get("Detc", [])
        rows = [rows] if isinstance(rows, dict) else rows
        return {"total": root.get("totalCnt") or 0, "rows": [r for r in rows if isinstance(r, dict)]}

    def service(detc_id: str) -> Optional[dict]:
        res = run_service(get_client=client, target="detc", response_type="JSON",
                          snake_params={"oc": oc, "target": "detc", "id": detc_id, "type": "JSON"})
        calls["n"] += 1
        if res.get("status") != "ok":
            if res.get("error_code") == ErrorCode.NOT_FOUND:
                return None
            raise UpstreamFailure(res)
        fields = parse_detc_service(res.get("raw_content", ""))
        if fields is None:
            raise UpstreamFailure({"status": "error", "error_code": ErrorCode.UPSTREAM_ERROR,
                                   "message": f"detc_service {detc_id} 응답(200)을 결정문으로 해석하지 못했습니다."})
        return fields

    try:
        aliased = get_resolver().resolve(name)
        lroot = fetch("law", {"query": aliased or name, "display": 20})
        lrows = lroot.get("law", [])
        lrows = [lrows] if isinstance(lrows, dict) else lrows
        resolved = resolve_official_name(name, [r for r in lrows if isinstance(r, dict)]) or (
            resolve_official_name(aliased, [r for r in lrows if isinstance(r, dict)]) if aliased else None)
        if not resolved:
            names = [r.get("법령명한글") for r in lrows if isinstance(r, dict)][:5]
            return {"status": "error", "error_code": ErrorCode.VALIDATION_ERROR,
                    "message": f"법령명 '{name}'을(를) 공식 법령명이나 약칭으로 확인하지 못했습니다. 위헌 결정 없음으로 처리하지 않습니다.",
                    "hints": ["정식 법령명으로 다시 조회하세요" + (f" (검색된 이름: {', '.join(names)})" if names else "")]}
        official, how = resolved
        out = check_article(law_name=official, article=num, branch=branch, search=search, service=service,
                            max_scan=max_scan, alias=name if _sq(name) != _sq(official) else None)
    except UpstreamFailure as f:
        resp = dict(f.response)
        resp.setdefault("status", "error")
        resp["message"] = (f"{resp.get('message', '')} (law_constitutional_check 중단: "
                           "업스트림 오류는 '위헌 결정 없음'으로 처리하지 않습니다.)")
        return resp
    scope = out["searched_scope"]
    scope["law_name_input"] = name
    scope["law_name_official"] = official
    scope["law_name_resolved_by"] = how
    caveats = list(CAVEATS)
    if how != "exact":
        caveats.insert(0, f"법령명 '{name}'은 약칭으로, 공식 법령명 '{official}'로 조회했습니다.")
    if scope["not_scanned"]:
        caveats.append(f"후보 {scope['title_matches'] + scope['law_title_matches_from_phrase_search']}건 중 "
                       f"{scope['scanned'] + len(scope['unscannable']) + len(scope['dropped_no_article_in_order'])}건만 읽었습니다"
                       "(not_scanned 참조). max_scan을 늘려 다시 조회할 수 있습니다.")
    if scope["list_truncated"]:
        caveats.append(f"검색 결과 {scope['search_rows_total']}건 중 {scope['search_rows_listed']}건만 조회했습니다.")
    if scope["unscannable"]:
        caveats.append("본문이 제공되지 않은 후보: " + ", ".join(c["case_number"] for c in scope["unscannable"]))
    status = out["decision_status"]
    if status == ADVERSE_FOUND:
        d = out["adverse_decisions"][0]
        statement = (f"{out['article']}: 헌재 결정 중 위헌·헌법불합치 단서 {len(out['adverse_decisions'])}건 "
                     f"(예: {d['case_number']}, {d['decision_date']}, {d['outcome']}). 단서이며 확인이 필요합니다. "
                     "결정 이후 조문이 개정되었을 수 있습니다.")
    elif status == NEEDS_REVIEW:
        d = out["needs_review_decisions"][0]
        statement = (f"{out['article']}: {d['case_number']}({d['decision_date']})의 주문에 위헌·헌법불합치가 있으나 이 조문에 "
                     "연결하지 못했습니다(needs_review). 주문을 직접 확인하세요.")
    elif status == INCOMPLETE:
        statement = (f"{out['article']}: 검색이 완전하지 않아 위헌·헌법불합치 결정 여부를 판단할 수 없습니다(읽은 결정 "
                     f"{scope['scanned']}건) — 확인 필요. 읽지 못한 부분은 searched_scope와 caveats 참조.")
    else:
        statement = (f"{out['article']}: 검색한 범위(읽은 결정 {scope['scanned']}건)에서 위헌·헌법불합치 결정을 찾지 못했습니다. "
                     "위헌 판단이 없었다는 뜻이 아닙니다 — 확인 필요.")
    return {"status": "ok", **out, "statement": statement, "upstream_calls": calls["n"], "caveats": caveats}
