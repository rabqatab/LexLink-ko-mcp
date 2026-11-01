"""부칙 relative enforcement dates ("공포 후 6개월이 경과한 날부터 시행") in law_as_of's article scan."""

import pytest

from lexlink.as_of import relative_enforcement_date, scan_bupchik

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("announced,n,unit,expected", [
    # 스토킹범죄의 처벌 등에 관한 법률: 공포 2021-04-20, "공포 후 6개월이 경과한 날" = 시행 2021-10-21 (eflaw 시행일자)
    ("20210420", 6, "개월", "20211021"),
    ("20210831", 6, "개월", "20220301"),      # no such day (2.31): period ends on the month's last day
    ("20200131", 1, "개월", "20200301"),      # 2020 leap year: 2.30 does not exist
    ("20191231", 1, "년", "20210101"),
    ("20200229", 1, "년", "20210301"),
    ("20180320", 20, "일", "20180410"),
    ("", 6, "개월", None),
    ("2018", 6, "개월", None),
])
def test_relative_enforcement_date(announced, n, unit, expected):
    assert relative_enforcement_date(announced, n, unit) == expected


def unit(announced, *lines):
    return {"부칙공포일자": announced, "부칙공포번호": "1", "부칙내용": [["부칙 <제1호," + announced + ">", *lines]]}


def test_relative_date_after_d_is_a_staged_hit_with_computed_date():
    u = unit("20210420",
             "제1조(시행일) 이 법은 공포 후 6개월이 경과한 날부터 시행한다. 다만, 제9조는 공포 후 1년이 경과한 날부터 시행한다.")
    hit = scan_bupchik([u], 9, 0, "20211101")
    assert len(hit) == 1 and hit[0]["later_dates"] == ["20220421"]
    assert hit[0]["computed_from_announcement"] == ["20220421"] and "unresolved" not in hit[0]
    assert scan_bupchik([u], 9, 0, "20220421") == []          # on the computed date it is in force


def test_relative_date_not_after_d_is_no_hit():
    u = unit("20210420", "제1조(시행일) 제5조는 공포 후 6개월이 경과한 날부터 시행한다.")
    assert scan_bupchik([u], 5, 0, "20211021") == []
    assert [h["later_dates"] for h in scan_bupchik([u], 5, 0, "20211020")] == [["20211021"]]


def test_delegated_date_is_unresolved():
    u = unit("20210420", "제1조(시행일) 제7조는 공포 후 1년 6개월 이내에서 대통령령으로 정하는 날부터 시행한다.")
    hit = scan_bupchik([u], 7, 0, "20300101")
    assert len(hit) == 1 and hit[0]["later_dates"] == [] and hit[0]["unresolved"]


def test_relative_to_enforcement_date_is_unresolved_and_missing_announcement_too():
    u = unit("20210420", "제2조(시행일) 제8조는 이 법 시행 후 6개월이 경과한 날부터 시행한다.")
    assert scan_bupchik([u], 8, 0, "20211101")[0]["unresolved"]
    v = {"부칙내용": [["제1조 제4조는 공포 후 6개월이 경과한 날부터 시행한다."]]}   # no 부칙공포일자
    assert scan_bupchik([v], 4, 0, "20200101")[0]["unresolved"]


def test_unrelated_article_unaffected():
    u = unit("20210420", "제1조(시행일) 제7조는 공포 후 6개월이 경과한 날부터 시행한다.")
    assert scan_bupchik([u], 8, 0, "20200101") == []


# ---- real 부칙 text: 스토킹범죄의 처벌 등에 관한 법률, 공포 2023-07-11 (MST 252483) ---------------------

import json
import pathlib

from test_law_as_of import ROWS, BODIES, BUPCHIK, _row, as_of  # noqa: F401  (as_of is a fixture)

REAL = json.loads((pathlib.Path(__file__).parent / "fixtures" / "bupchik_stalking_act_units.json").read_text(encoding="utf-8"))
REAL_UNIT = REAL["252483"]["unit"]


def test_real_text_stalking_act_2023_amendment():
    # "제1조(시행일) 이 법은 공포한 날부터 시행한다. 다만, 제9조제1항제3호의2, 같은 조 제3항ㆍ제4항,
    #  제10조제1항ㆍ제5항, 제17조의4 및 제20조제1항제1호의 개정규정은 공포 후 6개월이 경과한 날부터 시행한다."
    # eflaw lists 시행일자 20240112 for this MST, which is 2023-07-11 + 6개월 by the same rule.
    assert REAL["252483"]["effective"] == "20240112"
    for art, branch in ((9, 0), (10, 0), (17, 4), (20, 0)):
        hit = scan_bupchik([REAL_UNIT], art, branch, "20230801")
        assert [h["later_dates"] for h in hit] == [["20240112"]], (art, branch)
        assert hit[0]["computed_from_announcement"] == ["20240112"]
    assert scan_bupchik([REAL_UNIT], 17, 4, "20240112") == []     # in force on the computed date
    assert scan_bupchik([REAL_UNIT], 17, 3, "20230801") == []     # 제17조의3 is not named
    assert scan_bupchik([REAL_UNIT], 7, 0, "20230801") == []      # 제7조제5항 is an 적용례, not 시행일


@pytest.fixture
def stalking(as_of, monkeypatch):
    import test_law_as_of as tla
    name = "스토킹테스트법"
    rows = [
        _row("002001", name, "252483", "20230711", "20230711", "19518", "일부개정", "연혁"),
        _row("002001", name, "252483", "20240112", "20230711", "19518", "일부개정", "현행"),
        _row("002002", "위임테스트법", "262000", "20230711", "20230711", "19600", "일부개정", "현행"),
    ]
    ROWS.extend(rows)
    monkeypatch.setitem(BODIES, ("252483", "20230711"), {"제9조": "제9조(잠정조치) 신법 전"})
    monkeypatch.setitem(BODIES, ("252483", "20240112"), {"제9조": "제9조(잠정조치) 신법 후"})
    monkeypatch.setitem(BUPCHIK, ("252483", "20240112"), [REAL_UNIT])
    monkeypatch.setitem(BODIES, ("262000", "20230711"), {"제9조": "제9조(위임) 본문"})
    monkeypatch.setitem(BUPCHIK, ("252483", "20230711"), [REAL_UNIT])
    monkeypatch.setitem(BUPCHIK, ("262000", "20230711"), [{
        "부칙공포일자": "20230711", "부칙공포번호": "19600",
        "부칙내용": [["부칙 <제19600호,2023.7.11>", "제1조(시행일) 이 법은 공포한 날부터 시행한다. 다만, 제9조는 공포 후 1년 이내에서 대통령령으로 정하는 날부터 시행한다."]]}])
    yield as_of, name
    for r in rows:
        ROWS.remove(r)


def test_law_as_of_reports_computed_relative_date_for_the_article(stalking):
    as_of, name = stalking
    out = as_of(law_name=name, as_of="20230801", article=9)
    assert out["in_force"] is True
    scan = out["partial_effect"]["article_scan"]
    assert scan["article_staged_enforcement_found"] and scan["matches"][0]["later_dates"] == ["20240112"]
    assert any("20240112" in c and "공포일 20230711 기준 계산" in c for c in out["caveats"])
    after = as_of(law_name=name, as_of="20240112", article=9)
    assert after["partial_effect"]["article_scan"]["article_staged_enforcement_found"] is False


FAMILY = json.loads((pathlib.Path(__file__).parent / "fixtures" / "bupchik_family_register_2016_unit.json").read_text(encoding="utf-8"))


def test_old_amendments_delegated_date_does_not_apply_to_later_versions():
    # 가족관계의 등록 등에 관한 법률 부칙 <제14169호,2016.5.29>: 제14조제5항 전단 및 제15조 ... 대법원규칙으로 정하는 날
    unit_ = FAMILY["unit"]
    own_2016 = scan_bupchik([unit_], 15, 0, "20180101", own=("20160529", "14169"))
    assert own_2016 and own_2016[0].get("unresolved") and not own_2016[0].get("settled_unresolved")
    later = scan_bupchik([unit_], 15, 0, "20180101", own=("20171031", "14963"))     # version of the 2017 amendment
    assert later and later[0].get("settled_unresolved") and "unresolved" not in later[0]
    assert scan_bupchik([unit_], 14, 0, "20260101", own=("20231226", "19841"))[0].get("settled_unresolved")


@pytest.fixture
def family(as_of):
    name = "가족등록테스트법"
    rows = [
        _row("002003", name, "198473", "20171031", "20171031", "14963", "일부개정", "연혁"),
        _row("002003", name, "257203", "20231226", "20231226", "19841", "일부개정", "현행"),
    ]
    ROWS.extend(rows)
    for key in (("198473", "20171031"), ("257203", "20231226")):
        BODIES[key] = {"제15조": "제15조(증명서) 본문"}
        BUPCHIK[key] = [FAMILY["unit"]]
    yield as_of, name
    for r in rows:
        ROWS.remove(r)
    for key in (("198473", "20171031"), ("257203", "20231226")):
        BODIES.pop(key, None)
        BUPCHIK.pop(key, None)


@pytest.mark.parametrize("d", ["20180101", "20260101"])
def test_law_as_of_in_force_does_not_regress_on_old_delegated_date(family, d):
    as_of, name = family
    out = as_of(law_name=name, as_of=d, article=15)
    assert out["in_force"] is True and "reason" not in out
    assert out["partial_effect"]["earlier_amendment_unresolved_dates"][0]["phrases"] == ["대법원규칙으로 정하는 날"]
    assert any("이전 개정의 부칙" in c and "쓰지 않았습니다" in c for c in out["caveats"])


@pytest.mark.parametrize("text,expected", [
    # 공포 2020-01-15
    ("제2조 제5조는 공포 후 1년 6개월이 경과한 날부터 시행한다.", [["20210716"]]),
    ("제2조 제5조는 공포 후 6개월이 경과한 날이 속하는 달의 1일부터 시행한다.", [["20200701"]]),
    ("제2조 제5조는 공포 후 6개월이 경과한 날의 다음 날부터 시행한다.", [["20200717"]]),
    ("제2조 제5조는 공포 후 6개월이 경과한 날이 속하는 달의 다음 달 1일부터 시행한다.", "unresolved"),
    ("제2조 제5조는 공포 후 6개월이 경과한 날의 전날부터 시행한다.", "unresolved"),
    ("제2조 제5조는 공포 6개월 후부터 시행한다.", "unresolved"),
    ("제2조 제5조는 공포한 날부터 6개월이 경과한 날부터 시행한다.", "unresolved"),
    ("제2조 제5조는 공포 후 1년 2일이 경과한 날부터 시행한다.", "unresolved"),
])
def test_relative_forms(text, expected):
    u = {"부칙공포일자": "20200115", "부칙공포번호": "1", "부칙내용": [["부칙 <제1호,2020.1.15>", text]]}
    hits = scan_bupchik([u], 5, 0, "20200116")
    if expected == "unresolved":
        assert len(hits) == 1 and hits[0].get("unresolved") and not hits[0]["later_dates"], hits
    else:
        assert [h["later_dates"] for h in hits] == expected, hits


def test_items_under_each_ho_that_name_the_article():
    u = {"부칙공포일자": "20200115", "부칙공포번호": "1", "부칙내용": [[
        "부칙 <제1호,2020.1.15>",
        "제1조(시행일) 이 법은 다음 각 호의 구분에 따른 날부터 시행한다.",
        "  1. 제5조: 2024년 1월 1일",
        "  2. 제6조: 공포 후 1년이 경과한 날",
        "  3. 제7조: 대통령령으로 정하는 날"]]}
    assert [h["later_dates"] for h in scan_bupchik([u], 5, 0, "20200116")] == [["20240101"]]
    assert [h["later_dates"] for h in scan_bupchik([u], 6, 0, "20200116")] == [["20210116"]]
    assert scan_bupchik([u], 7, 0, "20200116")[0].get("unresolved")
    assert scan_bupchik([u], 8, 0, "20200116") == []


def test_law_as_of_in_force_is_null_when_the_date_cannot_be_computed(stalking):
    as_of, _ = stalking
    out = as_of(law_name="위임테스트법", as_of="20230801", article=9)
    assert out["in_force"] is None and out["reason"] == "ARTICLE_STAGED_DATE_UNRESOLVED"
    assert out["partial_effect"]["unresolved"][0]["phrases"]
    assert "in_force=null" in out["statement"]
    assert any("대통령령으로 정하는 날" in c and "확인할 수 없습니다" in c for c in out["caveats"])
