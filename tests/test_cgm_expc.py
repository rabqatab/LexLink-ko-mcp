"""Offline unit tests for ministry interpretation (cgm_expc) helpers.

Covers the audit findings of 2026-10-25:
- target name must be "{code}CgmExpc" (e.g. moelCgmExpc), not "cgmExpc{Code}"
- 기획재정부 was renamed 재정경제부 (code Moef unchanged); old name stays an alias
- 재정경제부/국세청 have no full-text API
- the auto-ranking path must find the "cgmExpc" list under root "CgmExpc"
"""

import json

import pytest

from lexlink.agency_codes import (
    MINISTRY_CODES,
    MINISTRY_ALIASES,
    MINISTRIES_LIST_ONLY,
    CGM_EXPC_LIST_KEY,
    CGM_EXPC_TITLE_FIELD,
    cgm_expc_target,
    resolve_ministry,
    enforce_display,
)
from lexlink._helpers import detect_items_key, run_search
from lexlink.parser import extract_items_list


# --- target name ---------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("code,expected", [
    ("Moel", "moelCgmExpc"),
    ("Kipo", "kipoCgmExpc"),
    ("Moleg", "molegCgmExpc"),
    ("Moef", "moefCgmExpc"),
    ("Naacc", "naaccCgmExpc"),
])
def test_cgm_expc_target_is_code_prefix(code, expected):
    assert cgm_expc_target(code) == expected


@pytest.mark.unit
def test_cgm_expc_target_never_uses_old_inverted_pattern():
    for code in MINISTRY_CODES.values():
        t = cgm_expc_target(code)
        assert t.endswith("CgmExpc")
        assert not t.startswith("cgmExpc")
        assert t[0].islower()


# --- ministry names -------------------------------------------------------

@pytest.mark.unit
def test_39_ministries_and_renamed_moef():
    assert len(MINISTRY_CODES) == 39
    assert MINISTRY_CODES["재정경제부"] == "Moef"
    assert "기획재정부" not in MINISTRY_CODES
    assert MINISTRY_ALIASES["기획재정부"] == "재정경제부"


@pytest.mark.unit
def test_resolve_ministry_accepts_canonical_and_alias():
    assert resolve_ministry("고용노동부") == "고용노동부"
    assert resolve_ministry("재정경제부") == "재정경제부"
    assert resolve_ministry("기획재정부") == "재정경제부"
    assert resolve_ministry(" 지식재산처 ") == "지식재산처"
    assert resolve_ministry("없는부처") is None
    assert resolve_ministry("") is None


@pytest.mark.unit
def test_list_only_ministries():
    assert MINISTRIES_LIST_ONLY == {"재정경제부", "국세청"}
    for name in MINISTRIES_LIST_ONLY:
        assert name in MINISTRY_CODES  # still searchable


# --- list extraction -----------------------------------------------------

def _cgm_expc_payload(n, total=None):
    """Mimic lawSearch.do?target=moelCgmExpc&type=JSON."""
    items = [
        {
            "id": str(i + 1),
            CGM_EXPC_TITLE_FIELD: f"퇴직금 산정 질의 {i + 1}" if i else "퇴직금",
            "법령해석일련번호": str(10000 + i),
            "해석기관명": "고용노동부",
            "해석일자": "2020.01.01",
        }
        for i in range(n)
    ]
    return {
        "CgmExpc": {
            "resultMsg": "success", "resultCode": "00", "target": "moelCgmExpc",
            "키워드": "퇴직금", "page": 1, "totalCnt": total or n,
            "numOfRows": n, "section": "itmNm",
            CGM_EXPC_LIST_KEY: items if n != 1 else items[0],
        }
    }


@pytest.mark.unit
def test_extract_items_list_finds_cgm_expc_under_root():
    root = _cgm_expc_payload(5)["CgmExpc"]
    assert len(extract_items_list(root, "cgmExpc")) == 5
    # the old call used the target name and found nothing
    assert extract_items_list(root, "moelCgmExpc") == []
    assert detect_items_key(root) == "cgmExpc"


@pytest.mark.unit
def test_extract_items_list_single_item_dict():
    root = _cgm_expc_payload(1)["CgmExpc"]
    assert len(extract_items_list(root, "cgmExpc")) == 1


class _FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, path, params, response_type):
        self.calls.append((path, dict(params)))
        return {"status": "ok", "raw_content": json.dumps(self.payload, ensure_ascii=False)}


@pytest.mark.unit
def test_run_search_ranks_and_truncates_cgm_expc(monkeypatch):
    monkeypatch.delenv("SLIM_RESPONSE", raising=False)
    client = _FakeClient(_cgm_expc_payload(100, total=806))
    target = cgm_expc_target("Moel")
    resp = run_search(
        get_client=lambda: client, target=target, query="퇴직금",
        snake_params={"oc": "x", "target": target, "type": "JSON",
                      "query": "퇴직금", "display": 2, "page": 1},
        response_type="JSON", display=2,
        ranking_field=CGM_EXPC_TITLE_FIELD, list_type="items",
        item_category=CGM_EXPC_LIST_KEY, over_fetch_key="display",
    )
    assert client.calls[0][1]["target"] == "moelCgmExpc"
    assert client.calls[0][1]["display"] == "100"  # over-fetch for ranking
    ranked = resp["ranked_data"]
    assert len(ranked["cgmExpc"]) == 2
    assert ranked["cgmExpc"][0]["안건명"] == "퇴직금"  # exact match first
    assert ranked["display"] == "2"

    resp = enforce_display(resp, 2, CGM_EXPC_LIST_KEY)
    assert len(json.loads(resp["raw_content"])["CgmExpc"]["cgmExpc"]) == 2
