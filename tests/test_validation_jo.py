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
