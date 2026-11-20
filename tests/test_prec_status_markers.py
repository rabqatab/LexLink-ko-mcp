"""prec_status: misses from legal-research experiment 014 (offline, mocked upstream).

Fixtures are verbatim from live 법제처 responses (public 대법원 decisions), trimmed:
* tests/fixtures/prec_service_<overruling case>_trimmed.json: the sentence that names the target (판례내용)
  plus the full 참조판례; 사건번호/선고일자/판결유형/법원명/사건명 as served.
* tests/fixtures/prec_status_marker_refs_trimmed.json: the full 참조판례 of 전원합의체 decisions that spell the
  변경 marker in the formats the older tests did not cover.
Rows marked SYNTHETIC are made-up negatives. No credentials or links.
"""

import json
import pathlib

import pytest

import lexlink.server as server_mod
from lexlink import precedent_status as ps
from lexlink.cache import get_cache

pytestmark = pytest.mark.unit

FIX = pathlib.Path(__file__).parent / "fixtures"


def body(name):
    return json.loads((FIX / f"prec_service_{name}_trimmed.json").read_text(encoding="utf-8"))["PrecService"]


REFS = json.loads((FIX / "prec_status_marker_refs_trimmed.json").read_text(encoding="utf-8"))


def row(no, date, pid, kind="판결", name="", court="대법원"):
    return {"사건번호": no, "선고일자": date, "판례일련번호": pid, "판결유형": kind, "법원명": court, "사건명": name}


EB = "전원합의체 판결"

# target -> (target list row, overruling row, overruling decision file, expected evidence kind)
PAIRS = {
    "71누196": (row("71누196", "1972.02.22", "601203", name="행정처분무효확인"),
                row("2003두9015", "2004.04.22", "127086", EB, "지목변경신청반려처분취소"), "2003두9015", "explicit_sentence"),
    "81다카545": (row("81다카545", "1982.12.28", "97130", name="소유권이전등기말소등"),
                  row("88다카33619", "1990.02.27", "147296", "전원합의체판결", "소유권이전등기말소"), "88다카33619", "explicit_sentence"),
    "95도1035": (row("95도1035", "1996.12.23", "600705", name="국가보안법위반"),
                 row("2010도1189", "2010.07.23", "192343", EB, "국가보안법위반"), "2010도1189", "explicit_sentence"),
    "4294민상1350": (row("4294민상1350", "1962.04.26", "150422", name="저당권설정등기말소등기"),
                     row("93다16338", "1994.01.25", "200454", EB, "근저당권설정등기말소"), "93다16338", "explicit_sentence"),
    "93누21255": (row("93누21255", "1993.12.21", "200767", name="자동차운행정지처분등취소"),
                  row("94누14148", "1995.10.17", "600623", EB, "택시운전자격정지처분취소"), "94누14148", "explicit_sentence"),
}


def synthetic_rows(target_row):
    return [
        # SYNTHETIC: en-banc decision dated BEFORE the target -> not later, never read
        row("1949다1", "1949.01.01", "900001", EB, "synthetic"),
        # SYNTHETIC: later 전원합의체 row of another court -> never read
        row("2099나3", "2030.01.01", "900004", EB, "synthetic", court="서울고등법원"),
    ]


class FakeClient:
    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == "/DRF/lawSearch.do":
            if params.get("nb"):
                t = PAIRS.get(params["nb"])
                rows = [t[0]] if t else []
            else:
                t = PAIRS.get((params.get("query") or "").strip('"'))
                rows = ([t[1]] + synthetic_rows(t[0])) if t else []
            payload = {"PrecSearch": {"totalCnt": str(len(rows)), "page": "1", "prec": rows}}
        else:
            pid = str(params.get("ID"))
            by_id = {v[1]["판례일련번호"]: v[2] for v in PAIRS.values()}
            payload = {"PrecService": body(by_id[pid])}
        return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                "raw_content": json.dumps(payload, ensure_ascii=False)}


@pytest.fixture
def status(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", FakeClient)
    monkeypatch.setenv("OC", "test")
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    get_cache().invalidate()
    server = server_mod.create_server()
    yield lambda **kw: server._tool_manager.get_tool("prec_status").fn(**kw)
    get_cache().invalidate()


# ---- the five pairs that were missed -------------------------------------------------------------

@pytest.mark.parametrize("target", list(PAIRS))
def test_missed_pair_is_now_found_with_honest_confidence(status, target):
    _, _, overruler, kind = PAIRS[target]
    out = status(case_number=target)
    assert out["status"] == "ok" and out["overruling_status"] == "overruled_found"
    assert {e["source"]["case_number"] for e in out["evidence"]} == {overruler}
    assert {e["evidence"] for e in out["evidence"]} == {kind}
    # a named-in-a-sentence finding is medium, never the high of a 참조판례 marker
    assert {e["confidence"] for e in out["evidence"]} == {"medium"}
    assert out["searched_scope"]["scanned"] and out["searched_scope"]["incomplete"] is False
    assert out["upstream_calls"] == 3            # nb lookup + citing search + one decision body
    assert target.split("민상")[-1] in " ".join(e["quote"] for e in out["evidence"]).replace(" ", "")


def test_synthetic_rows_are_never_read(status):
    out = status(case_number="71누196")
    assert not {c["id"] for c in out["searched_scope"]["scanned"]} & {"900001", "900004"}


# ---- root causes, one by one -------------------------------------------------------------------

def test_case_number_glued_to_following_word_is_still_parsed():
    # 94누14148: "1993.12.21. 선고 93누21255판결은 이를 폐기하기로 한다" (no space before 판결)
    assert ps.parse_case_numbers("93누21255판결은") == [(1993, "누", 21255)]
    # SYNTHETIC negatives: a trailing letter that is not a citation word keeps the number unparsed
    assert ps.parse_case_numbers("2018다248909가") == []
    assert ps.parse_case_numbers("2018다2489091") == []


def test_space_between_kind_and_number_is_tolerated():
    # 93다16338 writes "4294민상 1350"
    assert ps.parse_case_numbers("1962.4.26.선고 4294민상 1350 판결") == [(4294, "민상", 1350)]
    # a single-letter kind does not get the same tolerance ("94므 1713" is not a case number)
    assert ps.parse_case_numbers("94므 1713") == []


@pytest.mark.parametrize("text,key", [
    ("4290민재항고58", (4290, "민재항고", 58)),
    ("대법원 1957. 12. 5. 자 4290민재항고58 결정", (4290, "민재항고", 58)),
    ("4294민상1350", (4294, "민상", 1350)),
    ("71누196", (1971, "누", 196)),
    ("88다카33619", (1988, "다카", 33619)),
    ("4291형상7", (4291, "형상", 7)),
    ("4285형재항고3", (4285, "형재항고", 3)),   # SYNTHETIC number
    ("4290민별항고7", (4290, "민별항고", 7)),   # SYNTHETIC: a kind that is not listed at all: generic fallback
])
def test_old_and_odd_case_numbers_parse(text, key):
    assert ps.parse_case_numbers(text) == [key]
    assert ps.parse_target(text)[0] == key


def test_prose_is_not_mistaken_for_a_case_number():
    # SYNTHETIC
    assert ps.parse_case_numbers("2020일부터30 이내") == []


def test_odd_case_type_returns_case_not_found_not_an_error(status):
    out = status(case_number="4290민재항고58")
    assert out["status"] == "ok" and out["overruling_status"] == "case_not_found"
    assert out["target"]["found_in_index"] is False


def test_list_declaration_with_closing_clause_ties_every_listed_case():
    f = body("2010도1189")
    ev = ps.find_evidence(f, (1995, "도", 1035))
    assert [e["evidence"] for e in ev["explicit"]] == ["explicit_sentence"]
    assert "95도1035" in ev["explicit"][0]["quote"]


def test_list_closing_clause_does_not_tie_a_case_the_court_keeps():
    # SYNTHETIC: the court keeps A and changes B in the same sentence
    t = ("이와 달리 판시한 대법원 2001. 1. 1. 선고 2000다1 판결은 유지하되, 대법원 2002. 1. 1. 선고 2001다2 판결과 "
         "그 밖에 이 판결의 견해와 다른 대법원 판결들은 이 판결의 견해에 배치되는 범위 안에서 이를 변경하기로 한다.")
    assert ps.find_evidence({"판례내용": t}, (2000, "다", 1))["explicit"] == []
    assert len(ps.find_evidence({"판례내용": t}, (2001, "다", 2))["explicit"]) == 1


def test_parenthesised_citation_followed_by_discarded_view():
    ev = ps.find_evidence(body("88다카33619"), (1981, "다카", 545))
    assert [(e["evidence"], e.get("pattern")) for e in ev["explicit"]] == [
        ("explicit_sentence", "cited_in_parenthesis_then_view_changed")]
    # the 참조판례 of that decision does not list 81다카545 at all
    assert "81다카545" not in body("88다카33619")["참조판례"]


@pytest.mark.parametrize("tail,found", [
    (", 이러한 견해는 폐기한다.", True),
    (", 이러한 견해는 이로써 변경한다.", True),
    # SYNTHETIC negatives
    (", 이러한 견해는 폐기할 필요가 없다.", False),
    (", 이러한 견해는 유지한다.", False),
    (". 이러한 견해는 폐기한다.", False),                      # a new sentence: not tied to the citation
    ("; 이 사건에서는 다른 쟁점이다. 이러한 견해는 폐기한다.", False),
])
def test_parenthesis_pattern_variants(tail, found):
    t = f"당원은 종전에 달리 판시한 일이 있으나(1982. 12. 28. 선고 81다카545 판결 각 참조){tail}"
    assert bool(ps.find_evidence({"판례내용": t}, (1981, "다카", 545))["explicit"]) is found


def test_parenthesis_pattern_in_minority_opinion_is_not_evidence():
    # SYNTHETIC
    t = ("[대법관 가나다의 반대의견] 당원은 종전에 달리 판시한 일이 있으나(1982. 12. 28. 선고 81다카545 판결 각 참조), "
         "이러한 견해는 폐기한다.")
    assert ps.find_evidence({"판례내용": t}, (1981, "다카", 545))["explicit"] == []


def test_dissent_that_would_keep_the_case_is_not_evidence():
    # 94누14148's dissent: "다수의견에서 폐기하기로 하는 ... 93누21255 판결은 이를 유지하고"
    t = body("94누14148")["판례내용"]
    assert ps.find_evidence({"판례내용": "[반대의견] " + t.replace("이는", "이는")}, (1993, "누", 21255))["explicit"] == []


# ---- marker formats ------------------------------------------------------------------------------

def marker_of(name, key):
    ev = ps.find_evidence({"참조판례": REFS[name]["참조판례"]}, key)
    return [(e["evidence"], e["marker"], e["partial"]) for e in ev["explicit"]], ev["cited"]


@pytest.mark.parametrize("name,key,marker,partial", [
    ("97도985", (1993, "도", 1951), "(변경)", False),            # "(공1993하, 3120, 변경)": marker last in an info list
    ("97도985", (1995, "도", 1148), "(변경)", False),
    ("97다47637", (1979, "스", 9), "(폐기)", False),             # "결정[폐기]"
    ("91누8050", (1981, "누", 254), "(일부폐기)", True),         # partial
    ("66사2", (1964, "다", 104), "본결정으로 변경", False),       # ": 본결정으로 변경"
])
def test_marker_spellings(name, key, marker, partial):
    explicit, cited = marker_of(name, key)
    assert explicit == [("explicit_marker", marker, partial)] and cited == []


@pytest.mark.parametrize("name,key", [
    ("91다43848", (1966, "다", 1166)),     # "[본판결에 의하여 변경된 판결]" heading, cases after it
    ("91다43848", (1986, "다카", 2438)),
    ("93스14", (1981, "스", 19)),          # "/ [본결정에 의하여 변경된 결정]"
    ("80므60", (1966, "므", 11)),          # "【변경된 판례】" on its own line
    ("80다3286", (1972, "다", 1933)),      # plain "변경된 판결" line
])
def test_heading_list_marks_the_cases_after_it(name, key):
    explicit, cited = marker_of(name, key)
    assert explicit == [("explicit_marker", "(변경된 판례 목록)", False)] and cited == []


@pytest.mark.parametrize("name,key", [
    ("91다43848", (1970, "다", 1714)),     # listed BEFORE the heading: the supporting citation, not changed
    ("93스14", (1986, "스", 15)),          # before "/ [... 변경된 결정]"
    ("80므60", (1967, "므", 22)),
    ("80다3286", (1978, "다", 1485)),
    ("97도985", (1997, "도", 1)),
])
def test_cases_before_a_heading_are_not_marked(name, key):
    explicit, cited = marker_of(name, key)
    assert explicit == []
    if key != (1997, "도", 1):
        assert cited


def test_heading_list_stops_at_a_section_separator():
    # SYNTHETIC
    ref = ("[1] 대법원 1990. 1. 1. 선고 89다1 판결 / 변경된 판결 대법원 1980. 1. 1. 선고 79다2 판결 "
           "/ [2] 대법원 1991. 1. 1. 선고 90다3 판결")
    assert ps.find_evidence({"참조판례": ref}, (1979, "다", 2))["explicit"]
    assert ps.find_evidence({"참조판례": ref}, (1990, "다", 3))["explicit"] == []
    assert ps.find_evidence({"참조판례": ref}, (1989, "다", 1))["explicit"] == []


def test_marker_belongs_to_its_own_entry_in_info_list_form():
    # 97도985 [2]: only the entries carrying 변경 in their own parentheses are marked
    ref = REFS["97다36873"]["참조판례"]
    assert ps.find_evidence({"참조판례": ref}, (1979, "다", 2226))["explicit"]
    # SYNTHETIC: a bare info parenthesis without a marker is not a marker
    s = "대법원 1980. 2. 12. 선고 79다2226 판결(공1980, 12627), 대법원 1991. 11. 8. 선고 91다28955 판결(공1992, 82, 변경)"
    assert ps.find_evidence({"참조판례": s}, (1979, "다", 2226))["explicit"] == []
    assert ps.find_evidence({"참조판례": s}, (1991, "다", 28955))["explicit"]
    # SYNTHETIC: "변경" inside a parenthesis that is not a marker (e.g. 지목변경) is not one
    s2 = "대법원 1980. 2. 12. 선고 79다2226 판결(지목변경에 관한 사례)"
    assert ps.find_evidence({"참조판례": s2}, (1979, "다", 2226))["explicit"] == []


def test_partial_marker_is_medium_confidence():
    # the confidence field must not claim a full overruling for "(일부폐기)"
    r = REFS["91누8050"]
    got = ps.check_status(
        key=(1981, "누", 254), co_keys=[], case_text="81누254",
        target_row=row("81누254", "1983.06.14", "1"),
        search=lambda p: {"total": 1, "rows": [row("91누8050", "1993.01.19", "2", EB)]},
        service=lambda i: r)
    assert [(e["evidence"], e["confidence"]) for e in got["evidence"]] == [("explicit_marker", "medium")]


def test_case_in_an_earlier_supporting_parenthesis_is_not_tied_to_a_later_discarded_view():
    # 88다카33619 cites 79다1741 as support ("... 각 참조)."); only the NEXT sentence's parenthesis,
    # which lists 81다카545, is followed by "이러한 견해는 폐기한다"
    b = body("88다카33619")
    assert ps.find_evidence(b, (1979, "다", 1741))["explicit"] == []
    assert ps.find_evidence(b, (1979, "다", 1741))["cited"]
    assert ps.find_evidence(b, (1981, "다카", 545))["explicit"]
