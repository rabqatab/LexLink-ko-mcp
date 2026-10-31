"""Offline tests: eflaw LID history needs nw, upstream failures are not 'law not found',
chain_law_system reports admin rules / linked ordinances honestly (issues #10, #16)."""

import json

import pytest

import lexlink.server as server_mod
from test_amendment import FakeClient, _json_rows

ERR = {"status": "error", "error_code": "UPSTREAM_ERROR", "message": "boom", "request_id": "fake"}
ORDIN_ROWS = [
    {"자치법규ID": "2019611", "id": "1", "자치법규명": "가평군 건축 조례", "자치법규종류": "조례"},
    {"자치법규ID": "2019668", "id": "2", "자치법규명": "가평군 군계획 조례", "자치법규종류": "조례"},
]


class StrictClient(FakeClient):
    """Like law.go.kr: JSON eflaw + LID returns only the 현행 rows unless nw=1,2,3."""

    fail_targets: set = set()

    def get(self, endpoint, params, response_type="JSON"):
        if params.get("target") in StrictClient.fail_targets:
            FakeClient.calls.append((endpoint, dict(params)))
            return dict(ERR)
        return super().get(endpoint, params, response_type)

    def _search(self, target, params):
        if target == "eflaw" and params.get("LID") and not params.get("nw"):
            rows = [r for r in _json_rows("eflaw_search_copyright.json")
                    if r.get("법령ID") == params["LID"] and r.get("현행연혁코드") == "현행"]
            return self._ok(json.dumps({"LawSearch": {"totalCnt": str(len(rows)), "law": rows}},
                                       ensure_ascii=False))
        if target == "lnkLsOrd":
            return self._ok(json.dumps({"OrdinSearch": {"totalCnt": "523", "page": "1", "law": ORDIN_ROWS}},
                                       ensure_ascii=False))
        if target == "lnkLs":  # laws, not ordinances
            return self._ok(json.dumps({"LawSearch": {"totalCnt": "1", "law": [
                {"법령ID": "000798", "법령명한글": "저작권법", "법령구분명": "법률"}]}}, ensure_ascii=False))
        return super()._search(target, params)


@pytest.fixture
def strict_tools(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", StrictClient)
    monkeypatch.setenv("OC", "test")
    FakeClient.calls = []
    StrictClient.fail_targets = set()
    from lexlink.cache import get_cache
    get_cache().invalidate()
    server = server_mod.create_server()
    yield lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)
    StrictClient.fail_targets = set()
    get_cache().invalidate()


def test_history_lookup_sends_nw_and_returns_all_versions(strict_tools):
    out = strict_tools("law_amendment_summary", law_name="저작권법", date_from="19000101")
    assert out["status"] == "ok", out
    lid_calls = [p for _, p in FakeClient.calls if p.get("LID")]
    assert lid_calls and all(p.get("nw") == "1,2,3" for p in lid_calls)
    assert out["total_revisions"] > 1


def test_chain_amendment_track_has_two_versions_to_compare(strict_tools):
    out = strict_tools("chain_amendment_track", law_name="저작권법", article=35, article_branch=5,
                       date_from="20200101")
    assert out["status"] == "ok", out
    assert out.get("article_diff") is not None


@pytest.mark.parametrize("name,kwargs", [
    ("chain_law_system", {"law_name": "저작권법"}),
    ("chain_amendment_track", {"law_name": "저작권법"}),
    ("law_amendment_summary", {"law_name": "저작권법"}),
])
def test_upstream_failure_is_not_law_not_found(strict_tools, name, kwargs):
    StrictClient.fail_targets = {"eflaw"}
    out = strict_tools(name, **kwargs)
    assert out["status"] == "error"
    assert out["error_code"] == "UPSTREAM_ERROR"
    assert "찾을 수 없습니다" not in out["message"]


def test_history_page_failure_is_upstream_error(strict_tools, monkeypatch):
    orig = StrictClient._search

    def flaky(self, target, params):
        if target == "eflaw" and params.get("LID"):
            return dict(ERR)
        return orig(self, target, params)
    monkeypatch.setattr(StrictClient, "_search", flaky)
    out = strict_tools("law_amendment_summary", law_name="저작권법")
    assert out["status"] == "error" and out["error_code"] == "UPSTREAM_ERROR"


def test_chain_law_system_lists_ordinances_and_delegated_admin_rules(strict_tools):
    out = strict_tools("chain_law_system", law_name="저작권법")
    assert out["status"] == "ok", out
    assert [o["name"] for o in out["linked_ordinances"]] == ["가평군 건축 조례", "가평군 군계획 조례"]
    assert out["linked_ordinances"][0]["type"] == "조례"
    assert out["linked_ordinances_total"] == 523
    names = [r["name"] for r in out["admin_rules"]]
    assert "도서관의 저작물 복제·전송이용 보상금 기준" in names
    assert "warnings" not in out
    assert any(p.get("target") == "lnkLsOrd" and p.get("knd") == "000798" for _, p in FakeClient.calls)


def test_chain_law_system_surfaces_fetch_failures(strict_tools):
    StrictClient.fail_targets = {"lnkLsOrd"}
    out = strict_tools("chain_law_system", law_name="저작권법")
    assert out["status"] == "ok" and out["linked_ordinances"] == []
    assert any("lnkLsOrd" in w for w in out["warnings"])


def test_chain_law_system_warns_when_delegation_fetch_fails(monkeypatch, strict_tools):
    orig = StrictClient._service

    def svc(self, target, params, response_type):
        if target == "lsDelegated":
            return dict(ERR)
        return orig(self, target, params, response_type)
    monkeypatch.setattr(StrictClient, "_service", svc)
    out = strict_tools("chain_law_system", law_name="저작권법")
    assert out["admin_rules"] == []
    assert any("lsDelegated" in w and "admin_rules" in w for w in out["warnings"])


# ---------------------------------------------------------------- history paging / fallback pair

class PagedClient(StrictClient):
    """LID history served 100 rows per page from a synthetic list of ``n_rows`` versions."""

    n_rows = 250
    total_override = None

    def _search(self, target, params):
        if target == "eflaw" and params.get("LID"):
            page = int(params.get("page", 1))
            lo = (page - 1) * 100
            hi = min(lo + 100, PagedClient.n_rows)
            rows = [{"법령ID": params["LID"], "법령명한글": "저작권법", "법령구분명": "법률",
                     "법령일련번호": str(1000 + i), "공포일자": f"{2026 - i // 12}{i % 12 + 1:02d}01",
                     "시행일자": f"{2026 - i // 12}{i % 12 + 1:02d}01",
                     "현행연혁코드": "현행" if i == 0 else "연혁"} for i in range(lo, hi)]
            total = PagedClient.total_override or PagedClient.n_rows
            return self._ok(json.dumps({"LawSearch": {"totalCnt": str(total), "law": rows}},
                                       ensure_ascii=False))
        return super()._search(target, params)


@pytest.fixture
def paged_tools(monkeypatch):
    monkeypatch.setattr(server_mod, "LawAPIClient", PagedClient)
    monkeypatch.setenv("OC", "test")
    FakeClient.calls = []
    PagedClient.fail_targets = set()
    PagedClient.n_rows, PagedClient.total_override = 250, None
    from lexlink.cache import get_cache
    get_cache().invalidate()
    server = server_mod.create_server()
    yield lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)
    PagedClient.n_rows, PagedClient.total_override = 250, None
    get_cache().invalidate()


def test_history_pages_past_three_pages(paged_tools):
    PagedClient.n_rows = 368
    out = paged_tools("law_amendment_summary", law_name="저작권법", date_from="19000101")
    assert out["total_versions"] == 368
    assert "warnings" not in out
    assert max(p["page"] for _, p in FakeClient.calls if p.get("LID")) == 4


def test_history_cap_hit_surfaces_warning(paged_tools):
    PagedClient.n_rows, PagedClient.total_override = 100000, 100000
    out = paged_tools("law_amendment_summary", law_name="저작권법", date_from="19000101")
    assert out["status"] == "ok"
    assert out["warnings"] and "누락" in out["warnings"][0]


def test_fallback_pair_prefers_in_force_versions(strict_tools):
    # newest two rows of 저작권법 are 시행예정 (291259, 285693); 현행 is 283335
    out = strict_tools("chain_amendment_track", law_name="저작권법", article="35의5", date_from="20240101")
    diff = out["article_diff"]
    assert diff["new_status"] != "시행예정" and diff["old_status"] != "시행예정"
    assert diff["new_mst"] == "283335"
    assert diff["basis"].startswith("fallback:") and "283335" in diff["basis"]
