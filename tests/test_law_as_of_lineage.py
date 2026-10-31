"""Same-name 법령IDs: swap to the old law only within one lineage; flag ambiguous names."""

from test_law_as_of import as_of  # noqa: F401  (fixture)


def test_no_swap_across_different_ministries(as_of):
    out = as_of(law_name="고용규정", as_of="19550101")
    assert out["in_force"] is False and out["reason"] == "BEFORE_EARLIEST_AVAILABLE_VERSION"
    assert "same_name_predecessor" not in out and out["law"]["law_id"] == "003001"
    assert out["same_name_other_law_ids"] == ["003002"]
    assert out["same_name_other_laws"][0]["ministry"] == "공보부"
    assert any("구법으로 보지 않았습니다" in c and "003002" in c for c in out["caveats"])


def test_swap_for_same_type_and_ministry(as_of):
    out = as_of(law_name="동부령", as_of="19700101")
    assert out["in_force"] is True and out["law"]["law_id"] == "003011"
    assert out["same_name_predecessor"]["replaced_law_id"] == "003012"


def test_swap_for_statute_even_if_ministry_changed(as_of):
    out = as_of(law_name="개편법", as_of="19700101")
    assert out["in_force"] is True and out["law"]["law_id"] == "003021"
    assert out["same_name_predecessor"] == {"law_id": "003021", "replaced_law_id": "003022", "law_name": "개편법"}


def test_ambiguous_same_name_is_flagged_for_in_force_results(as_of):
    # only repealed LIDs: found through the nw retry, the other ids are already in those rows
    out = as_of(law_name="다중규정", as_of="19650101")
    assert out["in_force"] is True
    assert len(out["same_name_other_law_ids"]) == 1
    assert out["same_name_other_law_ids"][0] != out["law"]["law_id"]
    assert any("동일 명칭의 법령이" in c for c in out["caveats"])
    # two current LIDs: known from the plain name search
    twin = as_of(law_name="쌍둥이규정", as_of="20200101")
    assert len(twin["same_name_other_law_ids"]) == 1 and twin["in_force"] is True
    assert twin["same_name_other_laws"][0]["ministry"] in ("가부", "나부")


def test_unambiguous_name_has_no_flag_and_no_extra_lookup(as_of):
    from test_law_as_of import FakeClient, T
    out = as_of(law_name=T, as_of="20200101")
    assert "same_name_other_law_ids" not in out
    assert not any(p.get("efYd") for _, p in FakeClient.calls)   # predecessor search only when D precedes the first version
