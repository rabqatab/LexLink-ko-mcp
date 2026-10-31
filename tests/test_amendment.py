"""Offline tests for the Phase 8/9 tools with a fake law.go.kr client.

The fake serves fixtures captured from the real API (2026-10-25) so the tool
logic — law-id resolution, 현행 selection, revision listing, article extraction,
diffing, precedent fallback — runs end to end without network access.
"""

import json
import os
from pathlib import Path

import pytest

import lexlink.server as server_mod

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _json_rows(name: str) -> list:
    return json.loads(load(name))["LawSearch"]["law"]


PREC_ROWS = [
    {"판례일련번호": "609463", "사건명": "경정거부처분취소", "사건번호": "2021두59908",
     "선고일자": "2025.09.18", "법원명": "대법원"},
    {"판례일련번호": "123456", "사건명": "손해배상(지)", "사건번호": "2023다1234",
     "선고일자": "2024.01.11", "법원명": "대법원"},
]

PREC_SERVICE = {
    "PrecService": {
        "판례정보일련번호": "609463",
        "사건명": "경정거부처분취소",
        "판시사항": "[1] 저작물의 공정한 이용에 해당하는지 여부<br/>[2] 손해배상 범위를 어떻게 정할 것인지 여부",
        "판결요지": "원심판결을 파기하고<br/>사건을 환송한다.",
        "판례내용": "【주    문】<br/>원심판결을 파기하고, 사건을 서울고등법원에 환송한다.<br/>【이    유】<br/>...",
    }
}


NO_ARTICLE_MSTS = {"29306", "1", "2"}  # 1957 제정 version and bogus ids


class FakeClient:
    """Routes law.go.kr requests to fixtures; records every call."""

    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        FakeClient.calls.append((endpoint, dict(params)))
        target = params.get("target")
        if endpoint == "/DRF/lawSearch.do":
            return self._search(target, params)
        return self._service(target, params, response_type)

    @staticmethod
    def _ok(body: str) -> dict:
        return {"status": "ok", "request_id": "fake", "upstream_type": "JSON", "raw_content": body}

    def _search(self, target, params):
        if target == "eflaw":
            rows = _json_rows("eflaw_search_copyright.json")
            if params.get("LID"):
                rows = [r for r in rows if r.get("법령ID") == params["LID"]]
            elif params.get("query"):
                q = params["query"].replace(" ", "")
                rows = [r for r in rows if q in r.get("법령명한글", "").replace(" ", "")]
            return self._ok(json.dumps({"LawSearch": {"target": "eflaw", "totalCnt": str(len(rows)),
                                                       "page": params.get("page", 1), "law": rows}},
                                       ensure_ascii=False))
        if target in ("prec", "decc", "detc", "ttSpecialDecc"):
            key = {"prec": "prec", "decc": "decc", "detc": "detc", "ttSpecialDecc": "decc"}[target]
            if str(params.get("search", "1")) == "2" and target == "prec":
                body = {"PrecSearch": {"totalCnt": "84", "page": "1", key: PREC_ROWS}}
            else:
                body = {"PrecSearch": {"totalCnt": "0", "page": "1"}}
            return self._ok(json.dumps(body, ensure_ascii=False))
        # knowledge base / linkage lookups used by simplify_article & chain_law_system
        return self._ok(json.dumps({"Empty": {"totalCnt": "0"}}))

    def _service(self, target, params, response_type):
        if target == "law":
            mst, jo = params.get("MST"), params.get("JO")
            ext = "xml" if response_type == "XML" else "json"
            path = FIXTURES / f"law_{mst}_jo{jo}.{ext}"
            if path.exists():
                return self._ok(path.read_text(encoding="utf-8"))
            # versions that pre-date the article (or unknown MSTs) have no 조문
            if mst in NO_ARTICLE_MSTS or jo != "003505":
                return self._ok(load("law_283335_nojo.json"))
            # any other MST of 저작권법: same 제35조의5 text as the current version
            return self._ok(load(f"law_283335_jo003505.{ext}"))
        if target == "lsJoHstInf":
            return self._ok(load("lsJoHstInf_000798_003505.json"))
        if target == "lsDelegated":
            return self._ok(load("lsDelegated_000798_trimmed.json"))
        if target == "prec":
            return self._ok(json.dumps(PREC_SERVICE, ensure_ascii=False))
        return self._ok("{}")


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", FakeClient)
    monkeypatch.setenv("OC", "test")
    FakeClient.calls = []
    from lexlink.cache import get_cache
    get_cache().clear() if hasattr(get_cache(), "clear") else None
    server = server_mod.create_server()

    def call(name, **kwargs):
        return server._tool_manager.get_tool(name).fn(**kwargs)
    return call


# ---------------------------------------------------------------- law_amendment_summary

def test_amendment_summary_lists_only_the_statute(tools):
    out = tools("law_amendment_summary", law_name="저작권법", date_from="20240101")
    assert out["status"] == "ok", out
    assert out["law_id"] == "000798" and out["law_name"] == "저작권법" and out["law_type"] == "법률"
    assert out["period"].endswith("1231") and len(out["period"]) == 17
    msts = [r["mst"] for r in out["revisions"]]
    assert msts == ["291259", "285693", "283335", "270165", "260839"]
    assert [r["status"] for r in out["revisions"]] == ["시행예정", "시행예정", "현행", "연혁", "연혁"]
    assert {r["law_type"] for r in out["revisions"]} == {"법률"}
    assert out["revisions"][2] == {
        "date": "20260210", "effective_date": "20260811", "type": "일부개정",
        "announcement_no": "21336", "mst": "283335", "status": "현행", "law_type": "법률",
        "effective_dates": ["20260511", "20260811"],
    }
    assert out["current_mst"] == "283335"
    assert out["total_revisions"] == 5 and out["total_versions"] == 42
    # name search + LID search, nothing else
    searches = [p for ep, p in FakeClient.calls if ep == "/DRF/lawSearch.do"]
    assert len(searches) == 2 and searches[1]["LID"] == "000798" and "query" not in searches[1]


def test_amendment_summary_respects_date_range_and_decree(tools):
    out = tools("law_amendment_summary", law_name="저작권법", date_from="20250101", date_to="20251231")
    assert [r["mst"] for r in out["revisions"]] == ["270165"]
    out = tools("law_amendment_summary", law_name="저작권법 시행령", date_from="20200101")
    assert out["law_name"] == "저작권법 시행령" and out["law_type"] == "대통령령"
    assert out["law_id"] != "000798"


def test_amendment_summary_bad_dates(tools):
    out = tools("law_amendment_summary", law_name="저작권법", date_from="20250101", date_to="20240101")
    assert out["status"] == "error"


# ---------------------------------------------------------------- simplify_article

def test_simplify_article_returns_full_text_from_current_version(tools):
    out = tools("simplify_article", law_name="저작권법", article=35, article_branch=5)
    assert out["status"] == "ok", out
    assert out["mst"] == "283335" and out["version"]["status"] == "현행"
    lines = out["original_text"].split("\n")
    assert lines[0] == "제35조의5(저작물의 공정한 이용)"
    assert lines[1].startswith("① 제23조부터") and lines[2].startswith("② 저작물 이용 행위가")
    assert lines[3:] == [
        "1. 이용의 목적 및 성격",
        "2. 저작물의 종류 및 용도",
        "3. 이용된 부분이 저작물 전체에서 차지하는 비중과 그 중요성",
        "4. 저작물의 이용이 그 저작물의 현재 시장 또는 가치나 잠재적인 시장 또는 가치에 미치는 영향",
    ]
    assert out["article"] == "제35조의5" and out["article_title"] == "저작물의 공정한 이용"
    assert out["terms_found"] > 0
    # article fetched with target=law, 6-digit JO, from the 현행 MST
    svc = [p for ep, p in FakeClient.calls if ep == "/DRF/lawService.do" and p.get("target") == "law"]
    assert svc and svc[0]["MST"] == "283335" and svc[0]["JO"] == "003505"


def test_simplify_article_accepts_string_reference(tools):
    out = tools("simplify_article", law_name="저작권법", article="35의5")
    assert out["status"] == "ok" and out["article"] == "제35조의5"


def test_simplify_article_missing_article_is_a_clear_error(tools):
    out = tools("simplify_article", law_name="저작권법", article=999)
    assert out["status"] == "error"
    assert "제999조" in out["message"] and out.get("hints")


# ---------------------------------------------------------------- article_amendment_diff

def test_article_diff_real_text_both_sides(tools):
    out = tools("article_amendment_diff", mst_old="270165", mst_new="283335", article=35, article_branch=5)
    assert out["status"] == "ok", out
    assert out["article"] == "제35조의5"
    assert out["old_version"]["text"].startswith("제35조의5(저작물의 공정한 이용)\n① 제23조부터")
    assert out["new_version"]["text"].count("\n") == 6
    assert out["old_version"]["date"] == "20250325" and out["new_version"]["date"] == "20260210"
    assert out["has_changes"] is False and out["changes"] == []
    assert "warning" not in out


def test_article_diff_accepts_ints_and_strings(tools):
    out = tools("article_amendment_diff", mst_old=270165, mst_new=283335, article="제35조의5")
    assert out["status"] == "ok" and out["article"] == "제35조의5"


def test_article_diff_added_article(tools):
    # MST 29306 (제정 1957) has no fixture → fake returns a payload without 조문
    out = tools("article_amendment_diff", mst_old="29306", mst_new="283335", article=35, article_branch=5)
    assert out["status"] == "ok"
    assert out["old_version"]["text"] == "" and "note" in out["old_version"]
    assert out["summary"].startswith("Article added")
    assert len(out["changes"]) == 7 and all(c["type"] == "added" for c in out["changes"])


def test_article_diff_missing_both_sides(tools):
    out = tools("article_amendment_diff", mst_old="1", mst_new="2", article=35, article_branch=5)
    assert out["status"] == "error" and out.get("hints")


# ---------------------------------------------------------------- chain_amendment_track

def test_chain_amendment_track_compares_adjacent_versions_of_same_law(tools):
    out = tools("chain_amendment_track", law_name="저작권법", article=35, article_branch=5, date_from="20200101")
    assert out["status"] == "ok", out
    assert out["law_id"] == "000798" and out["current_mst"] == "283335"
    assert all(r["law_type"] == "법률" for r in out["revisions"])
    assert out["article"] == "제35조의5"
    assert [h["mst"] for h in out["article_history"]] == ["253595", "211523"]
    diff = out["article_diff"]
    # latest article change in period is MST 253595 (2023-08-08); the version
    # right before it in the same law is 251105 (2023-05-16)
    assert diff["new_mst"] == "253595" and diff["old_mst"] == "251105"
    assert diff["basis"].startswith("lsJoHstInf")
    assert diff["old_date"] == "20230516" and diff["new_date"] == "20230808"
    msts = {r["mst"] for r in out["revisions"]}
    assert {"253595", "251105"} <= msts


def test_chain_amendment_track_summary_only(tools):
    out = tools("chain_amendment_track", law_name="저작권법")
    assert out["status"] == "ok" and "article_diff" not in out
    assert out["revisions"][0]["mst"] == "291259"
    assert out["period"].startswith("20200101~") and out["period"].endswith("1231")


def test_chain_amendment_track_falls_back_to_latest_two(tools):
    # Window excludes both lsJoHstInf change dates (2020, 2023) → latest two revisions
    out = tools("chain_amendment_track", law_name="저작권법", article="35의5", date_from="20240101")
    diff = out["article_diff"]
    assert diff["new_mst"] == "291259" and diff["old_mst"] == "285693"
    assert "latest two revisions" in diff["basis"]


# ---------------------------------------------------------------- precedent fallback

def test_check_precedent_odds_falls_back_to_body_search(tools):
    out = tools("check_precedent_odds", query="저작권 공정이용", display=20, top_n=5)
    assert out["status"] == "ok", out
    assert out["total_found"] == 84 and out["analyzed"] == 2
    assert out["search_mode"] == "본문(search=2)"
    assert [a["mode"] for a in out["search_attempts"]] == ["사건명(search=1)", "본문(search=2)"]
    case = out["representative_cases"][0]
    assert "<br" not in case["holding"] and "<br" not in case["summary"]
    assert "\n" in case["holding"]
    assert all("<br" not in f for f in out["key_factors"]) and out["key_factors"]
    assert case["outcome"] == "파기환송" or case["outcome"] == "파기"


def test_chain_dispute_prep_reports_search_modes(tools):
    out = tools("chain_dispute_prep", query="저작권 침해", display=5)
    assert out["status"] == "ok", out
    assert len(out["precedents"]) == 2
    assert out["search_modes"]["precedents"]["mode"] == "본문(search=2)"
    assert out["search_modes"]["constitutional_decisions"]["total_found"] == 0
    assert out["total_results"] == 2


# ---------------------------------------------------------------- chain_law_system

def test_chain_law_system_uses_current_version_and_compact_tree(tools):
    out = tools("chain_law_system", law_name="저작권법")
    assert out["status"] == "ok", out
    assert out["mst"] == "283335" and out["version_status"] == "현행"
    assert out["law_type"] == "법률"
    assert "delegation_tree_raw" not in out
    tree = out["delegation_tree"]
    assert tree["entry_count"] > 0 and tree["entries"][0]["article"] == "제2조"
    json.dumps(out, ensure_ascii=False)
