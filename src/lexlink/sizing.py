"""Size-aware response modes for the long-text tools (brief view and character paging).

Pure functions over an already fetched (and cached) *full* upstream response. Nothing here
mutates its input: ``raw_content`` is parsed into a fresh object every time.

Case law (prec/detc/expc/decc): ``summarize_case`` (size fields only), ``brief_case``, ``page_case``.
Laws (law/eflaw): ``brief_law``, ``page_law``, ``law_toc``.

All lengths are characters (Unicode code points), not bytes.
"""

from __future__ import annotations

import bisect
import copy
import html
import json
import re
from typing import Any, Optional

from .article_text import article_unit_text

AUTO_BRIEF_THRESHOLD = 20_000   # a body up to this many characters comes back whole when sections is omitted
DEFAULT_PAGE_CHARS = 20_000
MIN_PAGE_CHARS = 1_000
MAX_PAGE_CHARS = 24_000
HEAD_CHARS = 6_000
TAIL_CHARS = 3_000
WHOLE_MAJORITY_CHARS = 9_000

_BR = "<br/>"

CLOSING_RE = re.compile(
    r"이\s*판결(?:에는|에 대하여는)[^\n]*?관여\s*(?:대)?법관(?:들)?의\s*(?:의견이\s*)?일치(?:하였|되었)다\.?"
)
KINDS = ("반대", "별개", "보충")
_KIND_RE = re.compile(r"(반대|별개|보충)의견")
_NAME_RE = re.compile(r"대법관\s*([가-힣]{2,4}?)(?=\s|,|의|$)")
_NUM = r"(?:\d{1,2}\.\s*)?"
_HEADER_A = re.compile(
    rf"^\s*{_NUM}대법관\s[^()]*?의\s*(반대|별개|보충)의견은\s*다음과\s*같다\.?\s*$"
)
_HEADER_B = re.compile(
    rf"^\s*{_NUM}(?:다수|반대|별개)의견에\s*대한\s*[^()]*?보충의견(?:은\s*다음과\s*같다)?\.?\s*$"
)
_LOOSE_RE = re.compile(rf"^\s*{_NUM}[^\n()]{{0,160}}(반대|별개|보충)의견(?:은\s*다음과\s*같다)?\.?\s*$")
_JUMUN_RE = re.compile(r"【\s*주\s*문\s*】")


# ---------------------------------------------------------------- generic helpers

def count_text_chars(node: Any) -> int:
    """Characters of every string value in a parsed JSON tree."""
    if isinstance(node, str):
        return len(node)
    if isinstance(node, dict):
        return sum(count_text_chars(v) for v in node.values())
    if isinstance(node, list):
        return sum(count_text_chars(v) for v in node)
    return 0


def _find_dict_with(node: Any, key: str, depth: int = 0) -> Optional[dict]:
    """First dict in the tree that holds ``key`` (depth-first)."""
    if depth > 12:
        return None
    if isinstance(node, dict):
        if key in node:
            return node
        for v in node.values():
            found = _find_dict_with(v, key, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_dict_with(v, key, depth + 1)
            if found is not None:
                return found
    return None


def _parse_json(raw: Any) -> Optional[Any]:
    if not isinstance(raw, str) or raw.lstrip()[:1] not in ("{", "["):
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------- opinion map

def _names(text: str) -> list[str]:
    return _NAME_RE.findall(text)


def _expected_from_closing(sentence: str) -> dict[str, set]:
    """Kinds (and justices) named in the closing sentence."""
    expected: dict[str, set] = {}
    prev = 0
    for m in _KIND_RE.finditer(sentence):
        expected.setdefault(m.group(1), set()).update(_names(sentence[prev:m.start()]))
        prev = m.end()
    return expected


def analyze_opinions(body: str) -> dict:
    """Map the majority/separate-opinion structure of a judgment body.

    Returns a dict with:
      ``state``: "absent" (no separate opinions mentioned), "mapped" or "unknown"
      ``majority_end``: offset (in ``body``) where the majority part ends, or None
      ``limit``: a safe end for the majority when ``majority_end`` is None (first header /
                 separate-opinion line, else len(body))
      ``segments``: [(start, end, label)] covering the body
      ``counts``: {"반대": n, ...} of headers found (mapped state)
      ``kinds``: kinds mentioned (closing sentence, headers or loose lines)
    """
    n = len(body)
    norm = body.replace(_BR, "\n")
    # offsets of each <br/> in the normalized text, to map normalized -> original positions
    shifts, pos = [], 0
    while True:
        i = body.find(_BR, pos)
        if i < 0:
            break
        shifts.append(i - 4 * len(shifts))  # position of the "\n" in the normalized text
        pos = i + len(_BR)

    def orig(p: int) -> int:
        return p + 4 * bisect.bisect_left(shifts, p)

    closing = CLOSING_RE.search(norm)
    expected: dict[str, set] = {}
    maj_end: Optional[int] = None
    if closing:
        expected = _expected_from_closing(closing.group(0))
        line_end = norm.find("\n", closing.end())
        maj_end = orig(len(norm) if line_end < 0 else line_end)

    # header lines (a header split over two lines is joined before judging)
    lines, p = [], 0
    for line in norm.split("\n"):
        lines.append((p, line))
        p += len(line) + 1
    headers: list[tuple[int, str, list]] = []
    loose: list[tuple[int, str]] = []
    for idx, (start, line) in enumerate(lines):
        text = line
        if not text.strip():
            continue
        cand = text
        if not re.search(r"[.다]\s*$", cand) and idx + 1 < len(lines):
            cand = text.rstrip() + " " + lines[idx + 1][1].strip()
        for variant in (text, cand):
            if len(variant) > 260 or "(" in variant:
                continue
            stripped = re.sub(r"^\s*\d{1,2}\.\s*", "", variant).rstrip()
            if re.search(r"\.\s", stripped):
                continue  # a sentence end mid-line: prose, not a header
            m = _HEADER_A.match(variant) or _HEADER_B.match(variant)
            if m:
                kind = m.group(1) if m.re is _HEADER_A else "보충"
                headers.append((orig(start), kind, _names(variant)))
                break
        else:
            if "대법관" in text and _LOOSE_RE.match(text) and len(text) <= 260:
                lm = _LOOSE_RE.match(text)
                loose.append((orig(start), lm.group(1)))

    counts: dict[str, int] = {}
    for _, kind, _n in headers:
        counts[kind] = counts.get(kind, 0) + 1
    kinds = sorted(set(expected) | set(counts) | {k for _, k in loose}, key=KINDS.index)

    def matches() -> bool:
        if not expected or set(expected) != set(counts):
            return False
        for kind, names in expected.items():
            got = {nm for _, k, ns in headers if k == kind for nm in ns}
            if names and got and names != got:
                return False
        return True

    mentioned = bool(expected or headers or loose)
    if not mentioned:
        state = "absent"
    elif closing and matches():
        state = "mapped"
    else:
        state = "unknown"

    first_mark = min([h[0] for h in headers] + [l[0] for l in loose] + [n])
    limit = n if state == "absent" else (maj_end if maj_end is not None else first_mark)
    if state == "absent":
        maj_end = n  # whole body is the majority part

    segments: list[tuple[int, int, str]] = []
    if state == "absent":
        segments = [(0, n, "다수의견")]
    elif state == "mapped":
        hs = sorted(headers)
        segments = [(0, hs[0][0], "다수의견")]
        for i, (hp, kind, names) in enumerate(hs):
            end = hs[i + 1][0] if i + 1 < len(hs) else n
            label = f"{kind}의견"
            if names:
                label += "(" + "·".join(names[:3]) + (f" 외{len(names) - 3}" if len(names) > 3 else "") + ")"
            segments.append((hp, end, label))
    else:
        if maj_end is not None:
            segments = [(0, maj_end, "다수의견"), (maj_end, n, "불명")]
        else:
            segments = [(0, n, "불명")]
    return {"state": state, "majority_end": maj_end, "limit": limit, "segments": segments,
            "counts": counts, "kinds": kinds, "n": n}


def opinions_field(info: dict) -> tuple[bool, Any]:
    """(present, value) for the top-level ``full_opinions``."""
    if info["state"] == "absent":
        return False, None
    if info["state"] == "unknown":
        return True, None
    value = {f"{k}의견": info["counts"][k] for k in KINDS if k in info["counts"]}
    value["chars"] = info["n"] - info["majority_end"] if info["majority_end"] is not None else 0
    # chars counts from the end of the majority part (closing sentence line)
    return True, value


# ---------------------------------------------------------------- case law

def _body_slot(data: Any, field: str) -> Optional[dict]:
    holder = _find_dict_with(data, field)
    if holder is not None and isinstance(holder.get(field), str):
        return holder
    return None


def size_fields(data: Any, field: str, body: str) -> dict:
    out: dict[str, Any] = {"full_chars": count_text_chars(data), "full_body_chars": len(body)}
    present, value = opinions_field(analyze_opinions(body))
    if present:
        out["full_opinions"] = value
    return out


def body_of(raw: Any, field: str) -> Optional[str]:
    """The body text of a JSON ``raw_content`` (None when absent or not JSON)."""
    data = _parse_json(raw)
    if data is None:
        return None
    holder = _body_slot(data, field)
    return holder[field] if holder else None


def case_size_fields_xml(raw: str, field: str) -> dict:
    """Approximate size fields for XML bodies (tags removed, entities decoded)."""
    def plain(s: str) -> str:
        return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", re.sub(r"<(?!br\s*/?>)[^>]+>", "", s)))
    m = re.search(rf"<{re.escape(field)}>(.*?)</{re.escape(field)}>", raw, flags=re.DOTALL)
    return {"full_chars": len(plain(raw)), "full_body_chars": len(plain(m.group(1))) if m else 0}


def _cut_to_break(text: str, start: int, end: int) -> int:
    """Largest cut point in (start, end] at a paragraph break, else a sentence end, else ``end``."""
    window = text[start:end]
    floor = max(len(window) // 5, 1)
    best = -1
    for token in (_BR, "\n"):
        i = window.rfind(token)
        if i >= 0:
            best = max(best, i + len(token))
    if best > floor:
        return start + best
    m = None
    for m in re.finditer(r"[.?!][\"'’”)\]]*\s", window):
        pass
    if m is not None and m.end() > floor:
        return start + m.end()
    i = text.rfind("<", start, end)  # a hard cut must not split a <br/> token
    if i > start and text.startswith(_BR, i) and i + len(_BR) > end:
        return i
    return end


def _segment_label(info: dict, start: int, end: int) -> str:
    labels = []
    for s, e, label in info["segments"]:
        if s < end and e > start and label not in labels:
            labels.append(label)
    return ", ".join(labels) or "불명"


def page_case(response: dict, field: str, offset: Optional[int], max_chars: Optional[int],
              extra_fields: tuple = ()) -> dict:
    """One page of the body ``field`` of a full case-law response."""
    from ._helpers import ToolValidationError
    data = _parse_json(response.get("raw_content"))
    holder = _body_slot(data, field) if data is not None else None
    if holder is None:
        raise ToolValidationError(f"{field} 본문을 찾을 수 없어 offset/max_chars를 적용할 수 없습니다")
    body = holder[field]
    total = len(body)
    start = offset or 0
    size = max_chars or DEFAULT_PAGE_CHARS
    if total and start >= total:
        raise ToolValidationError(
            f"offset={start}이 본문 길이({total}자) 이상입니다",
            hints=[f"offset은 0 이상 {total - 1} 이하여야 합니다. 이전 응답의 next_offset을 사용하세요"],
        )
    end = min(start + size, total)
    if end < total:
        end = _cut_to_break(body, start, end)
    info = analyze_opinions(body)
    header = f"[{field} {start + 1}~{end}자 / 전체 {total}자 · {_segment_label(info, start, end)}]"
    holder[field] = header + "\n" + body[start:end]
    if start > 0:  # later pages carry only the metadata and the page
        for key in list(holder):
            if key in extra_fields:
                del holder[key]
    out = dict(response)
    out["raw_content"] = _dump(data)
    out.update(size_fields(_parse_json(response["raw_content"]), field, body))
    if end < total:
        out["next_offset"] = end
    if start > 0 or end < total:
        shown = end - start
        out["truncated"] = True
        out["truncated_fields"] = [f"{field}: {total}자 중 {start + 1}~{end}자 ({shown}자)만 표시"]
        out["truncated_note"] = (
            f'이 응답은 {field} {start + 1}~{end}자 한 쪽입니다. '
            + (f"이어 받기: offset={end}. " if end < total else "마지막 쪽입니다. ")
            + 'offset/max_chars를 빼고 sections="full"로 부르면 전문을 한 번에 받습니다.'
        )
        out["truncated_detail"] = [{"field": field, "original_chars": total, "shown_chars": shown}]
    return out


def _brief_body(body: str, info: dict) -> Optional[tuple[str, int, bool, bool]]:
    """(brief_body_without_banner, shown_chars, has_gap, tail_omitted) or None when nothing is cut."""
    n = len(body)
    region_end = info["majority_end"] if info["majority_end"] is not None else info["limit"]
    has_tail_rule = info["majority_end"] is not None
    if region_end <= WHOLE_MAJORITY_CHARS:
        if region_end >= n:
            return None
        return body[:region_end], region_end, False, not has_tail_rule
    block = ""
    head_start = 0
    m = _JUMUN_RE.search(body, 0, region_end)
    if m:
        nxt = body.find("【", m.end(), region_end)
        block_end = nxt if nxt >= 0 else min(region_end, m.end() + 600)
        block = body[m.start():block_end]
        head_start = block_end
    head_end = min(head_start + HEAD_CHARS, region_end)
    head = body[head_start:head_end]
    parts = [block] if block else []
    parts.append(head)
    shown = len(block) + len(head)
    gap = False
    if has_tail_rule:
        tail_start = max(region_end - TAIL_CHARS, head_end)
        if tail_start > head_end:
            parts.append(f"[…중략 {tail_start - head_end}자…]")
            gap = True
        tail = body[tail_start:region_end]
        if tail:
            parts.append(tail)
            shown += len(tail)
    else:
        gap = head_end < region_end
    return "\n".join(p for p in parts if p), shown, gap, not has_tail_rule


def _opinion_note(info: dict, tail_omitted: bool) -> str:
    if info["state"] == "absent":
        return ""
    kinds = info["kinds"] or ["별개"]
    if tail_omitted:
        return "·".join(kinds) + " 의견 구간 확인 불가로 뒤 조각 생략"
    label = "·".join(kinds) + "의견 생략"
    if info["state"] == "mapped":
        label += "(" + ", ".join(f"{k} {info['counts'][k]}" for k in KINDS if k in info["counts"]) + ")"
    else:
        label += "(구간 확인 불가)"
    return label


def brief_case(response: dict, field: str) -> dict:
    """Brief view of a full case-law response. Returns the response unchanged (plus size
    fields) when the body is small enough that nothing would be cut."""
    data = _parse_json(response.get("raw_content"))
    holder = _body_slot(data, field) if data is not None else None
    if holder is None:
        return dict(response)
    body = holder[field]
    total = len(body)
    out = dict(response)
    out.update(size_fields(_parse_json(response["raw_content"]), field, body))
    info = analyze_opinions(body)
    built = _brief_body(body, info)
    if built is None:
        return out
    text, shown, gap, tail_omitted = built
    clauses = [f"축약본 · 전문 {total}자 중 {shown}자"]
    if gap:
        clauses.append("이유 중간 생략")
    note = _opinion_note(info, tail_omitted)
    if note:
        clauses.append(note)
    clauses.append('전문은 sections="full", 이어 받기는 offset/max_chars')
    holder[field] = "[" + " · ".join(clauses) + "]\n" + text
    out["raw_content"] = _dump(data)
    detail = {"field": field, "original_chars": total, "shown_chars": shown}
    if info["state"] != "absent":
        detail["separate_opinions_omitted"] = True
    out["truncated"] = True
    out["truncated_fields"] = [f"{field}: {total}자 중 {shown}자만 표시"]
    out["truncated_note"] = (
        f'{field}를 축약했습니다(주문 전체 + 앞 {HEAD_CHARS}자 + 다수의견 끝 {TAIL_CHARS}자). '
        f'전문은 sections="full", 이어 받기는 offset=0, max_chars={DEFAULT_PAGE_CHARS}로 시작해 next_offset을 따라가세요.'
    )
    out["truncated_detail"] = [detail]
    return out


# ---------------------------------------------------------------- laws

def law_units_holder(data: Any) -> Optional[dict]:
    """The dict that holds the ``조문단위`` list of a parsed law payload."""
    return _find_dict_with(data, "조문단위")


def _units(holder: dict) -> list[dict]:
    v = holder.get("조문단위")
    if isinstance(v, dict):
        return [v]
    return [u for u in (v or []) if isinstance(u, dict)]


def law_article_chars(raw: Any) -> Optional[int]:
    """Characters of all rendered article text (None when the payload has no 조문단위)."""
    data = _parse_json(raw)
    holder = law_units_holder(data) if data is not None else None
    if holder is None:
        return None
    return sum(len(article_unit_text(u)) for u in _units(holder))


def toc_entry(unit: dict) -> dict:
    kind = str(unit.get("조문여부") or "")
    title = str(unit.get("조문제목") or "").strip()
    if kind == "전문" and not title:
        title = re.sub(r"\s+", " ", str(unit.get("조문내용") or "")).strip()
    return {"조문번호": str(unit.get("조문번호") or ""), "조문가지번호": str(unit.get("조문가지번호") or ""),
            "조문제목": title, "조문여부": kind}


def toc_line(e: dict) -> str:
    if e["조문여부"] == "전문":
        return e["조문제목"]
    num = f"제{e['조문번호']}조" + (f"의{e['조문가지번호']}" if e["조문가지번호"] not in ("", "0") else "")
    return f"{num} {e['조문제목']}".rstrip()


def law_toc(raw: Any, offset: Optional[int], max_chars: Optional[int]) -> Optional[dict]:
    """Paged TOC fields (lexlink_toc, toc_total, next_offset) of a full law payload."""
    data = _parse_json(raw)
    holder = law_units_holder(data) if data is not None else None
    if holder is None:
        return None
    entries = [toc_entry(u) for u in _units(holder)]
    start = offset or 0
    limit = max_chars or DEFAULT_PAGE_CHARS
    page, used, i = [], 0, start
    while i < len(entries):
        cost = len(toc_line(entries[i])) + 1
        if page and used + cost > limit:
            break
        page.append(entries[i])
        used += cost
        i += 1
    out: dict[str, Any] = {"lexlink_toc": page, "toc_total": len(entries)}
    if i < len(entries):
        out["next_offset"] = i
    return out


def law_notice(toc_total: int, next_offset: Optional[int]) -> str:
    text = (f"조문 본문이 {AUTO_BRIEF_THRESHOLD}자를 넘어 목차(조문 {toc_total}개)만 돌려줍니다. "
            '조문 본문은 jo로 조문을 지정하거나, sections="full"로 전체를, '
            'sections="full"과 offset/max_chars로 조문 단위 쪽을 받으세요.')
    if next_offset is not None:
        text += f" 목차가 길어 일부만 담았습니다: 이어 받기 offset={next_offset}."
    return text


def brief_law(response: dict, offset: Optional[int], max_chars: Optional[int], with_article: bool = False,
              toc_source_raw: Optional[str] = None) -> dict:
    """TOC brief of a full law response (``with_article``: keep the response's own body and take
    the TOC from ``toc_source_raw``, the whole-law payload)."""
    raw = response.get("raw_content")
    source = toc_source_raw if toc_source_raw is not None else raw
    data = _parse_json(raw)
    toc = law_toc(source, offset, max_chars)
    if data is None or toc is None:
        return dict(response)
    out = dict(response)
    src_data = _parse_json(source)
    out["full_chars"] = count_text_chars(src_data)
    out["full_body_chars"] = law_article_chars(source) or 0
    out.update(toc)
    notice = law_notice(toc["toc_total"], toc.get("next_offset"))
    if with_article:
        out["notice"] = (f"요청한 조문 본문과 함께 전체 목차(조문 {toc['toc_total']}개)를 덧붙였습니다."
                         + (f" 목차가 길어 일부만 담았습니다: 이어 받기 offset={toc['next_offset']}."
                            if "next_offset" in toc else ""))
        return out
    out["notice"] = notice
    law = data.get("법령") if isinstance(data.get("법령"), dict) else data
    kept: dict[str, Any] = {}
    for k, v in law.items():
        if k in ("조문", "부칙", "별표", "개정문", "제개정이유"):
            continue
        kept[k] = v
        if k == "기본정보":
            kept["lexlink_notice"] = notice
    if "기본정보" not in kept:
        kept["lexlink_notice"] = notice
    if law is data:
        data = kept
    else:
        data["법령"] = kept
    out["raw_content"] = _dump(data)
    omitted = out["full_body_chars"]
    out["truncated"] = True
    out["truncated_fields"] = [f"조문단위: 조문 본문 {omitted}자 중 0자만 표시(목차만)"]
    out["truncated_note"] = notice
    out["truncated_detail"] = [{"field": "조문단위", "original_chars": omitted, "shown_chars": 0}]
    return out


def page_law(response: dict, offset: Optional[int], max_chars: Optional[int]) -> dict:
    """One page of 조문단위 (whole units that fit in ``max_chars``), upstream structure kept."""
    from ._helpers import ToolValidationError
    data = _parse_json(response.get("raw_content"))
    holder = law_units_holder(data) if data is not None else None
    if holder is None:
        raise ToolValidationError("조문단위를 찾을 수 없어 offset/max_chars를 적용할 수 없습니다")
    units = _units(holder)
    start = offset or 0
    limit = max_chars or DEFAULT_PAGE_CHARS
    if units and start >= len(units):
        raise ToolValidationError(
            f"offset={start}이 조문단위 개수({len(units)}) 이상입니다",
            hints=[f"offset은 0 이상 {len(units) - 1} 이하여야 합니다. 이전 응답의 next_offset을 사용하세요"],
        )
    total_chars = sum(len(article_unit_text(u)) for u in units)
    page, used, i = [], 0, start
    while i < len(units):
        cost = len(article_unit_text(units[i]))
        if page and used + cost > limit:
            break
        page.append(units[i])
        used += cost
        i += 1
    holder["조문단위"] = page
    if start > 0:
        parent = data.get("법령") if isinstance(data.get("법령"), dict) else data
        for k in list(parent):
            if k not in ("법령키", "기본정보", "조문"):
                del parent[k]
    out = dict(response)
    out["raw_content"] = _dump(data)
    src = _parse_json(response["raw_content"])
    out["full_chars"] = count_text_chars(src)
    out["full_body_chars"] = total_chars
    if i < len(units):
        out["next_offset"] = i
    if start > 0 or i < len(units):
        out["truncated"] = True
        out["truncated_fields"] = [f"조문단위: {len(units)}개 중 {start + 1}~{i}번째({used}자)만 표시"]
        out["truncated_note"] = (
            f"조문단위 {start + 1}~{i}번째 쪽입니다. "
            + (f"이어 받기: offset={i}. " if i < len(units) else "마지막 쪽입니다. ")
            + 'offset/max_chars 없이 sections="full"이면 전체를 한 번에 받습니다.'
        )
        out["truncated_detail"] = [{"field": "조문단위", "original_chars": total_chars, "shown_chars": used}]
    return out
