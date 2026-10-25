"""Offline unit tests for the 법령정보 지식베이스 linkage tools (lawService.do).

Covers pure logic only: jo normalization, trmRltCd validation, query/mst
requirement, param mapping, and parsed_data attachment. No network.
"""

import json

import pytest

from lexlink._helpers import ToolValidationError
from lexlink.linkage import (
    TRM_RLT_CODES,
    attach_parsed_data,
    normalize_jo_code,
    require_query_or_mst,
    validate_trm_rlt_cd,
)
from lexlink.params import map_params_to_upstream


# ---------------------------------------------------------------- jo codes
@pytest.mark.unit
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("35", "003500"),
        (35, "003500"),
        ("35의5", "003505"),
        ("제35조의5", "003505"),
        ("제35조", "003500"),
        ("003505", "003505"),
        ("000300", "000300"),
        ("3", "000300"),
        (" 15 의 2 ", "001502"),
        ("1234", "123400"),
    ],
)
def test_normalize_jo_code_accepts_common_forms(raw, expected):
    assert normalize_jo_code(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize("raw", [None, "", "   ", "abc", "35조의", "12345", "0000", "제0조", "35의100"])
def test_normalize_jo_code_rejects_bad_input(raw):
    with pytest.raises(ToolValidationError) as exc:
        normalize_jo_code(raw)
    assert exc.value.hints  # hints are surfaced in the structured error


# ---------------------------------------------------------------- trmRltCd
@pytest.mark.unit
def test_validate_trm_rlt_cd_codes_and_names():
    for code, name in TRM_RLT_CODES.items():
        assert validate_trm_rlt_cd(code) == code
        assert validate_trm_rlt_cd(name) == code
    assert validate_trm_rlt_cd(140305) == "140305"
    assert validate_trm_rlt_cd(None) is None
    assert validate_trm_rlt_cd("") is None


@pytest.mark.unit
def test_validate_trm_rlt_cd_rejects_unknown():
    with pytest.raises(ToolValidationError):
        validate_trm_rlt_cd("999999")


# ---------------------------------------------------------------- query/mst
@pytest.mark.unit
def test_require_query_or_mst():
    require_query_or_mst("공정한이용", None, "t")
    require_query_or_mst(None, "1470403", "t")
    for q, m in [(None, None), ("", None), ("*", None), ("  ", "")]:
        with pytest.raises(ToolValidationError):
            require_query_or_mst(q, m, "t")


# ---------------------------------------------------------------- params
@pytest.mark.unit
def test_param_mapping_for_service_targets():
    up = map_params_to_upstream({
        "oc": "x", "target": "lstrmRlt", "type": "JSON",
        "query": "공정한이용", "mst": "1470403", "trm_rlt_cd": "140305",
    })
    assert up == {
        "OC": "x", "target": "lstrmRlt", "type": "JSON",
        "query": "공정한이용", "MST": "1470403", "trmRltCd": "140305",
    }

    up = map_params_to_upstream({
        "oc": "x", "target": "joRltLstrm", "type": "JSON",
        "jo": "003505", "query": "저작권법", "id": "001823",
    })
    assert up["JO"] == "003505"
    assert up["ID"] == "001823"
    assert "display" not in up and "page" not in up


# ---------------------------------------------------------------- parsing
@pytest.mark.unit
def test_attach_parsed_data_json_unwraps_root():
    body = {"lstrmRltService": {"검색결과개수": "1", "법령용어": {"법령용어명": "공정한이용"}}}
    resp = {"status": "ok", "raw_content": json.dumps(body, ensure_ascii=False)}
    out = attach_parsed_data(resp, "JSON")
    assert out["parsed_data"]["검색결과개수"] == "1"
    assert out["parsed_data"]["법령용어"]["법령용어명"] == "공정한이용"
    assert "raw_content" in out  # service tools keep raw_content as fallback


@pytest.mark.unit
def test_attach_parsed_data_xml():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<lstrmRltService><검색결과개수>1</검색결과개수>"
        "<법령용어><법령용어명><![CDATA[공정한이용]]></법령용어명></법령용어></lstrmRltService>"
    )
    out = attach_parsed_data({"status": "ok", "raw_content": xml}, "XML")
    assert out["parsed_data"]["검색결과개수"] == "1"


@pytest.mark.unit
def test_attach_parsed_data_leaves_errors_and_empty_bodies_alone():
    err = {"status": "error", "message": "x"}
    assert attach_parsed_data(dict(err), "JSON") == err
    empty = {"status": "ok", "raw_content": ""}
    assert "parsed_data" not in attach_parsed_data(dict(empty), "JSON")
    bad = {"status": "ok", "raw_content": "{not json"}
    assert "parsed_data" not in attach_parsed_data(dict(bad), "JSON")
