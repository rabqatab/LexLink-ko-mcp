"""Offline tests for law_as_of (version in force on a date D). No OC / network needed.

The fake upstream mimics law.go.kr: eflaw list rows are one per (MST, 시행일자);
lawService target=eflaw serves a body per exact (MST, efYd) pair and fails for
any other pair; name search (no nw) only sees 현행 rows.
"""

import json

import pytest

import lexlink.server as server_mod
from lexlink.as_of import normalize_as_of

TODAY = "20260615"


def _row(lid, name, mst, ef, pub, pubno, kind, status):
    return {"현행연혁코드": status, "법령일련번호": mst, "법령명한글": name, "법령구분명": "법률",
            "소관부처명": "테스트부", "공포번호": pubno, "제개정구분명": kind, "법령ID": lid,
            "시행일자": ef, "공포일자": pub, "법령약칭명": ""}


T = "테스트법"
ROWS = [
    _row("009999", T, "100", "20100101", "20091201", "1000", "제정", "연혁"),
    _row("009999", T, "200", "20150101", "20141201", "2000", "일부개정", "연혁"),
    _row("009999", T, "300", "20180301", "20171201", "3000", "일부개정", "연혁"),
    _row("009999", T, "300", "20180901", "20171201", "3000", "일부개정", "연혁"),
    _row("009999", T, "400", "20200101", "20191201", "4000", "일부개정", "연혁"),
    _row("009999", T, "410", "20200101", "20191215", "4100", "일부개정", "현행"),
    _row("009999", T, "500", "20271201", "20261001", "5000", "일부개정", "시행예정"),
    _row("008888", "폐지법", "10", "20000101", "19991201", "10", "제정", "연혁"),
    _row("008888", "폐지법", "11", "20050301", "20050101", "11", "타법폐지", "연혁"),
]

# (mst, ef) -> {article label -> text}
BODIES = {
    ("100", "20100101"): {"제1조": "제1조(목적) v1", "제2조": "제2조(정의) A"},
    ("200", "20150101"): {"제1조": "제1조(목적) v2", "제2조": "제2조(정의) A"},
    ("300", "20180301"): {"제1조": "제1조(목적) v3a", "제2조": "제2조(정의) A"},
    ("300", "20180901"): {"제1조": "제1조(목적) v3b", "제2조": "제2조(정의) A", "제3조의2": "제3조의2(신설) X"},
    ("400", "20200101"): {"제1조": "제1조(목적) v4", "제2조": "제2조(정의) A"},
    ("410", "20200101"): {"제1조": "제1조(목적) v4b", "제2조": "제2조(정의) A", "제3조의2": "제3조의2(신설) X"},
    ("500", "20271201"): {"제1조": "제1조(목적) v5", "제2조": "제2조(정의) A", "제3조의2": "제3조의2(신설) X"},
    ("10", "20000101"): {"제1조": "제1조 옛 폐지법"},
}


def _article_body(mst, ef, label):
    row = next(r for r in ROWS if r["법령일련번호"] == mst and r["시행일자"] == ef)
    body = {"법령": {"기본정보": {"법령명_한글": row["법령명한글"], "법령ID": row["법령ID"],
                                 "시행일자": ef, "공포일자": row["공포일자"]}}}
    text = BODIES.get((mst, ef), {}).get(label)
    if text:
        num = label[1:].split("조")[0]
        branch = label.split("조의")[1] if "조의" in label else ""
        unit = {"조문번호": num, "조문내용": text, "조문시행일자": ef, "조문변경여부": "N"}
        if branch:
            unit["조문가지번호"] = branch
        body["법령"]["조문"] = {"조문단위": unit}
    return json.dumps(body, ensure_ascii=False)


class FakeClient:
    calls: list = []
    fail: dict = {}  # key -> error response ("search", "history", "service")

    def __init__(self, *a, **k):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        FakeClient.calls.append((endpoint, dict(params)))
        if endpoint == "/DRF/lawSearch.do":
            kind = "history" if params.get("LID") else "search"
            if kind in FakeClient.fail:
                return dict(FakeClient.fail[kind])
            rows = ROWS
            if params.get("LID"):
                rows = [r for r in rows if r["법령ID"] == params["LID"]]
            else:
                q = params["query"].replace(" ", "")
                rows = [r for r in rows if q in r["법령명한글"]]
            if not params.get("nw"):
                rows = [r for r in rows if r["현행연혁코드"] == "현행"]
            body = {"LawSearch": {"totalCnt": str(len(rows)), "page": "1", "law": rows}}
            return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                    "raw_content": json.dumps(body, ensure_ascii=False)}
        if "service" in FakeClient.fail:
            return dict(FakeClient.fail["service"])
        mst, ef, jo = params.get("MST"), params.get("efYd"), params.get("JO")
        if params.get("target") != "eflaw" or (mst, ef) not in {(r["법령일련번호"], r["시행일자"]) for r in ROWS}:
            return {"status": "error", "error_code": "NOT_FOUND", "message": "일치하는 법령이 없습니다", "request_id": "fake"}
        num, branch = int(jo[:4]), int(jo[4:])
        label = f"제{num}조" + (f"의{branch}" if branch else "")
        return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                "raw_content": _article_body(mst, ef, label)}


@pytest.fixture
def as_of(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", FakeClient)
    monkeypatch.setattr(server_mod, "_today", lambda: TODAY)
    monkeypatch.setenv("OC", "test")
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    FakeClient.calls = []
    FakeClient.fail = {}
    from lexlink.cache import get_cache
    get_cache().invalidate()
    server = server_mod.create_server()
    return lambda **kw: server._tool_manager.get_tool("law_as_of").fn(**kw)


def service_calls():
    return [p for e, p in FakeClient.calls if e == "/DRF/lawService.do"]


# ------------------------------------------------------------------ date normalization

@pytest.mark.parametrize("raw", ["2016-05-03", "2016.5.3.", "2016.05.03", "20160503", 20160503,
                                 "2016/5/3", "2016년 5월 3일", " 20160503 "])
def test_normalize_formats(raw):
    assert normalize_as_of(raw) == "20160503"


@pytest.mark.parametrize("raw", ["20160231", "2016-02-30", "2016-13-01", "abc", "", None, "2016-5", "1800-01-01", "20161"])
def test_normalize_rejects(raw):
    with pytest.raises(ValueError):
        normalize_as_of(raw)


def test_invalid_date_is_validation_error_without_upstream(as_of):
    out = as_of(law_name=T, as_of="20160231")
    assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR"
    assert FakeClient.calls == []


# ------------------------------------------------------------------ boundaries

def test_before_first_enforcement(as_of):
    out = as_of(law_name=T, as_of="2009-12-31", article=1)
    assert out["status"] == "ok" and out["in_force"] is False
    assert out["reason"] == "BEFORE_FIRST_ENFORCEMENT"
    assert out["first_version"]["effective_date"] == "20100101"
    assert "20091231" in out["statement"] and "article" not in out
    assert service_calls() == []


def test_exact_effective_date_and_day_before(as_of):
    on = as_of(law_name=T, as_of="20150101", article=1)
    before = as_of(law_name=T, as_of="20141231", article=1)
    assert on["version"]["mst"] == "200" and on["valid_from"] == "20150101"
    assert on["article"]["text"].endswith("v2")
    assert before["version"]["mst"] == "100" and before["valid_until"] == "20141231"
    assert before["article"]["text"].endswith("v1")


def test_first_day_in_force(as_of):
    out = as_of(law_name=T, as_of="20100101", article=2)
    assert out["in_force"] is True and out["version"]["mst"] == "100"
    assert out["version"]["revision_type"] == "제정"


def test_multiple_effective_dates_of_one_mst(as_of):
    a = as_of(law_name=T, as_of="20180301", article=1)
    b = as_of(law_name=T, as_of="20180831", article=1)
    c = as_of(law_name=T, as_of="20180901", article=1)
    assert a["version"]["mst"] == b["version"]["mst"] == c["version"]["mst"] == "300"
    assert a["version"]["effective_date"] == b["version"]["effective_date"] == "20180301"
    assert c["version"]["effective_date"] == "20180901"
    assert a["article"]["text"].endswith("v3a") and b["article"]["text"].endswith("v3a")
    assert c["article"]["text"].endswith("v3b")
    assert c["partial_effect"] == {"possible": True, "mst_effective_dates": ["20180301", "20180901"],
                                   "note": c["partial_effect"]["note"]}
    assert a["valid_until"] == "20180831"
    # the exact (MST, efYd) pair is requested, not just the MST
    assert {"MST": "300", "efYd": "20180901"}.items() <= service_calls()[-1].items()


def test_same_day_versions_pick_latest_promulgated(as_of):
    out = as_of(law_name=T, as_of="20200101", article=1)
    assert out["version"]["mst"] == "410"
    assert [v["mst"] for v in out["same_day_alternatives"]] == ["400"]
    assert any("같은 시행일" in c for c in out["caveats"])


def test_article_absent_in_that_version(as_of):
    out = as_of(law_name=T, as_of="2018-08-31", article="3의2")
    assert out["status"] == "error" and out["error_code"] == "ARTICLE_NOT_FOUND"
    assert out["as_of"] == "20180831" and out["version"]["mst"] == "300"
    assert "20180831" in out["message"] and "20180301" in out["message"]
    ok = as_of(law_name=T, as_of="2018-09-01", article=3, article_branch=2)
    assert ok["article"]["label"].startswith("제3조의2") and ok["article"]["text"].startswith("제3조의2")


def test_future_date_uses_pending_version(as_of):
    out = as_of(law_name=T, as_of="20271201", article=1)
    assert out["version"]["mst"] == "500" and out["version"]["status"] == "시행예정"
    assert out["is_future_version"] is True and out["valid_until"] is None
    assert out["comparison"]["is_current_version"] is False
    assert out["comparison"]["differs_from_current"] is True
    assert any("시행예정" in c for c in out["caveats"])
    gap = as_of(law_name=T, as_of="20270101", article=1)  # before 500 takes effect
    assert gap["version"]["mst"] == "410" and gap["valid_until"] == "20271130"


def test_repealed_law(as_of):
    before = as_of(law_name="폐지법", as_of="20050228", article=1)
    assert before["in_force"] is True and before["version"]["mst"] == "10"
    assert before["comparison"]["current_state"] == "repealed"
    assert before["comparison"]["differs_from_current"] is True
    on = as_of(law_name="폐지법", as_of="20050301")
    after = as_of(law_name="폐지법", as_of="2030-01-01", article=1)
    for out in (on, after):
        assert out["status"] == "ok" and out["in_force"] is False and out["reason"] == "AFTER_REPEAL"
        assert out["repealed_on"] == "20050301"
        assert out["last_version_before_repeal"]["mst"] == "10"
    pre = as_of(law_name="폐지법", as_of="19990101")
    assert pre["reason"] == "BEFORE_FIRST_ENFORCEMENT"


def test_law_by_id(as_of):
    out = as_of(law_name="9999", as_of="20150601", article=1)
    assert out["law"]["law_id"] == "009999" and out["law"]["law_name"] == T
    assert out["version"]["mst"] == "200"
    assert not any(p.get("query") for e, p in FakeClient.calls)


def test_unknown_law_is_validation_error(as_of):
    out = as_of(law_name="없는법령", as_of="20150101")
    assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------------ output content

def test_header_only_without_article(as_of):
    out = as_of(law_name=T, as_of="20160101")
    assert out["in_force"] is True and "article" not in out
    assert out["version"] == {"mst": "200", "effective_date": "20150101", "announced_date": "20141201",
                              "announcement_no": "2000", "revision_type": "일부개정", "status": "연혁"}
    assert out["comparison"]["is_current_version"] is False
    assert out["comparison"]["differs_from_current"] is None
    assert "20160101" in out["statement"] and "MST 200" in out["statement"]
    assert service_calls() == []


def test_difference_from_current_is_about_the_article(as_of):
    same = as_of(law_name=T, as_of="20160101", article=2)
    diff = as_of(law_name=T, as_of="20160101", article=1)
    assert same["comparison"]["differs_from_current"] is False
    assert diff["comparison"]["differs_from_current"] is True
    assert diff["comparison"]["current_article_text"].endswith("v4b")
    cur = as_of(law_name=T, as_of=TODAY, article=1)
    assert cur["comparison"]["is_current_version"] is True
    assert cur["comparison"]["differs_from_current"] is False


def test_article_missing_in_current_counts_as_different(as_of):
    out = as_of(law_name=T, as_of="20180901", article="3의2")
    assert out["comparison"]["differs_from_current"] is False  # still present in the current version
    gone = as_of(law_name=T, as_of="20100101", article="제3조의2")
    assert gone["error_code"] == "ARTICLE_NOT_FOUND"


def test_slim_response_drops_bulk(as_of, monkeypatch):
    full = as_of(law_name=T, as_of="20160101", article=1)
    assert "neighbors" in full and "current_article_text" in full["comparison"]
    monkeypatch.setenv("SLIM_RESPONSE", "1")
    slim = as_of(law_name=T, as_of="20160101", article=1)
    assert "neighbors" not in slim and "current_article_text" not in slim["comparison"]
    assert slim["version"] == full["version"] and slim["article"]["text"] == full["article"]["text"]


# ------------------------------------------------------------------ upstream failures

def test_search_failure_is_not_reported_as_not_found(as_of):
    FakeClient.fail["search"] = {"status": "error", "error_code": "TIMEOUT", "message": "x", "request_id": "r"}
    out = as_of(law_name=T, as_of="20150101")
    assert out["status"] == "error" and out["error_code"] == "TIMEOUT"
    assert "upstream 오류" in out["message"] and out.get("failed_sources")


def test_history_failure_is_upstream_error(as_of):
    FakeClient.fail["history"] = {"status": "error", "error_code": "UPSTREAM_ERROR", "message": "x", "request_id": "r"}
    out = as_of(law_name="9999", as_of="20150101")
    assert out["status"] == "error" and out["error_code"] == "UPSTREAM_ERROR"


def test_body_failure_keeps_version_and_is_not_article_not_found(as_of):
    FakeClient.fail["service"] = {"status": "error", "error_code": "TIMEOUT", "message": "x", "request_id": "r"}
    out = as_of(law_name=T, as_of="20150101", article=1)
    assert out["status"] == "error" and out["error_code"] == "TIMEOUT"
    assert out["version"]["mst"] == "200" and out["as_of"] == "20150101"
    assert "조문이 없다는 뜻이 아닙니다" in out["message"]


def test_unsubscribed_eflaw_falls_back_to_law_target(as_of, monkeypatch):
    real_get = FakeClient.get

    def get(self, endpoint, params, response_type="JSON"):
        if endpoint == "/DRF/lawService.do" and params.get("target") == "eflaw":
            FakeClient.calls.append((endpoint, dict(params)))
            return {"status": "error", "error_code": "API_NOT_SUBSCRIBED", "message": "x", "request_id": "r"}
        if endpoint == "/DRF/lawService.do":  # target=law keyed by MST only
            FakeClient.calls.append((endpoint, dict(params)))
            row = next(r for r in ROWS if r["법령일련번호"] == params["MST"])
            return {"status": "ok", "request_id": "r", "upstream_type": "JSON",
                    "raw_content": _article_body(row["법령일련번호"], row["시행일자"], "제1조")}
        return real_get(self, endpoint, params, response_type)

    monkeypatch.setattr(FakeClient, "get", get)
    out = as_of(law_name=T, as_of="20150101", article=1)
    assert out["status"] == "ok" and any("eflaw 본문 API 미신청" in c for c in out["caveats"])


# ------------------------------------------------------------------ registry

def test_tool_registered_and_docs_point_to_it(as_of):
    server = server_mod.create_server()
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    assert len(tools) == 55 and "law_as_of" in tools
    for name in ("eflaw_search", "eflaw_service", "eflaw_josub"):
        assert "law_as_of" in tools[name].description
    assert "law_as_of" in server._mcp_server.instructions


def test_truncated_history_is_reported_and_blocks_before_first_claim(as_of, monkeypatch):
    real_get = FakeClient.get

    def get(self, endpoint, params, response_type="JSON"):
        res = real_get(self, endpoint, params, response_type)
        if endpoint == "/DRF/lawSearch.do" and params.get("LID"):
            body = json.loads(res["raw_content"])
            body["LawSearch"]["totalCnt"] = "100000"  # upstream has far more rows than the page cap reads
            res = dict(res, raw_content=json.dumps(body, ensure_ascii=False))
        return res

    monkeypatch.setattr(FakeClient, "get", get)
    out = as_of(law_name="9999", as_of="19000101")
    assert out["history_complete"] is False and out["warnings"]
    assert out["reason"] == "BEFORE_EARLIEST_AVAILABLE_VERSION"
    assert any(out["warnings"][0] in c for c in out["caveats"])
