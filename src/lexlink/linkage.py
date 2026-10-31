"""
Pure helpers for the 법령정보 지식베이스 linkage tools and the
자치법규 기준 법령 연계 (ordinance-law linkage) search tool.

Everything here is side-effect free so it can be unit-tested offline:
- jo code normalization ("35", "35의5", "제35조의5", "003505" → "003505")
- 용어관계코드 (trmRltCd) validation
- mode selection for ordinLsCon_search (query / law_id / org → upstream target)
- attaching parsed JSON/XML data to a lawService.do response
"""

import json
import re
from typing import Any, Optional, Union

from ._helpers import ToolValidationError
from .parser import parse_xml_response
from .validation import format_article_number


# 용어관계코드 (trmRltCd) accepted by lstrmRlt / dlytrmRlt
TRM_RLT_CODES = {
    "140301": "동의어",
    "140302": "반의어",
    "140303": "상위어",
    "140304": "하위어",
    "140305": "연관어",
}
_TRM_RLT_BY_NAME = {name: code for code, name in TRM_RLT_CODES.items()}

# "35", "35의5", "제35조", "제35조의5"
_JO_TEXT_RE = re.compile(r"^제?\s*(\d{1,4})\s*조?\s*(?:의\s*(\d{1,2}))?$")


def normalize_jo_code(jo: Union[str, int, None]) -> str:
    """Normalize an article reference to the 6-digit JO code (XXXXYY).

    Accepts: 35, "35", "35의5", "제35조의5", "003505" (already 6 digits).
    Raises ToolValidationError with hints when the value is missing or malformed.
    """
    hints = [
        "Use the article number: jo='35' (제35조)",
        "Branch articles: jo='35의5' (제35조의5)",
        "Or the 6-digit upstream code: jo='003505' (4-digit article + 2-digit branch)",
    ]
    if jo is None or str(jo).strip() == "":
        raise ToolValidationError("'jo' (article number) is required", hints=hints)

    text = str(jo).strip()

    if text.isdigit():
        if len(text) == 6:
            article, branch = int(text[:4]), int(text[4:])
        elif len(text) <= 4:
            article, branch = int(text), 0
        else:
            raise ToolValidationError(
                f"Ambiguous article code '{text}': use 1-4 digits for an article "
                "number or exactly 6 digits for the upstream JO code",
                hints=hints,
            )
    else:
        m = _JO_TEXT_RE.match(text)
        if not m:
            raise ToolValidationError(
                f"Invalid article reference '{text}'", hints=hints
            )
        article = int(m.group(1))
        branch = int(m.group(2)) if m.group(2) else 0

    try:
        return format_article_number(article, branch)
    except ValueError as e:
        raise ToolValidationError(str(e), hints=hints)


def validate_trm_rlt_cd(value: Union[str, int, None]) -> Optional[str]:
    """Validate/normalize 용어관계코드. Accepts the 6-digit code or its Korean name.

    Returns None when value is empty so callers can simply skip the param.
    """
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if text in TRM_RLT_CODES:
        return text
    if text in _TRM_RLT_BY_NAME:
        return _TRM_RLT_BY_NAME[text]
    options = ", ".join(f"{c} ({n})" for c, n in TRM_RLT_CODES.items())
    raise ToolValidationError(
        f"Invalid trm_rlt_cd '{text}'",
        hints=[f"Valid values: {options}", "Omit trm_rlt_cd to get all relation types"],
    )


def require_query_or_mst(query: Optional[str], mst: Optional[str], tool_name: str) -> None:
    """lawService.do term-linkage targets need either query (term text) or MST."""
    if (query is None or str(query).strip() in ("", "*")) and not mst:
        raise ToolValidationError(
            f"{tool_name}: provide 'query' (term text) or 'mst' (term 일련번호)",
            hints=[
                "query: the exact term, e.g. query='공정한이용'",
                "mst: a term MST from a previous linkage result, e.g. mst='1470403'",
            ],
        )


# ordinLsCon_search mode → upstream target on lawSearch.do
ORDIN_LINK_MODES = {
    "query": "lnkOrd",     # search linked ordinances by ordinance name
    "law_id": "lnkLsOrd",  # ordinances linked to a statute (knd=법령ID)
    "org": "lnkOrg",       # ordinances of a local government (org code)
}


def select_ordin_link_mode(
    query: Optional[str],
    law_id: Union[str, int, None],
    org: Union[str, int, None],
) -> tuple[str, dict[str, str], str]:
    """Pick the upstream target for ordinLsCon_search.

    Exactly one of query / law_id / org must be given.

    Returns:
        (target, extra_params, ranking_query)
        ranking_query is the text used for relevance ranking ("*" disables it).
    """
    provided = {}
    if query is not None and str(query).strip() != "":
        provided["query"] = str(query).strip()
    if law_id is not None and str(law_id).strip() != "":
        provided["law_id"] = str(law_id).strip()
    if org is not None and str(org).strip() != "":
        provided["org"] = str(org).strip()

    hints = [
        "query='주차장'  → ordinances whose name matches (target lnkOrd)",
        "law_id='001823' → ordinances linked to that statute 법령ID (target lnkLsOrd)",
        "org='3270000'   → ordinances of that local-government code (target lnkOrg)",
    ]
    if len(provided) == 0:
        raise ToolValidationError(
            "ordinLsCon_search requires exactly one of 'query', 'law_id', or 'org'",
            hints=hints,
        )
    if len(provided) > 1:
        raise ToolValidationError(
            "ordinLsCon_search accepts only one mode at a time; got "
            + ", ".join(sorted(provided)),
            hints=hints,
        )

    (mode, value), = provided.items()
    target = ORDIN_LINK_MODES[mode]
    if mode == "query":
        return target, {"query": value}, value
    if mode == "law_id":
        return target, {"knd": value}, "*"
    return target, {"org": value}, "*"


def attach_parsed_data(response: dict, response_type: str) -> dict:
    """Add 'parsed_data' (dict) to a lawService.do response when the body parses.

    JSON: unwraps the single root key (e.g. lstrmRltService).
    XML: parse_xml_response().
    Leaves the response untouched on errors / HTML / empty bodies.
    """
    if response.get("status") != "ok":
        return response
    raw = response.get("raw_content")
    if not raw or not isinstance(raw, str):
        return response

    parsed: Any = None
    if response_type == "JSON":
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and len(data) == 1:
                parsed = next(iter(data.values()))
            else:
                parsed = data
        except ValueError:
            parsed = None
    elif response_type == "XML":
        try:
            parsed = parse_xml_response(raw)
        except Exception:
            parsed = None

    if parsed:
        response["parsed_data"] = parsed
    return response


# Only exact synonyms are reported: 상위어/하위어/연관어/반의어 links can invert or shift the legal sense.
GLOSS_RELATIONS = ("동의어",)


def pick_linked_term(root: Any, name_key: str, term: str = "") -> tuple[str, str, bool]:
    """Pick a synonym from a lstrmRlt/dlytrmRlt body root as ``(name, relation, ambiguous)``.

    The upstream shape is ``root[<법령용어|일상용어>]`` = one dict, or a list of dicts
    for homonyms, each holding ``연계용어`` (list, or a dict for a single link).
    Entities whose own name differs from ``term`` are ignored (exact match only). With
    several homonym entities the sense is unknown, so nothing is picked and
    ``ambiguous`` is True. Only 동의어 links are used; a link equal to ``term`` is skipped.
    """
    if not isinstance(root, dict):
        return "", "", False
    entities: list = []
    for value in root.values():
        for entity in (value if isinstance(value, list) else [value]):
            if not (isinstance(entity, dict) and "연계용어" in entity):
                continue
            own = str(entity.get("법령용어명") or entity.get("일상용어명") or "").strip()
            if term and own and own != term:
                continue
            entities.append(entity)
    if len(entities) > 1:
        return "", "", True
    if not entities:
        return "", "", False
    linked = entities[0]["연계용어"]
    links = linked if isinstance(linked, list) else [linked]
    for relation in GLOSS_RELATIONS:
        for link in links:
            if isinstance(link, dict) and link.get("용어관계") == relation:
                name = str(link.get(name_key) or "").strip()
                if name and name != term:
                    return name, relation, False
    return "", "", False


def parse_drlaw_html(html: str) -> Optional[dict]:
    """Parse the drlaw (법령-자치법규 연계현황) HTML dashboard into plain data.

    Returns ``{"total", "columns", "rows"}`` where each row holds 소관부처, 법령명,
    조문 and ``자치법규수`` (counts keyed by the column headers: 전체, 서울, ...),
    or None when the expected statistics table is missing.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    table = soup.find("table", id="unOrdinStatsTb")
    body = table.find("tbody") if table else None
    if body is None:
        return None
    header_rows = table.find("thead").find_all("tr") if table.find("thead") else []
    columns = [th.get_text(strip=True) for th in header_rows[-1].find_all("th")] if header_rows else []
    rows = []
    for tr in body.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue
        # The article <td> is never closed upstream, so the count cells nest inside it:
        # read only its own text and take the counts by class.
        article = "".join(cells[2].find_all(string=True, recursive=False)).strip()
        counts = [c.get_text(strip=True) for c in tr.find_all("td", class_="unordTd")]
        rows.append({
            "소관부처": cells[0].get_text(strip=True),
            "법령명": cells[1].get_text(strip=True),
            "조문": article,
            "자치법규수": dict(zip(columns, counts)) if len(columns) == len(counts) else counts,
        })
    total = None
    num = soup.select_one(".lelitop .num strong")
    if num and num.get_text(strip=True).isdigit():
        total = int(num.get_text(strip=True))
    return {"total": total, "columns": columns, "rows": rows}
