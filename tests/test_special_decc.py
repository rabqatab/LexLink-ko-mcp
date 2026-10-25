"""Offline unit tests for special administrative appeal (special_decc) helpers.

Audit 2026-10-25: response root is "Decc", list key "decc", but ranking was
called with item_category="ttSpecialDecc" so ranked_data was never built and
the 100-row over-fetch leaked past `display`.
"""

import json

import pytest

from lexlink.agency_codes import (
    TRIBUNAL_CODES,
    SPECIAL_DECC_LIST_KEY,
    SPECIAL_DECC_TITLE_FIELD,
    special_decc_target,
    enforce_display,
)
from lexlink._helpers import detect_items_key, run_search
from lexlink.parser import extract_items_list


@pytest.mark.unit
def test_special_decc_target():
    assert special_decc_target("tt") == "ttSpecialDecc"
    assert special_decc_target(TRIBUNAL_CODES["해양안전심판원"]) == "kmstSpecialDecc"
    assert len(TRIBUNAL_CODES) == 4


def _decc_payload(n, total=7305):
    items = [
        {
            "id": str(i + 1),
            SPECIAL_DECC_TITLE_FIELD: f"양도소득세 부과처분 취소 {i + 1}",
            "특별행정심판재결례일련번호": str(100000 + i),
            "재결청": "조세심판원", "의결일자": "2024.01.01",
        }
        for i in range(n)
    ]
    return {
        "Decc": {
            "키워드": "양도소득세", "page": 1, "target": "ttSpecialDecc",
            "totalCnt": total, "section": "evtNm",
            SPECIAL_DECC_LIST_KEY: items,
        }
    }


@pytest.mark.unit
def test_decc_list_key_lookup():
    root = _decc_payload(100)["Decc"]
    assert extract_items_list(root, "ttSpecialDecc") == []   # the bug
    assert len(extract_items_list(root, "decc")) == 100       # the fix
    assert detect_items_key(root) == "decc"                   # the fallback


class _FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, path, params, response_type):
        return {"status": "ok", "raw_content": json.dumps(self.payload, ensure_ascii=False)}


def _search(display, item_category):
    target = special_decc_target("tt")
    return run_search(
        get_client=lambda: _FakeClient(_decc_payload(100)), target=target,
        query="양도소득세",
        snake_params={"oc": "x", "target": target, "type": "JSON",
                      "query": "양도소득세", "display": display, "page": 1},
        response_type="JSON", display=display,
        ranking_field=SPECIAL_DECC_TITLE_FIELD, list_type="items",
        item_category=item_category, over_fetch_key="display",
    )


@pytest.mark.unit
def test_run_search_respects_display_with_correct_key(monkeypatch):
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    resp = _search(3, SPECIAL_DECC_LIST_KEY)
    assert len(resp["ranked_data"]["decc"]) == 3
    assert resp["ranked_data"]["display"] == "3"


@pytest.mark.unit
def test_run_search_fallback_detects_list_key_when_category_is_wrong(monkeypatch):
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    # Even with the old wrong category, detect_items_key rescues ranking.
    resp = _search(3, "ttSpecialDecc")
    assert "ranked_data" in resp
    assert len(resp["ranked_data"]["decc"]) == 3


@pytest.mark.unit
def test_enforce_display_truncates_raw_when_ranking_did_not_run():
    raw = json.dumps(_decc_payload(100), ensure_ascii=False)
    resp = {"status": "ok", "raw_content": raw}
    out = enforce_display(resp, 3, SPECIAL_DECC_LIST_KEY)
    assert len(out["ranked_data"]["decc"]) == 3
    assert out["ranked_data"]["display"] == "3"
    assert len(json.loads(out["raw_content"])["Decc"]["decc"]) == 3
    assert len(out["raw_content"]) < 20_000


@pytest.mark.unit
def test_enforce_display_syncs_raw_with_ranked():
    payload = _decc_payload(100)
    ranked = json.loads(json.dumps(payload["Decc"]))
    ranked["decc"] = ranked["decc"][:3]
    resp = {"status": "ok", "raw_content": json.dumps(payload), "ranked_data": ranked}
    out = enforce_display(resp, 3, SPECIAL_DECC_LIST_KEY)
    data = json.loads(out["raw_content"])
    assert list(data) == ["Decc"]
    assert len(data["Decc"]["decc"]) == 3


@pytest.mark.unit
def test_enforce_display_leaves_errors_and_xml_alone():
    err = {"status": "error", "message": "x"}
    assert enforce_display(err, 3, "decc") is err
    xml = {"status": "ok", "raw_content": "<Decc><decc/></Decc>"}
    assert enforce_display(dict(xml), 3, "decc") == xml
    empty = {"status": "ok", "raw_content": ""}
    assert enforce_display(dict(empty), 3, "decc") == empty
