"""Issue #59 follow-ups: schema descriptions, ef_yd guards, nw, date_basis, period mode.

Reuses the mock upstream of test_law_as_of.py (no OC / network).
"""

import re

import pytest

import lexlink.server as server_mod
from test_law_as_of import FakeClient, T, TODAY, as_of  # noqa: F401  (as_of is a fixture)


def _tools():
    server = server_mod.create_server()
    return {t.name: t for t in server._tool_manager.list_tools()}


def _head(desc):
    """What LexAgent shows the model: text before Args:, whitespace squashed, 360 chars max."""
    head = re.split(r"\n\s*(?:Args|Returns|Examples?|Raises):", desc)[0]
    one = re.sub(r"\s+", " ", head).strip()
    return one if len(one) <= 360 else one[:357] + "…"


def test_description_head_and_schema_point_to_law_as_of(as_of):
    tools = _tools()
    for name in ("eflaw_search", "eflaw_service", "eflaw_josub", "law_service", "law_josub",
                 "law_amendment_summary"):
        assert "law_as_of" in _head(tools[name].description), name
    own = _head(tools["law_as_of"].description)
    assert "ef_yd" in own and "as of" in own and "MST" in own and "공포일" in own
    for name in ("eflaw_search", "eflaw_service", "eflaw_josub"):
        assert "law_as_of" in tools[name].parameters["properties"]["ef_yd"]["description"], name
    assert "law_as_of" in tools["law_service"].parameters["properties"]["ld"]["description"]
    for name in ("eflaw_service", "eflaw_josub", "law_service", "law_josub"):
        props = tools[name].parameters["properties"]
        assert "description" in props["id"] and "description" in props["mst"]
    props = tools["law_as_of"].parameters["properties"]
    assert set(props) == {"law_name", "as_of", "article", "article_branch", "as_of_end", "oc", "type"}
    assert all("description" in props[k] for k in ("law_name", "as_of", "article", "article_branch", "as_of_end"))
    assert tools["law_as_of"].parameters["required"] == ["law_name", "as_of"]
    assert "description" in tools["eflaw_search"].parameters["properties"]["nw"]
    assert "description" in tools["law_amendment_summary"].parameters["properties"]["date_basis"]


@pytest.mark.parametrize("tool", ["eflaw_service", "eflaw_josub"])
def test_ef_yd_with_id_but_no_mst_is_rejected(as_of, tool):
    server = server_mod.create_server()
    fn = server._tool_manager.get_tool(tool).fn
    out = fn(id="009999", ef_yd=20150101, jo=1)
    assert out["status"] == "error" and out["error_code"] == "VALIDATION_ERROR"
    assert "law_as_of" in " ".join(out["hints"])
    assert FakeClient.calls == []
    ok = fn(mst="200", ef_yd=20150101, jo=1)  # int ef_yd still accepted together with mst
    assert ok.get("error_code") != "VALIDATION_ERROR"
    assert str(FakeClient.calls[-1][1]["efYd"]) == "20150101"


def test_eflaw_search_nw(as_of):
    fn = server_mod.create_server()._tool_manager.get_tool("eflaw_search").fn
    fn(query=T, nw="1,2,3")
    assert FakeClient.calls[-1][1]["nw"] == "1,2,3"
    fn(query=T)
    assert "nw" not in FakeClient.calls[-1][1]
    assert fn(query=T, nw="4")["error_code"] == "VALIDATION_ERROR"
    assert fn(query=T, ef_yd="20150101")["error_code"] == "VALIDATION_ERROR"  # single date is not a range


def test_amendment_summary_date_basis(as_of):
    fn = server_mod.create_server()._tool_manager.get_tool("law_amendment_summary").fn
    ann = fn(law_name=T, date_from="20160101", date_to="20161231")
    assert ann["revisions"] == [] and ann["date_basis"] == "announced"      # default unchanged
    eff = fn(law_name=T, date_from="20160101", date_to="20161231", date_basis="effective")
    assert [r["mst"] for r in eff["revisions"]] == ["200"]
    assert eff["revisions"][0]["in_force_at_period_start"] is True
    assert eff["date_filter_field"] == "시행일자"
    wide = fn(law_name=T, date_from="20170101", date_to="20190101", date_basis="effective")
    assert [(r["mst"], r["effective_date"]) for r in wide["revisions"]] == [
        ("300", "20180901"), ("300", "20180301"), ("200", "20150101")]
    assert wide["revisions"][-1]["in_force_at_period_start"] is True
    assert fn(law_name=T, date_basis="bogus")["error_code"] == "VALIDATION_ERROR"


def test_promulgated_but_not_yet_effective(as_of):
    out = as_of(law_name=T, as_of="2014-12-15", article=1)   # MST 200: promulgated 20141201, effective 20150101
    assert out["version"]["mst"] == "100"
    assert out["promulgated_not_yet_effective_exists"] is True
    assert [v["mst"] for v in out["promulgated_not_yet_effective"]] == ["200"]
    assert out["later_amendments"]["exists"] is True and out["later_amendments"]["next_effective_date"] == "20150101"
    assert out["comparison"]["differs_from_current"] is True
    assert "MST 200" in " ".join(out["caveats"])


def test_scheduled_and_later_flags(as_of):
    cur = as_of(law_name=T, as_of=TODAY, article=1)
    assert cur["scheduled_version_exists"] is True
    assert [v["mst"] for v in cur["scheduled_versions"]] == ["500"]
    assert cur["later_amendments"] == {"exists": True, "count": 1, "effective_date_count": 1,
                                       "next_effective_date": "20271201"}
    fut = as_of(law_name=T, as_of="20271201")
    assert fut["later_amendments"]["exists"] is False


def test_period_lists_every_revision_in_force(as_of):
    out = as_of(law_name=T, as_of="20171201", as_of_end="2019-01-01", article=1)
    p = out["period"]
    assert [(r["version"]["mst"], r["version"]["effective_date"]) for r in p["revisions"]] == [
        ("200", "20150101"), ("300", "20180301"), ("300", "20180901")]
    assert [r["article"]["text"].split()[-1] for r in p["revisions"]] == ["v2", "v3a", "v3b"]
    assert p["revisions"][0]["valid_from"] == "20171201" and p["revisions"][0]["valid_until"] == "20180228"
    assert p["revisions"][-1]["valid_until"] == "20190101"
    assert p["article_changed_within_period"] is True
    same = as_of(law_name=T, as_of="20171201", as_of_end="20180228", article=2)
    assert len(same["period"]["revisions"]) == 1 and same["period"]["article_changed_within_period"] is False


def test_period_with_article_added_midway_and_before_first(as_of):
    out = as_of(law_name=T, as_of="2018-08-31", as_of_end="2018-12-31", article="3의2")
    assert out["status"] == "ok" and out["article_status"] == "ARTICLE_NOT_FOUND"
    assert [r.get("article_status") for r in out["period"]["revisions"]] == ["ARTICLE_NOT_FOUND", None]
    early = as_of(law_name=T, as_of="20090101", as_of_end="20110101", article=1)
    assert early["in_force"] is False and len(early["period"]["revisions"]) == 1
    assert early["period"]["revisions"][0]["valid_from"] == "20100101"


def test_period_end_before_start_is_validation_error(as_of):
    assert as_of(law_name=T, as_of="20180101", as_of_end="20170101")["error_code"] == "VALIDATION_ERROR"
