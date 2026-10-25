"""Cache key / TTL regression tests (audit 2026-10-25)."""

from lexlink.cache import ResponseCache, _make_cache_key, TTL_CONFIG


def test_cache_key_includes_response_format():
    base = {"OC": "x", "query": "주차장", "display": 2}
    k_json = _make_cache_key("lnkOrd", {**base, "type": "JSON"})
    k_xml = _make_cache_key("lnkOrd", {**base, "type": "XML"})
    assert k_json != k_xml


def test_cache_key_format_is_case_insensitive_and_defaults_to_json():
    base = {"OC": "x", "query": "주차장"}
    assert _make_cache_key("lnkOrd", {**base, "type": "json"}) == _make_cache_key("lnkOrd", {**base, "type": "JSON"})
    assert _make_cache_key("lnkOrd", base) == _make_cache_key("lnkOrd", {**base, "type": "JSON"})


def test_cache_does_not_serve_json_body_to_xml_request():
    cache = ResponseCache(max_entries=10)
    params_json = {"OC": "x", "type": "JSON", "query": "주차장"}
    params_xml = {"OC": "x", "type": "XML", "query": "주차장"}
    cache.put("lnkOrd", params_json, {"status": "ok", "raw_content": "{}"})
    assert cache.get("lnkOrd", params_json) is not None
    assert cache.get("lnkOrd", params_xml) is None


def test_ttl_for_new_target_families():
    cache = ResponseCache()
    assert cache._get_ttl("moelCgmExpc") == TTL_CONFIG["search"]
    assert cache._get_ttl("lnkOrd") == TTL_CONFIG["search"]
    assert cache._get_ttl("ttSpecialDecc") == TTL_CONFIG["search"]
