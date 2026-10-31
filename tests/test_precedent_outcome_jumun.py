"""Offline tests: check_precedent_odds classifies by 주문, never by recitals."""

import asyncio
import json

import pytest

import lexlink.server as server_mod
from lexlink._helpers import OUTCOME_NOTE, classify_order, extract_order
from lexlink.cache import get_cache

_ROWS = [
    # id, case number, 판결요지, 판례내용
    ("1", "2023다308270", "청구를 인용하는 판결이 선고·확정되었는데 ...",
     "【원심판결】 서울남부지법<br/>【주    문】<br/>  원심판결을 파기하고, 사건을 서울남부지방법원에 환송한다.<br/><br/>【이    유】<br/>청구를 인용하는 판결이 선고·확정되었는데"),
    ("2", "2025다210305", "",
     "[원고, 피상고인] 원고<br/>[주    문]<br/>상고를 기각한다. 상고비용은 피고가 부담한다.<br/><br/>[이    유]<br/>원고의 청구를 인용하여야 한다."),
    ("3", "2025부505", "", "【주 문】 이 사건 특별항고를 각하한다. 【이 유】 ..."),
    ("4", "2025나1", "", "【주    문】<br/>피고의 항소를 기각한다.<br/>【이    유】<br/>"),
    ("5", "2025가합1", "", "【주    문】<br/>1. 피고는 원고에게 1,000만 원을 지급하라.<br/>2. 원고의 나머지 청구를 기각한다.<br/>【이    유】"),
    ("6", "2025다2", "원심판결을 파기환송한다.", "【이    유】 주문 섹션이 없는 본문"),
]


class _Client:
    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        def ok(b):
            return {"status": "ok", "request_id": "f", "upstream_type": "JSON",
                    "raw_content": json.dumps(b, ensure_ascii=False)}
        if endpoint == "/DRF/lawSearch.do":
            rows = [{"판례일련번호": i, "사건명": f"사건{i}", "사건번호": no, "선고일자": "2024.01.01", "법원명": "대법원"}
                    for i, no, _, _ in _ROWS]
            return ok({"PrecSearch": {"totalCnt": str(len(rows)), "page": "1", "prec": rows}})
        row = next(r for r in _ROWS if r[0] == str(params.get("id") or params.get("ID")))
        return ok({"PrecService": {"사건명": "x", "판시사항": "", "판결요지": row[2], "판례내용": row[3]}})


@pytest.fixture
def odds(monkeypatch):
    get_cache().invalidate()
    monkeypatch.setattr(server_mod, "LawAPIClient", _Client)
    monkeypatch.setenv("OC", "unit-test-oc")
    asyncio.set_event_loop(asyncio.new_event_loop())
    srv = server_mod.create_server()
    yield lambda **kw: srv._tool_manager.get_tool("check_precedent_odds").fn(**kw)
    get_cache().invalidate()


@pytest.mark.unit
def test_odds_classifies_by_jumun_not_recital(odds):
    out = odds(query="x", display=10, top_n=6)
    by_no = {c["case_number"]: c["outcome"] for c in out["representative_cases"]}
    assert by_no["2023다308270"] == "파기환송"   # recital said 인용, 주문 says 파기환송
    assert by_no["2025다210305"] == "상고기각"   # recital "인용하여야" must not win
    assert by_no["2025부505"] == "각하"
    assert by_no["2025나1"] == "항소기각"
    assert by_no["2025가합1"] == "일부인용"
    assert by_no["2025다2"] == "불명"            # no 주문 -> no guess from 판결요지
    assert out["outcome_summary"]["불명"] == 1
    assert out["outcome_note"] == OUTCOME_NOTE and "승소율이 아닙니다" in OUTCOME_NOTE
    assert out["representative_cases"][0]["order"].startswith("원심판결을 파기하고")


@pytest.mark.unit
@pytest.mark.parametrize("order,label", [
    ("원심판결을 파기하고, 사건을 대전지방법원에 환송한다.", "파기환송"),
    ("원심판결 중 유죄 부분을 파기하고, 이 부분 사건을 창원지방법원에 환송한다.", "파기환송"),
    ("원심판결을 파기하고, 피고의 항소를 기각한다.", "파기자판"),
    ("상고를 모두 기각한다.", "상고기각"),
    ("재항고를 기각한다.", "상고기각"),
    ("원고의 항소를 기각한다.", "항소기각"),
    ("원고의 청구를 기각한다.", "기각"),
    ("소를 각하한다.", "각하"),
    ("원고의 청구를 인용한다.", "인용"),
    ("피고가 2023. 1. 1. 원고에 대하여 한 처분을 취소한다.", "취소"),
    ("제1심판결을 다음과 같이 변경한다.", "원판결변경"),
    ("피고는 원고에게 100원을 지급하라. 나머지 청구를 기각한다.", "일부인용"),
    ("원고의 본소청구를 기각한다. 피고는 반소로 100원을 지급하라.", "불명"),
    ("피고인을 징역 1년에 처한다.", "유죄"),
    ("피고인은 무죄. 이 사건 공소사실에 대하여 무죄를 선고한다.", "무죄"),
    ("피고인을 징역 1년에 처한다. 이 사건 공소사실 중 일부는 무죄를 선고한다.", "불명"),
    ("피고인을 벌금 100만 원에 처한다. 피고인은 피해자에게 100만 원을 지급하라. 위 지급명령은 가집행할 수 있다.", "유죄"),
    ("이 사건 공소를 기각한다.", "공소기각"),
    ("피고인은 무죄.", "무죄"),
    ("피고인 1을 징역 4년에, 피고인 2를 징역 3년 6월에 각 처한다. 피고인 2에 대한 공소를 기각한다.", "불명"),
    ("피고인 1을 징역 6월, 피고인 2를 징역 1년에 각 처한다.", "유죄"),
    ("1. 제1심심판을 취소한다. 2. 상대방은 청구인에게 양육비를 지급하라.", "원판결변경"),
    ("1. 제1심 심판 중 상대방 패소 부분을 취소하고, 그 취소 부분에 해당하는 청구를 기각한다. 2. 청구인의 항고를 기각한다.", "원판결변경"),
    ("중앙노동위원회가 한 재심판정을 취소한다. 소송비용은 피고가 부담한다.", "취소"),
    ("피고인을 징역 3년에 각 처한다.", "유죄"),
    # review round 2 (minimal text from real cases)
    ("원심판결 중 피고 패소 부분을 파기한다. 위 파기 부분에 대한 피고의 항소를 기각한다. 나머지 상고를 기각한다.", "파기자판"),
    ("원심결정을 파기하고, 항고를 기각한다.", "파기자판"),
    ("원심판결을 파기한다. 사건을 서울고등법원에 환송한다.", "파기환송"),
    ("원심판결을 파기한다. 나머지 상고를 기각한다. 파기 부분 사건을 서울고등법원에 환송한다.", "파기환송"),
    ("제1심판결을 취소하고, 사건을 서울행정법원에 환송한다.", "파기환송"),
    ("원심결정을 취소한다. 사건을 수원지방법원에 환송한다.", "파기환송"),
    ("1. 제1심판결 중 피고 패소 부분을 일부 취소한다. 2. 피고는 원고에게 100원을 지급하라. 3. 원고의 나머지 항소를 기각한다.", "원판결변경"),
    ("제1심판결을 취소한다. 이 사건 소 중 일부를 각하한다. 나머지 청구를 기각한다.", "원판결변경"),
    ("피고인의 항소를 기각한다. 배상명령 신청을 각하한다. 피고인은 피해자에게 100원을 지급하라.", "항소기각"),
    ("피고인에게 배상명령 100원을 지급하라.", "불명"),
    ("원고의 항소를 기각한다. 소송비용은 원고가 부담한다. 피고는 원고에게 100원을 지급하라.", "불명"),
    ("상고를 기각하지 아니한다.", "불명"),
    ("", "불명"),
])
def test_classify_order(order, label):
    assert classify_order(order) == label


@pytest.mark.unit
def test_extract_order_stops_at_any_following_heading():
    t = "【주    문】<br/>피고의 항소를 기각한다.<br/><br/>【청구취지 및 항소취지】<br/>피고는 100원을 지급하라.<br/>【이    유】x"
    assert extract_order(t) == "피고의 항소를 기각한다."
    assert classify_order(extract_order(t)) == "항소기각"
    t = "[주    문]<br/>상고를 기각한다.<br/>[항고취지]<br/>원심결정을 취소한다.<br/>[이    유]"
    assert extract_order(t) == "상고를 기각한다."
    t = "【주    문】<br/>소를 각하한다.<br/>【재항고취지】원심판결을 파기한다.【이 유】"
    assert extract_order(t) == "소를 각하한다."


@pytest.mark.unit
def test_extract_order_variants():
    assert extract_order("") == ""
    assert extract_order("이유만 있음") == ""
    assert extract_order("[주    문]<br/>상고를 기각한다.<br/>[이    유]x") == "상고를 기각한다."
    assert extract_order("【주문】 소를 각하한다.【이유】x") == "소를 각하한다."
