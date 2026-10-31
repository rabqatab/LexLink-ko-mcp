"""article_citation: "같은 법" resolves to the most recently named law."""

import asyncio

from lexlink.citation import CitationExtractor


def _a(cls, text):
    return f'<a class="link {cls}" onclick="fncLsLawPop(\'1\',\'JO\',\'\')">{text}</a>'


def _law(name):
    return _a("sfon1", f"「{name}」")


def _extract(body, source="건축법"):
    html = f'<div class="lawcon"><p>{body}</p></div>'
    ex = CitationExtractor()
    return ex.consolidate_citations(ex.parse_citations(html, source))


def _summary(cits):
    return [(c.citation_type, c.target_law_name, c.target_article,
             c.target_article_branch, c.target_paragraph) for c in cits]


def test_same_law_resolves_to_named_external_law():
    body = (f"{_law('산지관리법')} {_a('sfon2', '제14조')}와 {_a('sfon2', '제15조')}에 따른 허가, "
            f"{_a('sfon1', '같은 법')} {_a('sfon2', '제15조의2')}에 따른 허가")
    assert _summary(_extract(body)) == [
        ("external", "산지관리법", 14, None, None),
        ("external", "산지관리법", 15, None, None),
        ("external", "산지관리법", 15, 2, None),
    ]


def test_same_law_with_paragraph_after_other_law():
    body = (f"{_law('국토의 계획 및 이용에 관한 법률')} {_a('sfon2', '제86조')}{_a('sfon3', '제5항')}에 따른 지정과 "
            f"{_a('sfon1', '같은 법')} {_a('sfon2', '제88조')}{_a('sfon3', '제2항')}에 따른 인가 "
            f"{_law('도로법')} {_a('sfon2', '제36조')}, {_a('sfon1', '같은 법')} "
            f"{_a('sfon2', '제52조')}{_a('sfon3', '제1항')}")
    assert _summary(_extract(body)) == [
        ("external", "국토의 계획 및 이용에 관한 법률", 86, None, 5),
        ("external", "국토의 계획 및 이용에 관한 법률", 88, None, 2),
        ("external", "도로법", 36, None, None),
        ("external", "도로법", 52, None, 1),
    ]


def test_chained_same_law_keeps_referent():
    body = (f"{_law('농지법')} {_a('sfon2', '제34조')} {_a('sfon1', '같은 법')} {_a('sfon2', '제35조')} "
            f"{_a('sfon1', '같은 법')} {_a('sfon2', '제43조')}")
    assert [c.target_law_name for c in _extract(body)] == ["농지법"] * 3


def test_same_law_decree_and_rule_forms():
    body = (f"{_law('산지관리법')} {_a('sfon2', '제14조')} "
            f"{_a('sfon1', '같은 법 시행령')} {_a('sfon2', '제10조')} "
            f"{_a('sfon1', '같은 법')} 시행규칙 {_a('sfon2', '제3조')}")
    assert [(c.target_law_name, c.target_article) for c in _extract(body)] == [
        ("산지관리법", 14), ("산지관리법 시행령", 10), ("산지관리법 시행규칙", 3),
    ]


def test_this_law_stays_internal_and_resets_referent():
    body = (f"{_law('도로법')} {_a('sfon2', '제36조')}, {_a('sfon1', '이 법')} {_a('sfon2', '제5조')}, "
            f"{_a('sfon1', '같은 법')} {_a('sfon2', '제6조')}")
    assert _summary(_extract(body)) == [
        ("external", "도로법", 36, None, None),
        ("internal", "건축법", None, None, None),
        ("internal", None, 5, None, None),
        ("internal", "건축법", None, None, None),
        ("internal", None, 6, None, None),
    ]


def test_same_law_without_prior_named_law_is_internal():
    cits = _extract(f"{_a('sfon1', '같은 법')} {_a('sfon2', '제6조')}")
    assert cits[0].citation_type == "internal"
    assert cits[0].target_law_name == "건축법"


def test_connector_article_joins_external_law_but_plain_article_stays_internal():
    body = (f"{_law('농지법')} {_a('sfon2', '제34조')}, {_a('sfon2', '제35조')} 및 {_a('sfon2', '제43조')}에 따라 "
            f"{_a('sfon2', '제21조')}")
    assert _summary(_extract(body)) == [
        ("external", "농지법", 34, None, None),
        ("external", "농지법", 35, None, None),
        ("external", "농지법", 43, None, None),
        ("internal", None, 21, None, None),
    ]


def test_extract_citations_counts_end_to_end(monkeypatch):
    body = f"{_law('도로법')} {_a('sfon2', '제36조')}, {_a('sfon1', '같은 법')} {_a('sfon2', '제52조')}"
    html = f'<div class="lawcon"><p>{body}</p></div>'
    ex = CitationExtractor(request_delay=0)

    async def fake_seq(law_name, mst):
        return "1"

    async def fake_html(*a, **k):
        return html

    monkeypatch.setattr(ex, "get_lsi_seq", fake_seq)
    monkeypatch.setattr(ex, "fetch_article_html", fake_html)
    result = asyncio.run(ex.extract_citations("1", "건축법", 11))
    assert (result.internal_count, result.external_count) == (0, 2)
