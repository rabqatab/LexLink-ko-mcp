"""Offline unit tests for ordinLsCon_search mode selection (lnkOrd / lnkLsOrd / lnkOrg).

Pure logic only — no network. End-to-end checks against law.go.kr are run
manually (see the verification notes in the commit message).
"""

import pytest

from lexlink._helpers import ToolValidationError
from lexlink.linkage import ORDIN_LINK_MODES, select_ordin_link_mode
from lexlink.params import map_params_to_upstream


@pytest.mark.unit
def test_query_mode_selects_lnkOrd_and_ranks_by_query():
    target, params, ranking_query = select_ordin_link_mode("주차장", None, None)
    assert target == "lnkOrd"
    assert params == {"query": "주차장"}
    assert ranking_query == "주차장"


@pytest.mark.unit
def test_law_id_mode_selects_lnkLsOrd_with_knd():
    target, params, ranking_query = select_ordin_link_mode(None, "001823", None)
    assert target == "lnkLsOrd"
    assert params == {"knd": "001823"}
    assert ranking_query == "*"  # no keyword → ranking disabled, display passthrough


@pytest.mark.unit
def test_org_mode_selects_lnkOrg():
    target, params, ranking_query = select_ordin_link_mode(None, None, "3270000")
    assert target == "lnkOrg"
    assert params == {"org": "3270000"}
    assert ranking_query == "*"


@pytest.mark.unit
def test_blank_values_are_treated_as_absent():
    target, params, _ = select_ordin_link_mode("  ", "001823", "")
    assert target == "lnkLsOrd" and params == {"knd": "001823"}


@pytest.mark.unit
def test_no_mode_is_a_validation_error_with_hints():
    with pytest.raises(ToolValidationError) as exc:
        select_ordin_link_mode(None, None, None)
    assert "exactly one" in str(exc.value)
    assert any("lnkOrd" in h for h in exc.value.hints)


@pytest.mark.unit
@pytest.mark.parametrize(
    "query, law_id, org",
    [("주차장", "001823", None), ("주차장", None, "3270000"), (None, "001823", "3270000"), ("a", "b", "c")],
)
def test_multiple_modes_is_a_validation_error(query, law_id, org):
    with pytest.raises(ToolValidationError) as exc:
        select_ordin_link_mode(query, law_id, org)
    assert "only one mode" in str(exc.value)


@pytest.mark.unit
def test_mode_table_matches_upstream_targets():
    assert ORDIN_LINK_MODES == {"query": "lnkOrd", "law_id": "lnkLsOrd", "org": "lnkOrg"}


@pytest.mark.unit
def test_upstream_params_pass_through_for_each_mode():
    for q, lid, org, expect in [
        ("주차장", None, None, {"query": "주차장"}),
        (None, "001823", None, {"knd": "001823"}),
        (None, None, "3270000", {"org": "3270000"}),
    ]:
        target, params, _ = select_ordin_link_mode(q, lid, org)
        up = map_params_to_upstream({"oc": "x", "target": target, "type": "JSON", "display": 2, "page": 1, **params})
        assert up["target"] == target
        assert up["display"] == 2
        for k, v in expect.items():
            assert up[k] == v
