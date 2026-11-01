"""Unit tests for jo (article number) normalization and article-presence detection."""

import json

import pytest

from lexlink.validation import (
    JoFormatError,
    describe_jo,
    extract_law_name,
    normalize_jo,
    response_has_article,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw, expected",
    [
        (35, "003500"),
        ("35", "003500"),
        (" 35 ", "003500"),
        ("35의5", "003505"),
        ("35 의 5", "003505"),
        ("제35조의5", "003505"),
        ("제35조", "003500"),
        ("35조의5", "003505"),
        ("35-5", "003505"),
        ("35_5", "003505"),
        ("35.5", "003505"),
        ("35,5", "003505"),
        ("(35,5)", "003505"),
        ("[35, 5]", "003505"),
        ("003505", "003505"),
        ("003500", "003500"),
        ("017400", "017400"),
        ("0035", "003500"),
        ("3", "000300"),
        ("제3조", "000300"),
        ("174", "017400"),
        ("1234", "123400"),
        ("９９의１", "009901"),  # full-width digits
    ],
)
def test_normalize_jo_accepts_common_forms(raw, expected):
    assert normalize_jo(raw) == expected


@pytest.mark.unit
def test_normalize_jo_none_and_empty_mean_no_filter():
    assert normalize_jo(None) is None
    assert normalize_jo("") is None
    assert normalize_jo("   ") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "garbage",
    [
        "abc",
        "제조",
        "35의",
        "의5",
        "35505",      # 5 digits: ambiguous
        "0000",       # article 0
        "000005",     # 6-digit code with article 0
        "12345678",   # too long
        "35-5-1",
        "제35조제1항",  # 항 is not part of jo
        "-5",
    ],
)
def test_normalize_jo_rejects_garbage_with_hints(garbage):
    with pytest.raises(JoFormatError) as exc:
        normalize_jo(garbage)
    assert isinstance(exc.value, ValueError)
    assert exc.value.hints, "JoFormatError must carry hints for the structured error"
    assert any("003505" in h for h in exc.value.hints)


@pytest.mark.unit
def test_describe_jo():
    assert describe_jo("003505") == "제35조의5"
    assert describe_jo("003500") == "제35조"
    assert describe_jo("017400") == "제174조"
    assert describe_jo("garbage") == "garbage"


# --- article presence -----------------------------------------------------

JSON_WITH_ARTICLE = json.dumps({
    "법령": {
        "법령키": "0007982026021021336",
        "기본정보": {"법령명_한글": "저작권법", "조문별시행일자": "20260811"},
        "조문": {"조문단위": {"조문번호": "35", "조문가지번호": "5", "조문내용": "제35조의5(저작물의 공정한 이용) ..."}},
    }
}, ensure_ascii=False)

JSON_ONLY_BASIC_INFO = json.dumps({
    "법령": {
        "법령키": "0007982026021021336",
        "기본정보": {"법령명_한글": "저작권법", "조문별시행일자": "20260811"},
    }
}, ensure_ascii=False)

XML_WITH_ARTICLE = """<?xml version="1.0" encoding="utf-8"?>
<법령 법령키="0007982026021021336">
<기본정보><법령명_한글><![CDATA[저작권법]]></법령명_한글>
<조문시행일자문자열>20260511:제2조</조문시행일자문자열></기본정보>
<조문><조문단위 조문키="0035005"><조문번호>35</조문번호><조문가지번호>5</조문가지번호>
<조문내용><![CDATA[제35조의5(저작물의 공정한 이용) ...]]></조문내용></조문단위></조문>
</법령>"""

XML_ONLY_BASIC_INFO = """<?xml version="1.0" encoding="utf-8"?>
<법령 법령키="0007982026021021336">
<기본정보><법령명_한글><![CDATA[저작권법]]></법령명_한글>
<조문시행일자문자열>20260511:제2조,제133조의2</조문시행일자문자열>
<조문별시행일자>20260811</조문별시행일자></기본정보>
</법령>"""


@pytest.mark.unit
def test_response_has_article_json():
    assert response_has_article(JSON_WITH_ARTICLE, "JSON") is True
    assert response_has_article(JSON_ONLY_BASIC_INFO, "JSON") is False
    assert response_has_article("{}", "JSON") is False
    assert response_has_article("", "JSON") is False
    assert response_has_article("not json", "JSON") is False


@pytest.mark.unit
def test_response_has_article_xml_ignores_basic_info_fields():
    assert response_has_article(XML_WITH_ARTICLE, "XML") is True
    # <조문시행일자문자열>/<조문별시행일자> must NOT count as an article
    assert response_has_article(XML_ONLY_BASIC_INFO, "XML") is False


@pytest.mark.unit
def test_response_has_article_html_is_not_judged():
    assert response_has_article("<html><body>anything</body></html>", "HTML") is True


@pytest.mark.unit
def test_extract_law_name():
    assert extract_law_name(JSON_ONLY_BASIC_INFO, "JSON") == "저작권법"
    assert extract_law_name(XML_ONLY_BASIC_INFO, "XML") == "저작권법"
    assert extract_law_name("{}", "JSON") is None
    assert extract_law_name(None, "JSON") is None


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["٣٥", "٠٠٣٥٠٥", "제٣٥조", "٣٥의٥", "٣٥-٥", "३५"])
def test_normalize_jo_rejects_non_ascii_digits(raw):
    # same policy as law_extras.ascii_digits: only full-width digits are folded
    with pytest.raises(JoFormatError):
        normalize_jo(raw)


@pytest.mark.unit
def test_normalize_jo_still_folds_fullwidth_digits():
    assert normalize_jo("３５") == "003500"
    assert normalize_jo("제３５조의５") == "003505"


@pytest.mark.unit
def test_validate_date_range_folds_fullwidth_and_returns_ascii():
    from lexlink.validation import validate_date_range
    assert validate_date_range("２０２００１０１~２０２４１２３１", "ef_yd") == "20200101~20241231"
    assert validate_date_range("20200101~20241231", "ef_yd") == "20200101~20241231"
    for bad in ("٢٠٢٠٠١٠١~٢٠٢٤١٢٣١", "2020-01-01~2024-12-31", "20241231~20200101"):
        with pytest.raises(ValueError):
            validate_date_range(bad, "ef_yd")


@pytest.mark.unit
def test_eflaw_search_sends_ascii_for_fullwidth_ef_yd(monkeypatch):
    import asyncio
    import httpx
    import lexlink.server as server_mod
    from lexlink.client import LawAPIClient
    from lexlink.cache import get_cache
    from urllib.parse import unquote
    get_cache().invalidate()
    monkeypatch.setenv("OC", "unit-test-oc")
    seen = []

    def handler(req):
        seen.append(unquote(str(req.url)))
        return httpx.Response(200, text=json.dumps({"LawSearch": {"totalCnt": "0", "law": []}}), request=req)

    def mk(*a, **k):
        c = LawAPIClient(base_url="http://law.test")
        c.client = httpx.Client(transport=httpx.MockTransport(handler))
        return c

    monkeypatch.setattr(server_mod, "LawAPIClient", mk)
    asyncio.set_event_loop(asyncio.new_event_loop())
    tool = server_mod.create_server()._tool_manager.get_tool("eflaw_search").fn
    out = tool(query="민법", ef_yd="２０２００１０１~２０２４１２３１")
    assert out["status"] == "ok" and "20200101" in seen[0] and "２" not in seen[0]


@pytest.mark.unit
def test_linkage_normalize_jo_code_digits():
    from lexlink.linkage import normalize_jo_code
    assert normalize_jo_code("３５") == "003500" and normalize_jo_code("제３５조의５") == "003505"
    with pytest.raises(Exception):
        normalize_jo_code("٣٥")
