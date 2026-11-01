"""Constitutional Court (헌재) decisions on one statute article, for ``law_constitutional_check``.

``law_as_of`` reads eflaw 시행일 data, which does not show an article that 헌재 struck down (e.g.
형법 제241조, 2015-02-26). This module finds the 헌재 decisions that name the article and reads the
outcome from the 주문. It is a lead generator: the search is by 사건명 text, the 주문 of a decision
that decides several provisions is attributed to the article only by sentence matching, and the
legal effect (소급효, 헌법불합치의 잠정적용 시한, later amendment) is not computed.

Pipeline (bounded): ``detc_search query="<법령명> 제N조" search=2`` (one page of 100, newest first)
-> keep rows whose 사건명 names the law and the article -> ``detc_service`` for up to ``max_scan``
of them -> classify the 주문.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

ADVERSE = ("위헌", "헌법불합치", "한정위헌")
DEFAULT_MAX_SCAN = 6
MAX_SCAN_LIMIT = 10
SEARCH_PAGE_SIZE = 100

_WS = re.compile(r"[\s　]+")


def _sq(text: Any) -> str:
    return _WS.sub("", str(text or ""))


def title_names_article(title: str, law_name: str, article: int, branch: int) -> bool:
    """Does a 사건명 such as '민법 제847조 제1항 위헌소원' name this law's article?

    '구 형법', '구 민법(…)' prefixes are accepted; 제241조 must not match 제241조의2 or 제1241조.
    """
    law = _sq(law_name)
    if not law:
        return False
    law_rx = r"\s*".join(re.escape(ch) for ch in law)
    ref = rf"제\s*{article}\s*조" + (rf"\s*의\s*{branch}(?!\d)" if branch else r"(?!\s*의\s*\d|\d)")
    # not inside a longer law name (군형법), optional 구 prefix and "(2005. 3. 31. 법률 제7427호로 개정된 것)"
    pattern = rf"(?<![가-힣])(?:구\s*)?{law_rx}\s*(?:\([^)]*\)\s*)?{ref}"
    return re.search(pattern, title or "") is not None


_ORDER_RE = re.compile(r"[\[【]\s*주\s*문\s*[\]】](.*?)[\[【]\s*이\s*유\s*[\]】]", re.S)
_OUTCOME_RULES = (
    # (label, regex) checked per sentence of the 주문, most specific first
    ("헌법불합치", re.compile(r"헌법에\s*합치되지\s*아니한다")),
    ("한정위헌", re.compile(r"(?:해석(?:하는|되는)?\s*한|범위\s*내에서|범위에서)[^.]*헌법에\s*위반(?:된다|됨)|한정\s*위헌")),
    ("위헌", re.compile(r"헌법에\s*위반된다|위헌임을\s*확인")),
    ("합헌", re.compile(r"헌법에\s*위반되지\s*아니한다")),
    ("각하", re.compile(r"각하한다|각하\s*결정")),
    ("기각", re.compile(r"기각한다")),
)


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", str(text or ""))).strip()


def extract_order(fields: dict) -> str:
    """The 주문 text of a detc_service body ('' when the 전문 has no recognizable 주문 section)."""
    m = _ORDER_RE.search(str(fields.get("전문") or ""))
    return _clean(m.group(1)) if m else ""


def classify_order(order: str, article: int, branch: int) -> dict:
    """Outcomes found in the 주문, with the sentence that carries each.

    ``article_specific`` is true when an outcome comes from a sentence naming this article; with a
    several-provision 주문 and no sentence naming it, the outcomes of the whole 주문 are returned
    with ``article_specific`` false (attribution to the article is then unverified).
    """
    if not order:
        return {"outcomes": [], "article_specific": False}
    # 주문 sentences end in "…다."; dates such as "1958. 2. 22. 법률 제471호" must not split a sentence
    sentences = [s.strip() for s in re.split(r"(?<=다)\.\s*", order) if s.strip()]
    ref = re.compile(rf"제\s*{article}\s*조" + (rf"\s*의\s*{branch}(?!\d)" if branch else r"(?!\s*의\s*\d)"))

    def scan(sents: list) -> list:
        found = []
        for s in sents:
            for label, rx in _OUTCOME_RULES:
                if rx.search(s):
                    found.append({"outcome": label, "sentence": s[:400]})
                    break
        return found

    named = [s for s in sentences if ref.search(s)]
    specific = scan(named)
    if specific:
        return {"outcomes": specific, "article_specific": True}
    return {"outcomes": scan(sentences), "article_specific": False}


def decision_record(row: dict, fields: dict, article: int, branch: int) -> dict:
    order = extract_order(fields)
    cls = classify_order(order, article, branch)
    labels = [o["outcome"] for o in cls["outcomes"]]
    adverse = [o for o in labels if o in ADVERSE]
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
        "order": order[:500],
        "holding_note": _clean(fields.get("판시사항"))[:300],
    }


SearchFn = Callable[[dict], dict]       # params -> {"total": int, "rows": [row, ...]}
ServiceFn = Callable[[str], Optional[dict]]  # 헌재결정례일련번호 -> fields (None = body not served)


def check_article(*, law_name: str, article: int, branch: int, search: SearchFn, service: ServiceFn,
                  max_scan: int = DEFAULT_MAX_SCAN) -> dict:
    max_scan = max(1, min(int(max_scan), MAX_SCAN_LIMIT))
    label = f"제{article}조" + (f"의{branch}" if branch else "")
    query = f"{law_name} {label}"
    res = search({"query": query, "search": 2, "display": SEARCH_PAGE_SIZE, "page": 1, "sort": "ddes"})
    rows = res.get("rows") or []
    total = int(res.get("total") or 0)
    cands = [r for r in rows if title_names_article(r.get("사건명", ""), law_name, article, branch)]
    to_scan, rest = cands[:max_scan], cands[max_scan:]
    records, unscannable = [], []
    for r in to_scan:
        fields = service(str(r.get("헌재결정례일련번호")))
        if fields is None:
            unscannable.append({"case_number": r.get("사건번호", ""), "id": str(r.get("헌재결정례일련번호", "")),
                                "case_name": r.get("사건명", "")})
            continue
        records.append(decision_record(r, fields, article, branch))
    adverse = [x for x in records if x["adverse"]]
    return {
        "article": f"{law_name} {label}",
        "decisions": records,
        "adverse_decisions": adverse,
        "decision_status": "adverse_decision_found" if adverse else "no_adverse_decision_in_searched_set",
        "searched_scope": {
            "query": query,
            "search_rows_total": total,
            "search_rows_listed": len(rows),
            "title_matches": len(cands),
            "scanned": len(records),
            "unscannable": unscannable,
            "not_scanned": [{"case_number": r.get("사건번호", ""), "id": str(r.get("헌재결정례일련번호", "")),
                             "decision_date": re.sub(r"\D", "", r.get("종국일자", "")), "case_name": r.get("사건명", "")}
                            for r in rest],
            "list_truncated": len(rows) < total,
            "max_scan": max_scan,
        },
    }


CAVEATS = [
    "단서(lead)입니다. law_as_of의 in_force는 바꾸지 않습니다. 인용 전에 헌재 결정 원문(주문)과 이후 법령 개정을 확인하세요.",
    "사건명에 법령명과 조문 번호가 있는 결정만 후보로 삼습니다. 사건명에 조문이 드러나지 않는 결정(‘등’으로 묶인 조문, 입법부작위, 법령 개정 전 구법 명칭)은 놓칠 수 있습니다.",
    "여러 조항을 함께 판단한 결정의 주문은 문장 단위로 해당 조문에 연결합니다(article_specific=false면 조문과의 연결 미확인).",
    "위헌결정의 효력 시점(소급효: 형벌조항은 직전 합헌결정 다음 날), 헌법불합치의 잠정적용·개선입법 시한, 이후 개정 여부는 계산하지 않습니다.",
    "no_adverse_decision_in_searched_set은 헌재에서 위헌 판단을 받지 않았다는 뜻이 아닙니다.",
]


def parse_detc_service(raw: str) -> Optional[dict]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    root = next(iter(data.values())) if isinstance(data, dict) and data else None
    return root if isinstance(root, dict) else None


def run_constitutional_check(*, get_client, oc: str, law_name: str, article, article_branch=0,
                             max_scan: int = DEFAULT_MAX_SCAN) -> dict:
    """Wire :func:`check_article` to detc_search / detc_service and shape the tool response."""
    from ._helpers import ToolValidationError, run_service
    from .article_text import normalize_article
    from .cache import get_cache
    from .errors import ErrorCode
    from .params import map_params_to_upstream
    from .precedent_status import UpstreamFailure

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

    def search(params: dict) -> dict:
        up = map_params_to_upstream({"oc": oc, "target": "detc", "type": "JSON", **params})
        resp = cache.get("detc", up)
        if resp is None:
            calls["n"] += 1
            resp = client().get("/DRF/lawSearch.do", up, "JSON")
            cache.put("detc", up, resp)
        if resp.get("status") != "ok":
            raise UpstreamFailure(resp)
        try:
            body = json.loads(resp.get("raw_content") or "{}")
        except ValueError:
            raise UpstreamFailure({"status": "error", "error_code": ErrorCode.UPSTREAM_ERROR,
                                   "message": "detc_search 응답을 해석할 수 없습니다."})
        root = next(iter(body.values())) if isinstance(body, dict) and body else {}
        root = root if isinstance(root, dict) else {}
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
        return parse_detc_service(res.get("raw_content", ""))

    try:
        out = check_article(law_name=name, article=num, branch=branch, search=search, service=service,
                            max_scan=max_scan)
    except UpstreamFailure as f:
        resp = dict(f.response)
        resp.setdefault("status", "error")
        resp["message"] = (f"{resp.get('message', '')} (law_constitutional_check 중단: "
                           "업스트림 오류는 '위헌 결정 없음'으로 처리하지 않습니다.)")
        return resp
    scope = out["searched_scope"]
    caveats = list(CAVEATS)
    if scope["not_scanned"]:
        caveats.append(f"사건명이 일치한 결정 {scope['title_matches']}건 중 {scope['scanned'] + len(scope['unscannable'])}건만 "
                       "읽었습니다(not_scanned 참조). max_scan을 늘려 다시 조회할 수 있습니다.")
    if scope["list_truncated"]:
        caveats.append(f"검색 결과 {scope['search_rows_total']}건 중 {scope['search_rows_listed']}건만 조회했습니다.")
    if out["adverse_decisions"]:
        d = out["adverse_decisions"][0]
        statement = (f"{out['article']}: 헌재 결정 중 위헌·헌법불합치 단서 {len(out['adverse_decisions'])}건 "
                     f"(예: {d['case_number']}, {d['decision_date']}, {d['outcome']}). 단서이며 확인이 필요합니다.")
    else:
        statement = (f"{out['article']}: 검색한 범위에서 위헌·헌법불합치 결정을 찾지 못했습니다"
                     f"(읽은 결정 {scope['scanned']}건). 위헌 판단이 없었다는 뜻이 아닙니다 — 확인 필요.")
    return {"status": "ok", **out, "statement": statement, "upstream_calls": calls["n"], "caveats": caveats}
