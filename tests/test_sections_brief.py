"""Size-aware response modes (sections=brief/auto, offset/max_chars paging). Offline, synthetic texts only."""

import asyncio
import copy
import json
import os
from pathlib import Path

import pytest

import lexlink.server as server_mod
from lexlink import sizing
from lexlink._helpers import enforce_slim_limit
from lexlink.cache import get_cache
from lexlink.tool_policy import META_KEY

pytestmark = pytest.mark.unit

BR = "<br/>"


# ---------------------------------------------------------------- synthetic texts

def _para(tag: str, i: int, n: int = 700) -> str:
    return f"  {tag}{i}. " + ("가나다라마바사 " * (n // 8)).strip() + " 라고 할 것이다."


def make_body(majority_paras=20, opinions=True, closing=True, decoys=True, header_style="ok") -> str:
    parts = ["【원고, 상고인】 갑", "【주    문】", "  상고를 기각한다.", "", "【이    유】"]
    parts += [_para("본", i) for i in range(majority_paras)]
    if decoys:
        parts.append("  가. 대법관 박마바의 별개의견(이하 '별개의견2'라고 한다)이 타당하다고 보는 것과 같이한다.")
    parts.append("  4. 그러므로 상고를 기각하기로 하여 주문과 같이 판결한다.")
    if closing:
        parts.append("이 판결에는 대법관 김가나, 대법관 이다라의 반대의견과 대법관 박마바의 별개의견이 있는 외에는 관여 법관의 의견이 일치되었다.")
    if opinions:
        parts.append("  5. 대법관 김가나, 대법관 이다라의 반대의견은 다음과 같다." if header_style == "ok"
                     else "  5. 어떤 대법관들의 반대의견은 다음과 같다.")
        parts += [_para("반", i) for i in range(6)]
        if decoys:
            parts.append("  가. 다수의견의 입장은 타당하다. 그 구체적인 이유는 다음과 같다.")
        parts.append("  6. 대법관 박마바의 별개의견은 다음과 같다.")
        parts += [_para("별", i) for i in range(6)]
    return BR.join(parts)


def case_json(body: str, field="판례내용", extra=None) -> str:
    inner = {"사건명": "합성", "판시사항": "판시 " * 20, "판결요지": "요지 " * 30, "참조조문": "민법 제1조",
             "참조판례": "대법원 2000. 1. 1. 선고 2000다1 판결", field: body}
    inner.update(extra or {})
    return json.dumps({"PrecService": inner}, ensure_ascii=False)


class StubClient:
    calls: list = []
    payload: dict = {}

    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        StubClient.calls.append(dict(params))
        raw = StubClient.payload[params.get("target")]
        if (params.get("JO") or params.get("jo")) and "jo" in StubClient.payload:
            raw = StubClient.payload["jo"]
        return {"status": "ok", "request_id": "r", "upstream_type": response_type, "raw_content": raw}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    get_cache().invalidate()
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    StubClient.calls = []
    StubClient.payload = {}
    yield
    get_cache().invalidate()


@pytest.fixture
def call(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", StubClient)
    monkeypatch.setenv("OC", "test")
    server = server_mod.create_server()

    def _call(name, **kw):
        out = server._tool_manager.get_tool(name).fn(**kw)
        return asyncio.run(out) if asyncio.iscoroutine(out) else out
    _call.server = server
    return _call


def body_of(res, field="판례내용"):
    return json.loads(res["raw_content"])["PrecService"][field]


# ---------------------------------------------------------------- opinion map

def test_opinions_found_with_counts_and_boundary():
    body = make_body()
    info = sizing.analyze_opinions(body)
    assert info["state"] == "mapped"
    assert info["counts"] == {"반대": 1, "별개": 1}
    cut = body.index("이 판결에는")
    assert cut < info["majority_end"] <= body.index("5. 대법관")
    present, val = sizing.opinions_field(info)
    assert present and val == {"반대의견": 1, "별개의견": 1, "chars": len(body) - info["majority_end"]}


def test_opinions_null_when_unmappable():
    info = sizing.analyze_opinions(make_body(header_style="bad"))   # header names do not match the closing sentence
    assert info["state"] == "unknown"
    assert sizing.opinions_field(info) == (True, None)
    info = sizing.analyze_opinions(make_body(closing=False))       # headers but no closing sentence
    assert info["state"] == "unknown" and info["majority_end"] is None


def test_opinions_absent_for_plain_judgment():
    body = make_body(opinions=False, closing=False, decoys=False)
    info = sizing.analyze_opinions(body)
    assert info["state"] == "absent"
    assert sizing.opinions_field(info) == (False, None)


def test_decoy_headers_are_not_split_points():
    body = make_body()
    info = sizing.analyze_opinions(body)
    assert info["counts"] == {"반대": 1, "별개": 1}      # the two decoy lines add nothing
    starts = [s for s, _e, _l in info["segments"]]
    assert body.index("가. 대법관 박마바의 별개의견(이하") > 0
    assert all(body[s:s + 40] != "  가. 다수의견의 입장은" for s in starts)
    assert len(info["segments"]) == 3


def test_header_split_over_two_lines_is_joined():
    body = "  5. 대법관 김가나, 대법관 이다라의" + BR + "반대의견은 다음과 같다." + BR + "내용"
    body = "이 판결에는 대법관 김가나, 대법관 이다라의 반대의견이 있는 외에는 관여 법관의 의견이 일치하였다." + BR + body
    info = sizing.analyze_opinions(body)
    assert info["state"] == "mapped" and info["counts"] == {"반대": 1}


# ---------------------------------------------------------------- auto / explicit modes

def test_auto_small_is_full_identical_to_upstream(call):
    raw = case_json(make_body(majority_paras=6, opinions=False, closing=False, decoys=False))
    assert len(body_of({"raw_content": raw})) <= 20000
    StubClient.payload["prec"] = raw
    out = call("prec_service", id="1")
    assert out["raw_content"] == raw
    assert "truncated" not in out and "full_chars" not in out


def test_auto_large_is_brief(call):
    body = make_body()
    assert len(body) > 20000
    StubClient.payload["prec"] = case_json(body)
    out = call("prec_service", id="1")
    shown = body_of(out)
    first = shown.split("\n")[0]
    assert first.startswith("[축약본 · 전문 ") and f"전문 {len(body)}자 중" in first
    assert "이유 중간 생략" in first and "반대(" not in first and "반대 1, 별개 1" in first
    assert 'sections="full"' in first and "offset/max_chars" in first
    assert out["truncated"] is True and out["truncated_note"]
    d = out["truncated_detail"][0]
    assert d["field"] == "판례내용" and d["original_chars"] == len(body) and d["shown_chars"] < len(body)
    assert d["separate_opinions_omitted"] is True
    assert out["full_body_chars"] == len(body) and out["full_chars"] > len(body)
    assert out["full_opinions"]["반대의견"] == 1
    inner = json.loads(out["raw_content"])["PrecService"]
    assert inner["판시사항"] and inner["판결요지"] and inner["참조조문"] and inner["참조판례"]


def test_brief_layout(call):
    body = make_body()
    StubClient.payload["prec"] = case_json(body)
    out = call("prec_service", id="1", sections="brief")
    shown = body_of(out)
    assert shown.startswith("[축약본")
    assert "【주    문】" in shown and "상고를 기각한다." in shown
    assert "[…중략 " in shown
    assert "반대의견은 다음과 같다" not in shown and "별개의견은 다음과 같다" not in shown
    head_text, rest = shown.split("[…중략 ", 1)
    gap, tail = rest.split("…]", 1)
    maj_end = sizing.analyze_opinions(body)["majority_end"]
    expected_tail = body[maj_end - sizing.TAIL_CHARS:maj_end]
    assert tail.strip("\n") == expected_tail
    assert int(gap.strip("자")) > 0
    assert tail.rstrip().endswith("의견이 일치되었다.")


def test_brief_short_majority_is_whole_without_gap(call):
    body = make_body(majority_paras=6) + BR + _para("뒤", 0, 12000)   # pad after the opinions so total > 20k
    StubClient.payload["prec"] = case_json(body)
    out = call("prec_service", id="1", sections="brief")
    shown = body_of(out)
    maj = sizing.analyze_opinions(body)["majority_end"]
    assert maj <= sizing.WHOLE_MAJORITY_CHARS and "중략" not in shown and "이유 중간 생략" not in shown.split("\n")[0]
    assert shown.endswith(body[:maj])


def test_brief_without_closing_omits_tail_and_says_so(call):
    body = make_body(closing=False)
    StubClient.payload["prec"] = case_json(body)
    out = call("prec_service", id="1", sections="brief")
    shown = body_of(out)
    assert "구간 확인 불가로 뒤 조각 생략" in shown.split("\n")[0]
    assert "[…중략" not in shown
    assert out["full_opinions"] is None
    first_header = body.index("5. 대법관")
    assert len(shown) < first_header + 200       # nothing after the first separate-opinion header


def test_explicit_full_identical_and_never_brief(call):
    raw = case_json(make_body())
    StubClient.payload["prec"] = raw
    call("prec_service", id="1")                      # fills the cache with the FULL response
    assert call("prec_service", id="1", sections="full")["raw_content"] == raw
    assert len(StubClient.calls) == 1                 # served from cache, still the full text
    out = call("prec_service", id="1", sections="summary")
    assert len(StubClient.calls) == 1                 # summary no longer bypasses the cache
    assert "excluded for size" in body_of(out)
    assert out["full_body_chars"] == len(make_body())


def test_cache_holds_full_and_is_not_mutated(call):
    raw = case_json(make_body())
    StubClient.payload["prec"] = raw
    first = call("prec_service", id="1", sections="brief")
    assert body_of(first).startswith("[축약본")
    full = call("prec_service", id="1", sections="full")
    assert full["raw_content"] == raw and "truncated" not in full
    assert len(StubClient.calls) == 1   # one upstream fetch, the cached object is the full text


# ---------------------------------------------------------------- paging

def _chain(call, body, max_chars, name="prec_service", **kw):
    pages, off = [], None
    for _ in range(200):
        res = call(name, id="1", sections="full", max_chars=max_chars, **({"offset": off} if off is not None else {}), **kw)
        pages.append(res)
        off = res.get("next_offset")
        if off is None:
            return pages
    raise AssertionError("no end")


def test_paging_chain_covers_body_exactly_once(call):
    body = make_body()
    StubClient.payload["prec"] = case_json(body)
    pages = _chain(call, body, 5000)
    assert len(pages) > 3
    rebuilt, expect_start = "", 0
    for i, res in enumerate(pages):
        text = body_of(res)
        header, chunk = text.split("\n", 1)
        a, b = header.split("판례내용 ")[1].split("자 /")[0].split("~")
        assert int(a) - 1 == expect_start and f"전체 {len(body)}자" in header
        assert len(chunk) == int(b) - int(a) + 1 and len(chunk) <= 5000
        expect_start = int(b)
        rebuilt += chunk
        assert res["truncated"] is True and res["full_body_chars"] == len(body)
        assert ("next_offset" in res) == (i < len(pages) - 1)
        if i < len(pages) - 1:
            assert res["next_offset"] == int(b)
            assert chunk.endswith(BR) or chunk.endswith("\n")        # cut at a paragraph break
    assert rebuilt == body
    assert "판시사항" in json.loads(pages[0]["raw_content"])["PrecService"]
    assert "판시사항" not in json.loads(pages[1]["raw_content"])["PrecService"]
    assert json.loads(pages[1]["raw_content"])["PrecService"]["사건명"] == "합성"


def test_paging_header_names_segment_and_spans_boundary(call):
    body = make_body()
    StubClient.payload["prec"] = case_json(body)
    first = body_of(call("prec_service", id="1", sections="full", max_chars=1000)).split("\n")[0]
    assert first.endswith("· 다수의견]")
    maj = sizing.analyze_opinions(body)["majority_end"]
    span = body_of(call("prec_service", id="1", offset=maj - 300, max_chars=1000)).split("\n")[0]
    assert "다수의견" in span and "반대의견(김가나·이다라)" in span
    last = body_of(call("prec_service", id="1", offset=len(body) - 500, max_chars=1000)).split("\n")[0]
    assert "별개의견(박마바)" in last


def test_paging_default_size_and_omitted_sections(call):
    body = make_body()
    StubClient.payload["prec"] = case_json(body)
    res = call("prec_service", id="1", offset=0)
    chunk = body_of(res).split("\n", 1)[1]
    assert 0 < len(chunk) <= 20000 and res["next_offset"] == len(chunk)
    res = call("prec_service", id="1", max_chars=24000)
    assert len(body_of(res).split("\n", 1)[1]) <= 24000


def test_paging_whole_body_in_one_page_is_not_truncated(call):
    body = make_body(majority_paras=4, opinions=False, closing=False, decoys=False)
    StubClient.payload["prec"] = case_json(body)
    res = call("prec_service", id="1", max_chars=24000)
    assert "next_offset" not in res and "truncated" not in res
    assert body_of(res).split("\n", 1)[1] == body


@pytest.mark.parametrize("kw", [
    {"offset": -1}, {"max_chars": 999}, {"max_chars": 24001}, {"offset": "x"}, {"max_chars": True},
    {"sections": "brief", "offset": 0}, {"sections": "summary", "max_chars": 2000}, {"offset": 10 ** 9},
])
def test_case_validation_errors(call, kw):
    StubClient.payload["prec"] = case_json(make_body())
    assert call("prec_service", id="1", **kw)["error_code"] == "VALIDATION_ERROR"


def test_brief_and_paging_need_json(call):
    StubClient.payload["prec"] = "<x/>"
    assert call("prec_service", id="1", sections="brief", type="XML")["error_code"] == "VALIDATION_ERROR"
    assert call("prec_service", id="1", offset=0, type="XML")["error_code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("name,target,field", [("detc_service", "detc", "전문"), ("expc_service", "expc", "이유"),
                                               ("decc_service", "decc", "이유")])
def test_other_case_tools_follow_the_same_modes(call, name, target, field):
    body = make_body()
    StubClient.payload[target] = json.dumps({"X": {"사건명": "합성", field: body}}, ensure_ascii=False)
    out = call(name, id="1")
    assert json.loads(out["raw_content"])["X"][field].startswith("[축약본") and out["full_body_chars"] == len(body)
    paged = call(name, id="1", sections="full", max_chars=3000)
    assert json.loads(paged["raw_content"])["X"][field].startswith(f"[{field} 1~")
    assert call(name, id="1", sections="summary")["full_body_chars"] == len(body)
    assert call(name, id="1", sections="full")["raw_content"] == StubClient.payload[target]


# ---------------------------------------------------------------- SLIM + policy

def test_slim_applies_after_brief_and_keeps_truncation_fields(call, monkeypatch):
    StubClient.payload["prec"] = case_json(make_body())
    monkeypatch.setenv("SLIM_RESPONSE", "true")
    out = call("prec_service", id="1")
    assert out["truncated"] is True and len(json.dumps(out, ensure_ascii=False).encode()) < 30000
    assert any("판례내용: " in f and "자만 표시" in f for f in out["truncated_fields"])
    res = enforce_slim_limit({"status": "ok", "raw_content": "x" * 50000, "truncated": True,
                              "truncated_fields": ["a: 1자 중 0자만 표시"], "truncated_note": "앞선 안내"})
    assert res["truncated_fields"][0] == "a: 1자 중 0자만 표시" and res["truncated_note"].startswith("앞선 안내")


def test_policy_meta_still_on_every_tool(call):
    tools = asyncio.run(call.server.list_tools())
    assert len(tools) >= 66
    for t in tools:
        assert t.meta and META_KEY in t.meta, t.name
    names = {t.name for t in tools}
    assert {"prec_service", "detc_service", "expc_service", "decc_service", "law_service", "eflaw_service"} <= names
    props = {t.name: t.inputSchema["properties"] for t in tools}
    for n in ("prec_service", "detc_service", "expc_service", "decc_service", "law_service", "eflaw_service"):
        assert {"sections", "offset", "max_chars"} <= set(props[n])


# ---------------------------------------------------------------- laws

def law_json(n_units=40, per=900, chapters=True, extra=True) -> str:
    units = []
    for i in range(1, n_units + 1):
        if chapters and i % 10 == 1:
            units.append({"조문번호": str(i * 100), "조문여부": "전문", "조문내용": f"제{i // 10 + 1}장 총칙{i}"})
        units.append({"조문번호": str(i), "조문가지번호": "2" if i == 3 else "", "조문여부": "조문", "조문제목": f"제목{i}",
                      "조문내용": f"제{i}조(제목{i}) " + "가" * per, "항": [{"항내용": "①" + "나" * 50}]})
    law = {"기본정보": {"법령명_한글": "합성법", "법령ID": "000001"}, "조문": {"조문단위": units}}
    if extra:
        law["부칙"] = {"부칙단위": [{"부칙내용": "부칙 " * 10}]}
    return json.dumps({"법령": law}, ensure_ascii=False)


def test_law_jo_given_unchanged(call):
    StubClient.payload["law"] = law_json(n_units=40)
    StubClient.payload["jo"] = json.dumps({"법령": {"기본정보": {"법령명_한글": "합성법"},
                                                 "조문": {"조문단위": {"조문번호": "3", "조문내용": "제3조 본문"}}}}, ensure_ascii=False)
    out = call("law_service", mst="1", jo="000300")
    assert out["raw_content"] == StubClient.payload["jo"] and "lexlink_toc" not in out
    StubClient.payload["eflaw"] = StubClient.payload["law"]
    assert call("eflaw_service", mst="1", ef_yd="20200101", jo="000300")["raw_content"] == StubClient.payload["jo"]


def test_law_small_without_jo_is_full(call):
    raw = law_json(n_units=5, per=100)
    StubClient.payload["law"] = raw
    out = call("law_service", mst="1")
    assert out["raw_content"] == raw and "lexlink_toc" not in out


def test_law_large_without_jo_is_toc_brief_with_notice_in_raw_content(call):
    raw = law_json(n_units=40)
    StubClient.payload["law"] = raw
    out = call("law_service", mst="1")
    toc = out["lexlink_toc"]
    assert len(toc) == 44 and out["toc_total"] == 44 and "next_offset" not in out
    assert {"조문번호", "조문가지번호", "조문제목", "조문여부"} == set(toc[0])
    assert toc[0]["조문여부"] == "전문" and toc[1]["조문제목"] == "제목1"
    assert out["notice"] and out["truncated"] is True and out["full_body_chars"] > 20000
    data = json.loads(out["raw_content"])                       # still valid JSON
    law = data["법령"]
    assert "조문" not in law and "조문단위" not in out["raw_content"] and "부칙" not in law
    keys = list(law)
    assert keys[keys.index("기본정보") + 1] == "lexlink_notice"   # right after 기본정보
    assert law["lexlink_notice"] == out["notice"] and 'sections="full"' in law["lexlink_notice"]
    assert "offset" in law["lexlink_notice"]
    assert out["truncated_detail"][0]["field"] == "조문단위"
    assert sizing.toc_line(toc[3]) == "제3조의2 제목3"
    assert sizing.toc_line(toc[0]).startswith("제1장")


def test_law_toc_paging_and_explicit_brief(call):
    StubClient.payload["law"] = law_json(n_units=300, per=50, chapters=False)
    out = call("law_service", mst="1", sections="brief", max_chars=1000)
    assert out["next_offset"] < out["toc_total"] == 300
    seen, res = list(out["lexlink_toc"]), out
    while "next_offset" in res:
        res = call("law_service", mst="1", sections="brief", max_chars=1000, offset=res["next_offset"])
        seen += res["lexlink_toc"]
    assert [t["조문번호"] for t in seen] == [str(i) for i in range(1, 301)]


def test_law_brief_with_jo_adds_toc_and_keeps_article(call):
    StubClient.payload["law"] = law_json(n_units=40)
    jo_raw = json.dumps({"법령": {"기본정보": {"법령명_한글": "합성법"}, "조문": {"조문단위": {"조문번호": "3", "조문내용": "제3조 본문"}}}},
                        ensure_ascii=False)
    StubClient.payload["jo"] = jo_raw
    out = call("law_service", mst="1", jo="000300", sections="brief")
    assert out["raw_content"] == jo_raw and out["toc_total"] == 44 and len(out["lexlink_toc"]) == 44


def test_law_full_paging_over_units(call):
    raw = law_json(n_units=40, chapters=False)
    StubClient.payload["law"] = raw
    full = json.loads(raw)["법령"]["조문"]["조문단위"]
    got, off, first = [], None, None
    for _ in range(100):
        out = call("law_service", mst="1", sections="full", max_chars=5000, **({"offset": off} if off is not None else {}))
        law = json.loads(out["raw_content"])["법령"]
        units = law["조문"]["조문단위"]
        got += units
        first = first or law
        assert sum(len(sizing.article_unit_text(u)) for u in units) <= 5000 or len(units) == 1
        off = out.get("next_offset")
        if off is None:
            assert out["truncated"] is True
            break
    assert got == full and "부칙" in first and out["full_body_chars"] == sum(len(sizing.article_unit_text(u)) for u in full)
    explicit = call("law_service", mst="1", sections="full")
    assert explicit["raw_content"] == raw


def test_law_validation_errors(call):
    StubClient.payload["law"] = law_json()
    for kw in ({"sections": "summary"}, {"max_chars": 10}, {"offset": -3}, {"sections": "x"}):
        assert call("law_service", mst="1", **kw)["error_code"] == "VALIDATION_ERROR"
    assert call("eflaw_service", mst="1", ef_yd="20200101", sections="summary")["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- internal callers

def test_internal_callers_still_get_full_bodies_above_20k(monkeypatch):
    from lexlink import precedent_status
    body = make_body()
    assert len(body) > 20000
    StubClient.payload["prec"] = case_json(body)
    monkeypatch.setenv("OC", "test")
    from lexlink._helpers import run_service
    res = run_service(get_client=lambda: StubClient(), target="prec", sections="full",
                      snake_params={"oc": "test", "target": "prec", "id": "9", "type": "JSON"}, response_type="JSON")
    assert body_of(res) == body
    # the default of run_service itself is unchanged for every non-tool caller
    get_cache().invalidate()
    res = run_service(get_client=lambda: StubClient(), target="prec",
                      snake_params={"oc": "test", "target": "prec", "id": "9", "type": "JSON"}, response_type="JSON")
    assert body_of(res) == body
    # prec_status reads the body through its own service() helper
    parsed = precedent_status.parse_prec_service(res["raw_content"])
    assert parsed and len(json.dumps(parsed, ensure_ascii=False)) > 20000


# ---------------------------------------------------------------- real decisions (optional)

REAL = Path("/private/tmp/claude-501/-Users-minhancho-HypeProof-hypeproof-legal/a1fe05b7-d648-41b0-a2ad-f8f8e0b8b71d/scratchpad/v180/real")
REAL_EXPECT = {"2013므568": ("mapped", {"반대": 1}), "2010므4071": ("mapped", {"반대": 1, "별개": 2, "보충": 1}),
               "2013다61381": ("mapped", {"별개": 2, "반대": 1, "보충": 1})}


@pytest.mark.parametrize("name", sorted(REAL_EXPECT))
def test_real_decisions_if_present(name):
    f = REAL / f"{name}.txt"
    if not f.exists():
        pytest.skip("real decision text not available")
    body = json.loads(json.loads(f.read_text(encoding="utf-8"))["raw_content"])["PrecService"]["판례내용"]
    info = sizing.analyze_opinions(body)
    state, counts = REAL_EXPECT[name]
    assert (info["state"], info["counts"]) == (state, counts)
    if state == "mapped":
        assert 3000 < info["majority_end"] < len(body)


# ---------------------------------------------------------------- follow-ups: variants and page budget

def _variant_body() -> str:
    parts = ["【주    문】", "  상고를 기각한다.", "", "【이    유】"] + [_para("본", i) for i in range(18)]
    parts.append("  7. 이 판결에는 상고이유 제3점에 관한 판단에 대하여 대법관 김가나의 별개의견이 있고, 대법관 이다라, 대법관 박마바의 "
                 "반대의견이 있는 외에는 관여 법관의 의견이 일치되었으며, 대법관 최사아, 대법관 정자차의 다수의견에 대한 보충의견이 있다.")
    parts += ["  8. 상고이유 제3점에 관한 판단에 대한 대법관 김가나의 별개의견", _para("별", 0),
              "  9. 대법관 이다라, 대법관 박마바의 반대의견", _para("반", 0),
              "  10. 대법관 최사아, 대법관 정자차의 다수의견에 대한 보충의견", _para("보", 0)]
    return BR.join(parts)


def test_closing_variant_and_header_without_eun_dagateunda_map():
    body = _variant_body()
    info = sizing.analyze_opinions(body)
    assert info["state"] == "mapped" and info["counts"] == {"별개": 1, "반대": 1, "보충": 1}
    assert body[info["majority_end"] - 5:info["majority_end"]].endswith("있다.")   # end of the whole sentence
    assert "8. 상고이유" in body[info["majority_end"]:info["majority_end"] + 30]


def test_kind_only_header_and_two_line_join():
    body = ("이 판결에는 대법관 김가나, 대법관 이다라의 반대의견이 있는 외에는 관여 법관의 의견이 일치하였다." + BR
            + "  5. 대법관 김가나, 대법관" + BR + "이다라의 반대의견" + BR + "내용")
    assert sizing.analyze_opinions(body)["counts"] == {"반대": 1}
    assert sizing._header_body("5. 반대의견은 다음과 같다.") is not None      # KIND_ONLY
    assert sizing._header_body("5. 어떤 이유의 반대의견") is None             # no 대법관, not KIND_ONLY
    assert sizing._header_body("가. 대법관 박마바의 별개의견(이하 '별개의견2'라고 한다)이 같다.") is None


def test_first_page_budget_counts_other_fields(call):
    body = make_body()
    StubClient.payload["prec"] = case_json(body, extra={"판결요지": "요" * 6000})
    res = call("prec_service", id="1", sections="full", max_chars=10000)
    inner = json.loads(res["raw_content"])["PrecService"]
    others = sum(len(v) for k, v in inner.items() if isinstance(v, str) and k != "판례내용")
    text = inner["판례내용"]
    assert others + len(text) <= 10000
    assert len(text.split("\n", 1)[1]) >= 1000
    nxt = json.loads(call("prec_service", id="1", offset=res["next_offset"], max_chars=10000)["raw_content"])["PrecService"]["판례내용"]
    assert len(nxt) <= 10000 and len(nxt.split("\n", 1)[1]) > len(text.split("\n", 1)[1])
    small = call("prec_service", id="1", sections="full", max_chars=1000)
    assert 0 < len(body_of(small).split("\n", 1)[1]) <= 1000      # body budget floor is 1,000


def test_brief_budget_shrinks_head_then_tail(call):
    body = make_body()
    StubClient.payload["prec"] = case_json(body, extra={"판결요지": "요" * 18000})
    out = call("prec_service", id="1", sections="brief")
    inner = json.loads(out["raw_content"])["PrecService"]
    total = sum(len(v) for v in inner.values() if isinstance(v, str))
    assert total <= 24000
    shown = inner["판례내용"]
    maj_end = sizing.analyze_opinions(body)["majority_end"]
    assert shown.rstrip().endswith(body[maj_end - 100:maj_end].rstrip()[-30:])    # tail kept, head shrunk
    first = shown.split("\n")[0]
    assert f"전문 {len(body)}자 중 " in first
    assert out["truncated_detail"][0]["shown_chars"] < sizing.HEAD_CHARS + sizing.TAIL_CHARS + 700
    # even larger other fields: the tail shrinks as well
    StubClient.payload["prec"] = case_json(body, extra={"판결요지": "요" * 22500})
    get_cache().invalidate()
    out = call("prec_service", id="1", sections="brief")
    inner = json.loads(out["raw_content"])["PrecService"]
    assert sum(len(v) for v in inner.values() if isinstance(v, str)) <= 24000
