"""Offline unit tests for lexlink.article_text (fixtures captured from law.go.kr, 2026-10-25)."""

import datetime
import json
from pathlib import Path

import pytest

from lexlink.article_text import (
    ArticleNotFoundError,
    article_jo,
    article_label,
    compact_delegation_tree,
    dedupe_versions,
    end_of_current_year,
    extract_article,
    extract_article_text,
    find_article_units,
    law_rows,
    normalize_article,
    parse_article_history,
    parse_law_payload,
    pick_current_version,
    previous_version,
    revision_record,
    select_law_rows,
    strip_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


EXPECTED_35_5 = [
    "제35조의5(저작물의 공정한 이용)",
    "① 제23조부터 제35조의4까지, 제101조의3부터 제101조의5까지의 경우 외에 저작물의 일반적인 이용 방법과 충돌하지 아니하고 저작자의 정당한 이익을 부당하게 해치지 아니하는 경우에는 저작물을 이용할 수 있다. <개정 2016.3.22, 2019.11.26, 2023.8.8>",
    "② 저작물 이용 행위가 제1항에 해당하는지를 판단할 때에는 다음 각 호의 사항등을 고려하여야 한다. <개정 2016.3.22>",
    "1. 이용의 목적 및 성격",
    "2. 저작물의 종류 및 용도",
    "3. 이용된 부분이 저작물 전체에서 차지하는 비중과 그 중요성",
    "4. 저작물의 이용이 그 저작물의 현재 시장 또는 가치나 잠재적인 시장 또는 가치에 미치는 영향",
]


# ---------------------------------------------------------------- article numbers

@pytest.mark.parametrize("ref,branch,expected", [
    (35, 0, (35, 0)),
    (35, 5, (35, 5)),
    ("35", 0, (35, 0)),
    ("35의5", 0, (35, 5)),
    ("제35조의5", 0, (35, 5)),
    ("제35조", None, (35, 0)),
    ("35-5", "", (35, 5)),
    ("003505", 0, (35, 5)),
    ("000200", 0, (2, 0)),
    (35, "5", (35, 5)),
])
def test_normalize_article(ref, branch, expected):
    assert normalize_article(ref, branch) == expected


@pytest.mark.parametrize("bad", ["", "abc", "제조", 0, 10000, "35의5의2"])
def test_normalize_article_rejects_garbage(bad):
    with pytest.raises(ValueError):
        normalize_article(bad)


def test_normalize_article_conflicting_branch():
    with pytest.raises(ValueError):
        normalize_article("35의5", 2)


def test_article_jo_and_label():
    assert article_jo("35의5") == "003505"
    assert article_jo(2) == "000200"
    assert article_label(35, 5) == "제35조의5"
    assert article_label(35) == "제35조"


# ---------------------------------------------------------------- extraction (JSON)

def test_extract_full_article_text_json():
    info = extract_article(load("law_283335_jo003505.json"), "JSON", 35, 5)
    assert info["text"].split("\n") == EXPECTED_35_5
    assert info["article"] == "제35조의5"
    assert info["title"] == "저작물의 공정한 이용"
    assert info["heading"] == "제35조의5(저작물의 공정한 이용)"
    assert info["lines"] == 7
    assert info["law"]["law_id"] == "000798"
    assert info["law"]["announced"] == "20260210"
    assert info["law"]["effective"] == "20260811"
    assert info["law"]["law_type"] == "법률"


def test_extract_without_article_number_takes_the_unit():
    assert extract_article_text(load("law_283335_jo003505.json")).split("\n") == EXPECTED_35_5


def test_extract_accepts_string_reference_and_parsed_dict():
    data = json.loads(load("law_283335_jo003505.json"))
    assert extract_article(data, "JSON", "제35조의5")["article"] == "제35조의5"
    assert extract_article(data, "JSON", "35의5")["lines"] == 7


def test_extract_xml_matches_json():
    xml_text = extract_article_text(load("law_283335_jo003505.xml"), "XML")
    json_text = extract_article_text(load("law_283335_jo003505.json"), "JSON")
    assert xml_text == json_text


def test_extract_older_version_has_same_text():
    old = extract_article(load("law_270165_jo003505.json"), "JSON", 35, 5)
    assert old["law"]["announced"] == "20250325"
    assert old["text"].split("\n") == EXPECTED_35_5


def test_extract_nested_mok():
    text = extract_article_text(load("law_283335_jo006400.json"), "JSON", 64)
    lines = text.split("\n")
    assert lines[0] == "제64조(보호받는 실연ㆍ음반ㆍ방송)"
    assert lines[1].startswith("①다음 각 호 각 목의 어느 하나에 해당하는 실연ㆍ음반 및 방송은")
    assert lines[2] == "1. 실연"
    assert lines[3].startswith("가. 대한민국 국민")
    assert any(line.startswith("2. 음반") for line in lines)
    # 목 lines appear directly after their 호, in order
    idx = lines.index("1. 실연")
    assert lines[idx + 1].startswith("가.") and lines[idx + 2].startswith("나.")


def test_extract_from_list_of_units_selects_requested_article():
    raw = load("law_283335_jo_multi.json")
    units = find_article_units(raw and json.loads(raw))
    assert len(units) == 3  # 전문(장 제목) + 제1조 + 제2조
    one = extract_article(raw, "JSON", 1)
    assert one["text"].startswith("제1조(목적) 이 법은 저작자의 권리와")
    assert one["lines"] == 1  # body is inside 조문내용 when there is no 항
    two = extract_article(raw, "JSON", 2)
    lines = two["text"].split("\n")
    assert lines[0].startswith("제2조(정의)")
    assert lines[1].startswith('1. "저작물"은')  # 항 without 항내용 → 호 directly
    # default (no number) skips the 전문 heading
    assert extract_article(raw, "JSON")["article"] == "제1조"


def test_extract_missing_article_raises_with_hint():
    with pytest.raises(ArticleNotFoundError) as exc:
        extract_article(load("law_283335_jo003505.json"), "JSON", 35, 6)
    assert "제35조의6" in str(exc.value)
    assert exc.value.hints and "제35조의5" in exc.value.hints[0]


def test_extract_version_without_the_article_raises():
    with pytest.raises(ArticleNotFoundError) as exc:
        extract_article(load("law_283335_nojo.json"), "JSON", 35, 5)
    assert "해당 조문이 없습니다" in str(exc.value)
    assert exc.value.hints


@pytest.mark.parametrize("raw", ["", "{}", None, "   ", "not json", b""])
def test_extract_empty_payload_raises_clear_error(raw):
    with pytest.raises(ArticleNotFoundError) as exc:
        extract_article(raw, "JSON", 35, 5)
    assert "비어 있습니다" in str(exc.value)
    assert any("JO" in h for h in exc.value.hints)


def test_parse_law_payload_shapes():
    assert parse_law_payload("{}") == {}
    assert parse_law_payload('{"a": 1}') == {"a": 1}
    assert parse_law_payload("<a><b>x</b><b>y</b></a>", "XML") == {"a": {"b": ["x", "y"]}}
    assert parse_law_payload({"k": "v"}) == {"k": "v"}


def test_whitespace_is_normalized():
    unit = {"조문내용": "  제1조(목적)   이 법은\n  문화   발전 ", "항": {"항내용": " ① 가 \t 나 ", "호": [{"호내용": "1.  다"}]}}
    assert extract_article_text({"법령": {"조문": {"조문단위": unit}}}) == "제1조(목적) 이 법은 문화 발전\n① 가 나\n1. 다"


# ---------------------------------------------------------------- version selection

@pytest.fixture
def copyright_rows():
    return law_rows(json.loads(load("eflaw_search_copyright.json")))


def test_law_rows_handles_run_search_result_and_single_row():
    assert law_rows({"ranked_data": {"law": {"법령ID": "1"}}}) == [{"법령ID": "1"}]
    assert law_rows({"LawSearch": {"law": [{"법령ID": "2"}]}}) == [{"법령ID": "2"}]
    assert law_rows({}) == [] and law_rows(None) == []


def test_select_law_rows_prefers_statute_over_decree(copyright_rows):
    rows = select_law_rows(copyright_rows, "저작권법")
    assert rows and {r["법령ID"] for r in rows} == {"000798"}
    assert {r["법령명한글"] for r in rows} == {"저작권법"}
    assert {r["법령구분명"] for r in rows} == {"법률"}
    # newest 공포일자 first
    dates = [r["공포일자"] for r in rows]
    assert dates == sorted(dates, reverse=True)


def test_select_law_rows_honours_decree_request(copyright_rows):
    rows = select_law_rows(copyright_rows, "저작권법 시행령")
    assert rows and {r["법령명한글"] for r in rows} == {"저작권법 시행령"}
    rows = select_law_rows(copyright_rows, "저작권법시행규칙")
    assert rows and all("시행규칙" in r["법령명한글"] for r in rows)


def test_select_law_rows_empty():
    assert select_law_rows([], "저작권법") == []


def test_pick_current_version_prefers_현행(copyright_rows):
    rows = select_law_rows(copyright_rows, "저작권법")
    cur = pick_current_version(rows)
    assert cur["법령일련번호"] == "283335"
    assert cur["현행연혁코드"] == "현행"
    # the first row would have been the 시행예정 MST 291259
    assert rows[0]["법령일련번호"] == "291259" and rows[0]["현행연혁코드"] == "시행예정"


def test_pick_current_version_fallbacks():
    history = [
        {"법령일련번호": "1", "현행연혁코드": "연혁", "시행일자": "20200101"},
        {"법령일련번호": "2", "현행연혁코드": "연혁", "시행일자": "20230101"},
        {"법령일련번호": "3", "현행연혁코드": "시행예정", "시행일자": "20270101"},
        {"법령일련번호": "4", "현행연혁코드": "시행예정", "시행일자": "20261101"},
    ]
    assert pick_current_version(history)["법령일련번호"] == "2"  # latest 연혁
    assert pick_current_version(history[2:])["법령일련번호"] == "4"  # nearest 시행예정
    assert pick_current_version([]) is None


def test_dedupe_versions_one_row_per_mst(copyright_rows):
    rows = select_law_rows(copyright_rows, "저작권법")
    versions = dedupe_versions(rows)
    msts = [v["법령일련번호"] for v in versions]
    assert len(msts) == len(set(msts))
    assert msts[:4] == ["291259", "285693", "283335", "270165"]
    by_mst = {v["법령일련번호"]: v for v in versions}
    # 283335 appears as 현행(20260811) and 연혁(20260511): representative is 현행
    assert by_mst["283335"]["현행연혁코드"] == "현행"
    assert by_mst["283335"]["effective_dates"] == ["20260511", "20260811"]
    assert by_mst["285693"]["effective_dates"] == ["20261029", "20270101"]


def test_revision_record_schema(copyright_rows):
    versions = dedupe_versions(select_law_rows(copyright_rows, "저작권법"))
    rec = revision_record(versions[2])
    assert rec == {
        "date": "20260210", "effective_date": "20260811", "type": "일부개정",
        "announcement_no": "21336", "mst": "283335", "status": "현행", "law_type": "법률",
        "effective_dates": ["20260511", "20260811"],
    }
    rec = revision_record(versions[3])
    assert rec["mst"] == "270165" and rec["status"] == "연혁" and "effective_dates" not in rec


def test_previous_version(copyright_rows):
    versions = [revision_record(v) for v in dedupe_versions(select_law_rows(copyright_rows, "저작권법"))]
    assert previous_version(versions, "283335")["mst"] == "270165"
    # 253595 and 253619 share 공포일자 20230808; 공포번호 orders them
    assert previous_version(versions, "253619")["mst"] == "253595"
    assert previous_version(versions, "253595")["mst"] == "251105"
    assert previous_version(versions, "29306") is None  # oldest (제정 1957)
    assert previous_version(versions, "nope") is None


# ---------------------------------------------------------------- lsJoHstInf / dates / html

def test_parse_article_history():
    entries = parse_article_history(load("lsJoHstInf_000798_003505.json"))
    assert [e["mst"] for e in entries] == ["253595", "211523"]
    assert entries[0]["reason"] == "조문변경" and entries[0]["change_date"] == "20230808"
    assert entries[1]["reason"] == "본조신설" and entries[1]["date"] == "20191126"
    assert parse_article_history("{}") == [] and parse_article_history("") == []


def test_end_of_current_year():
    assert end_of_current_year(datetime.date(2026, 10, 25)) == "20261231"
    assert end_of_current_year(datetime.date(2031, 1, 1)) == "20311231"
    assert len(end_of_current_year()) == 8 and end_of_current_year().endswith("1231")


def test_strip_html():
    assert strip_html("원고의<br/>청구를 <b>기각</b>&amp; 한다") == "원고의\n청구를 기각& 한다"
    assert strip_html("가<BR>나<br />다") == "가\n나\n다"
    assert strip_html(None) == "" and strip_html(["a<br/>", "b"]) == "a\nb"


# ---------------------------------------------------------------- lsDelegated compaction

def test_compact_delegation_tree():
    tree = compact_delegation_tree(load("lsDelegated_000798_trimmed.json"))
    assert tree["law"] == {"law_name": "저작권법", "law_id": "000798", "mst": "283335", "effective": "20260811"}
    assert tree["entry_count"] == len(tree["entries"]) > 0
    assert tree["truncated"] is False
    first = tree["entries"][0]
    assert first["article"] == "제2조" and first["kind"] == "인용법령"
    assert first["target"].startswith("정보통신망") and first["target_id"] == "277377"
    kinds = {e["kind"] for e in tree["entries"]}
    assert "위임행정규칙" in kinds or "위임규정" in kinds
    admin = next(e for e in tree["entries"] if e["kind"] in ("위임행정규칙", "위임규정"))
    assert admin["target"] and admin["target_id"]
    assert all("\n" not in k for k in tree["by_kind"])
    assert json.dumps(tree, ensure_ascii=False)  # serializable


def test_compact_delegation_tree_caps_entries_cleanly():
    tree = compact_delegation_tree(load("lsDelegated_000798_trimmed.json"), max_entries=2)
    assert len(tree["entries"]) == 2 and tree["truncated"] is True and "note" in tree
    assert compact_delegation_tree("{}")["entries"] == []
    assert compact_delegation_tree("")["entry_count"] == 0
