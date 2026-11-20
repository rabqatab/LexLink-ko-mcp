"""law_as_of: in_force_period, data_warnings (stale upstream snapshots) and period paging.

Fixtures: the 민법 version rows and the 제1019조 / 제837조 texts below are VERBATIM (trimmed) from
law.go.kr as measured 2026-11-20 (MST 58429 / 60400 / 67272 / 81988 / 79107 / 93194). Rows and texts
for the laws named 합성* are SYNTHETIC (invented, labelled) and exercise the rules without real data.
"""

import pytest

import lexlink.server as server_mod
from lexlink.as_of import (announcement_inversion, assess_snapshot, build_candidates,
                           flip_back_rows, paragraph_count)
import test_law_as_of as base
from test_law_as_of import FakeClient, _row, as_of  # noqa: F401  (as_of fixture)

# ---- VERBATIM: 민법 (LID 001706) version list, trimmed to 2002..2009 + current
CIVIL = [
    _row("001706", "민법", "58429", "20020114", "20020114", "06591", "일부개정", "연혁"),
    _row("001706", "민법", "60400", "20020701", "20011229", "06544", "일부개정", "연혁"),
    _row("001706", "민법", "67272", "20050331", "20050331", "07427", "일부개정", "연혁"),
    _row("001706", "민법", "81988", "20071221", "20071221", "08720", "일부개정", "연혁"),
    _row("001706", "민법", "79107", "20080101", "20070517", "08435", "타법개정", "연혁"),
    _row("001706", "민법", "93194", "20090809", "20090508", "09650", "일부개정", "연혁"),
    _row("001706", "민법", "284415", "20260317", "20260317", "21454", "일부개정", "현행"),
]
A1019_P = ("제1019조(승인, 포기의 기간)\n①상속인은 상속개시있음을 안 날로부터 3월내에 단순승인이나 한정승인 또는 포기를 할 수 있다. "
           "그러나 그 기간은 이해관계인 또는 검사의 청구에 의하여 가정법원이 이를 연장할 수 있다. <개정 1990.1.13>\n"
           "②상속인은 제1항의 승인 또는 포기를 하기 전에 상속재산을 조사할 수 있다. <개정 2002.1.14>\n"
           "③제1항의 규정에 불구하고 상속인은 상속채무가 상속재산을 초과하는 사실을 중대한 과실없이 제1항의 기간내에 알지 못하고 "
           "단순승인(제1026조제1호 및 제2호의 규정에 의하여 단순승인한 것으로 보는 경우를 포함한다)을 한 경우에는 그 사실을 안 날부터 "
           "3월내에 한정승인을 할 수 있다. <신설 2002.1.14>")
A1019_STALE = A1019_P.split("\n③")[0].replace("<개정 2002.1.14>", "").replace("제1항의 승인", "전항의 승인")
A837_OLD = ("제837조(이혼과 자의 양육책임)\n①당사자는 그 자의 양육에 관한 사항을 협의에 의하여 정한다. <개정 1990.1.13>\n"
            "②제1항의 양육에 관한 사항의 협의가 되지 아니하거나 협의할 수 없는 때에는 가정법원은 당사자의 청구 또는 직권에 의하여 "
            "그 자의 연령, 부모의 재산상황 기타 사정을 참작하여 양육에 필요한 사항을 정하며 언제든지 그 사항을 변경 또는 다른 적당한 "
            "처분을 할 수 있다. <개정 1990.1.13, 2005.3.31>\n③제2항의 규정은 양육에 관한 사항외에는 부모의 권리의무에 변경을 "
            "가져오지 아니한다. <개정 1990.1.13>")
A837_NEW = ("제837조(이혼과 자의 양육책임)\n①당사자는 그 자의 양육에 관한 사항을 협의에 의하여 정한다. <개정 1990.1.13>\n"
            "② 제1항의 협의는 다음의 사항을 포함하여야 한다. <개정 2007.12.21>\n1. 양육자의 결정\n2. 양육비용의 부담\n"
            "3. 면접교섭권의 행사 여부 및 그 방법\n③ 제1항에 따른 협의가 자(子)의 복리에 반하는 경우에는 가정법원은 보정을 명하거나 "
            "직권으로 그 자(子)의 의사(意思)ㆍ연령과 부모의 재산상황, 그 밖의 사정을 참작하여 양육에 필요한 사항을 정한다. <개정 2007.12.21>")
A836_2 = "제836조의2(이혼의 절차)\n① 협의상 이혼을 하려는 자는 가정법원이 제공하는 이혼에 관한 안내를 받아야 한다. <신설 2007.12.21>"

# ---- SYNTHETIC rows (not real): 합성역전법 has a 공포-order inversion (MST 703 promulgated before 702, in force after it)
SYN = [
    _row("009100", "합성역전법", "701", "20100101", "20091201", "1", "제정", "연혁"),
    _row("009100", "합성역전법", "702", "20110101", "20100601", "2", "일부개정", "연혁"),
    _row("009100", "합성역전법", "703", "20110701", "20100501", "3", "일부개정", "연혁"),   # 공포 < 702's
    _row("009100", "합성역전법", "704", "20120101", "20111101", "4", "일부개정", "현행"),
    # 합성정상법: ordinary history, 공포 order == 시행 order
    _row("009200", "합성정상법", "801", "20100101", "20091201", "1", "제정", "연혁"),
    _row("009200", "합성정상법", "802", "20110101", "20101201", "2", "일부개정", "연혁"),
    _row("009200", "합성정상법", "803", "20120101", "20111201", "3", "일부개정", "현행"),
    # 합성지연법: inversion, but the delayed amendment's body is complete (identical wording) -> no warning
    _row("009300", "합성지연법", "901", "20100101", "20091201", "1", "제정", "연혁"),
    _row("009300", "합성지연법", "902", "20110101", "20100601", "2", "일부개정", "연혁"),
    _row("009300", "합성지연법", "903", "20110701", "20100501", "3", "일부개정", "현행"),
] + [  # 합성다량법: 25 revisions
    _row("009400", "합성다량법", str(1000 + i), f"{2000 + i}0101", f"{1999 + i}1201", str(i + 1), "일부개정",
         "현행" if i == 24 else "연혁") for i in range(25)
]
OLDW, NEWW = "제1조(목적) 이 법은 구문언을 따른다.", "제1조(목적) 이 법은 신문언을 따른다."
BODIES = {
    ("58429", "20020114"): {"제1019조": A1019_P},
    ("60400", "20020701"): {"제1019조": A1019_STALE},
    ("81988", "20071221"): {"제837조": A837_NEW, "제836조의2": A836_2},
    ("79107", "20080101"): {"제837조": A837_OLD},
    ("93194", "20090809"): {"제837조": A837_NEW, "제836조의2": A836_2},
    ("701", "20100101"): {"제1조": OLDW}, ("702", "20110101"): {"제1조": NEWW},
    ("703", "20110701"): {"제1조": OLDW}, ("704", "20120101"): {"제1조": NEWW},
    ("801", "20100101"): {"제1조": OLDW}, ("802", "20110101"): {"제1조": NEWW}, ("803", "20120101"): {"제1조": NEWW},
    ("901", "20100101"): {"제1조": OLDW}, ("902", "20110101"): {"제1조": NEWW}, ("903", "20110701"): {"제1조": NEWW},
}
BODIES.update({(str(1000 + i), f"{2000 + i}0101"): {"제1조": f"제1조 {2000 + i}년 문언"} for i in range(25)})


@pytest.fixture
def w(monkeypatch, as_of):
    monkeypatch.setattr(base, "ROWS", base.ROWS + CIVIL + SYN)
    for k, v in BODIES.items():
        monkeypatch.setitem(base.BODIES, k, v)
    return as_of


def _n(t):
    return "".join(t.split())


def codes(out):
    return [x["code"] for x in out["data_warnings"]]


# ---- (a) paragraphs missing: 민법 제1019조 on 2003-01-01 (VERBATIM)
def test_a_missing_paragraph_warns_and_text_is_untouched(w):
    out = w(law_name="민법", as_of="20030101", article=1019)
    assert out["in_force"] is True and out["version"]["mst"] == "60400"
    assert _n(out["article"]["text"]) == _n(A1019_STALE)   # never altered
    assert codes(out) == ["SUSPECT_SNAPSHOT_PARAGRAPHS_DROPPED"]
    assert out["data_warnings"][0]["compared_with_mst"] == "58429"
    assert out["announcement_order_inversion"]["earlier_effective_version"]["mst"] == "58429"
    assert "data_warnings" in out["statement"]


# ---- (b) article missing in the chosen version but present in the neighbours: 제836조의2 on 2008-02-01
def test_b_article_missing_error_carries_warning(w):
    out = w(law_name="민법", as_of="20080201", article=836, article_branch=2)
    assert out["status"] == "error" and out["error_code"] == "ARTICLE_NOT_FOUND"   # still reported as absent
    assert codes(out) == ["SUSPECT_SNAPSHOT_ARTICLE_MISSING"]
    assert set(out["data_warnings"][0]["present_in"]) == {"previous", "next", "announced_later"}
    assert out["in_force_period"] == {"start": "20080101", "end": "20090808", "end_inclusive": True, "open_ended": False}


# ---- (c) wording flips back: 제837조 on 2008-02-01 (VERBATIM); 가사소송법 제2조 behaves the same
def test_c_old_wording_between_new_wordings(w):
    out = w(law_name="민법", as_of="20080201", article=837)
    assert _n(out["article"]["text"]) == _n(A837_OLD) and codes(out) == ["SUSPECT_SNAPSHOT_WORDING_FLIP"]   # trimmed to 3 항, so not a paragraph drop
    p = w(law_name="민법", as_of="20071225", as_of_end="20091231", article=837)["period"]
    assert [r["version"]["mst"] for r in p["revisions"]] == ["81988", "79107", "93194"]
    # period mode finds the flip with no extra upstream call and flags the out-of-order version
    ws = w(law_name="민법", as_of="20071225", as_of_end="20091231", article=837)["data_warnings"]
    assert [x["code"] for x in ws] == ["SUSPECT_SNAPSHOT_WORDING_FLIP_BETWEEN_IDENTICAL_VERSIONS"]
    assert ws[0]["mst"] == "79107" and ws[0]["identical_before_and_after_mst"] == ["81988", "93194"]
    assert ws[0]["version_announced_out_of_order"] is True


def test_synthetic_wording_flip_with_equal_paragraph_count(w):
    # SYNTHETIC: 703 (공포 before 702, 시행 after) serves 702's predecessor wording; 704 is new again
    out = w(law_name="합성역전법", as_of="20110801", article=1)
    assert out["version"]["mst"] == "703" and out["article"]["text"] == OLDW
    assert codes(out) == ["SUSPECT_SNAPSHOT_WORDING_FLIP"]


def test_no_false_warning_on_ordinary_and_on_harmless_inversion(w):
    for law, d in (("합성정상법", "20110601"), ("합성지연법", "20110801"), ("테스트법", "20190101")):
        out = w(law_name=law, as_of=d, article=1)
        assert out["data_warnings"] == [], (law, out["data_warnings"])
    # harmless inversion still exposes the neutral flag
    assert w(law_name="합성지연법", as_of="20110801", article=1)["announcement_order_inversion"] is not None
    assert w(law_name="합성정상법", as_of="20110601", article=1)["announcement_order_inversion"] is None


def test_header_only_inversion_is_a_notice(w):
    out = w(law_name="민법", as_of="20080201")
    assert [(x["code"], x["severity"]) for x in out["data_warnings"]] == [("ANNOUNCEMENT_ORDER_INVERSION", "notice")]


# ---- (e) in_force_period
def test_in_force_period_fields(w):
    out = w(law_name="민법", as_of="20030101", article=1019)
    assert out["in_force_period"] == {"start": "20020701", "end": "20050330", "end_inclusive": True, "open_ended": False}
    assert out["valid_from"] == "20020701" and out["valid_until"] == "20050330"      # legacy aliases agree
    assert out["article"]["in_force_period"]["end"] == "20050330"
    assert out["article"]["in_force_period"]["upstream_article_effective_date"] == "20020701"
    cur = w(law_name="민법", as_of="20270101")
    assert cur["in_force_period"] == {"start": "20260317", "end": None, "end_inclusive": True, "open_ended": True}
    row = w(law_name="합성정상법", as_of="20100601", as_of_end="20120601")["period"]["revisions"][0]
    assert row["in_force_period"]["start"] == "20100101" and row["in_force_period"]["end"] == "20101231"
    assert row["valid_from"] == "20100601"     # valid_* is clipped to the query, in_force_period is not


# ---- (d) period paging
def test_period_paging_with_cursor(w):
    first = w(law_name="합성다량법", as_of="20000101", as_of_end="20300101", article=1)
    p = first["period"]
    assert p["truncated"] is True and p["revision_count"] == 20 and p["total_revisions_in_period"] == 25
    assert p["remaining_revisions"] == 5 and p["next_cursor"] == "20190101"
    assert p["article_changed_scope"] == "returned_revisions_only"
    assert "period_after=20190101" in " ".join(first["caveats"])
    FakeClient.calls = []
    second = w(law_name="합성다량법", as_of="20000101", as_of_end="20300101", article=1, period_after=p["next_cursor"])
    q = second["period"]
    assert [r["version"]["effective_date"] for r in q["revisions"]] == [f"{2020 + i}0101" for i in range(5)]
    assert "truncated" not in q and q["continued_after"] == "20190101"
    # the continuation fetches only its own revisions' articles (+ the usual header / current comparison calls)
    assert len([c for c in FakeClient.calls if c[1].get("JO")]) <= 5 + 2


def test_period_after_needs_as_of_end(w):
    out = w(law_name="합성다량법", as_of="20000101", article=1, period_after="20100101")
    assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR"


# ---- pure helpers
def test_pure_helpers_and_mutation_guards():
    c = build_candidates(CIVIL)
    by = {x["mst"]: x for x in c}
    assert announcement_inversion(c, by["60400"])["mst"] == "58429"
    assert announcement_inversion(c, by["58429"]) is None
    assert announcement_inversion(c, by["93194"]) is None            # 공포 2009 is after every earlier one
    assert paragraph_count(A1019_P) == 3 and paragraph_count(A1019_STALE) == 2
    assert assess_snapshot(A1019_STALE, A1019_P) == "PARAGRAPHS_DROPPED"
    assert assess_snapshot(None, A1019_P) == "ARTICLE_MISSING"
    assert assess_snapshot(OLDW, NEWW, NEWW) == "REVERTS_TO_EARLIER_WORDING"
    assert assess_snapshot(OLDW, NEWW, None) is None                 # no next version known: no verdict
    assert assess_snapshot(NEWW, NEWW, NEWW) is None and assess_snapshot(NEWW, NEWW) is None and assess_snapshot(A1019_P, None) is None
    assert flip_back_rows([OLDW, NEWW, OLDW]) == [(1, "REVERTS_TO_EARLIER_WORDING")]
    assert flip_back_rows([OLDW, None, OLDW]) == [(1, "ARTICLE_MISSING")]
    assert flip_back_rows([OLDW, NEWW, NEWW]) == [] and flip_back_rows([OLDW, NEWW]) == []
