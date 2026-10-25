"""Tests for the lexlink://law/{name} resource template and version reporting (offline)."""

import json
import re
from pathlib import Path
from urllib.parse import quote

import pytest

import lexlink
from lexlink import server as server_module
from lexlink.server import create_server

pytestmark = pytest.mark.unit


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _read(server, uri: str) -> dict:
    contents = list(await server.read_resource(uri))
    assert contents, f"no content for {uri}"
    return json.loads(contents[0].content)


def _stub_run_search(laws: list[dict]):
    """Replace server_module.run_search with an offline stub returning `laws`."""
    calls = []

    def fake_run_search(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ok",
            "request_id": "stub",
            "upstream_type": "JSON",
            "raw_content": "{}",
            "ranked_data": {"totalCnt": str(len(laws)), "law": laws},
        }

    return fake_run_search, calls


@pytest.fixture
def server(monkeypatch):
    # Default: no upstream — any live lookup returns nothing
    fake, _ = _stub_run_search([])
    monkeypatch.setattr(server_module, "run_search", fake)
    monkeypatch.setenv("OC", "test")
    return create_server()


@pytest.mark.anyio
async def test_percent_encoded_name_is_decoded(server):
    out = await _read(server, "lexlink://law/" + quote("민법"))
    assert out["id"] == "001706"
    assert out["full_name"] == "민법"
    assert out["query"] == "민법"


@pytest.mark.anyio
async def test_plain_korean_name_resolves_from_cache(server):
    out = await _read(server, "lexlink://law/건축법")
    assert out["id"] == "001823"


@pytest.mark.anyio
async def test_cache_abbreviation_resolves(server):
    out = await _read(server, "lexlink://law/헌법")
    assert out["full_name"] == "대한민국헌법"
    assert out["id"] == "001444"


@pytest.mark.anyio
async def test_seed_alias_via_resolver(server):
    """자통법 is only in resolver.SEED_ALIASES, not in the frequently-used cache keys."""
    for uri in ("lexlink://law/자통법", "lexlink://law/" + quote("자통법")):
        out = await _read(server, uri)
        assert out["full_name"] == "자본시장과 금융투자업에 관한 법률"
        assert out["id"] == "010513"
        assert out["resolved_from"] == "자본시장과 금융투자업에 관한 법률"


@pytest.mark.anyio
async def test_live_lookup_exact_match_is_cached(monkeypatch):
    laws = [
        {"법령명한글": "저작권법 시행령", "법령ID": "012345", "법령약칭명": None, "법령구분명": "대통령령"},
        {"법령명한글": "저작권법", "법령ID": "000798", "법령약칭명": None, "법령구분명": "법률"},
    ]
    fake, calls = _stub_run_search(laws)
    monkeypatch.setattr(server_module, "run_search", fake)
    monkeypatch.setenv("OC", "test")
    srv = create_server()

    out = await _read(srv, "lexlink://law/" + quote("저작권법"))
    assert out["id"] == "000798"
    assert out["full_name"] == "저작권법"
    assert len(calls) == 1 and calls[0]["query"] == "저작권법"

    # Second read is served from cache: no further upstream call
    out2 = await _read(srv, "lexlink://law/저작권법")
    assert out2["id"] == "000798"
    assert len(calls) == 1


@pytest.mark.anyio
async def test_not_found_message_shows_decoded_name(server):
    encoded = quote("존재하지않는법")
    out = await _read(server, "lexlink://law/" + encoded)
    assert out["error"] == "not_found"
    assert out["query"] == "존재하지않는법"
    assert "존재하지않는법" in out["message"]
    assert "%" not in out["message"]
    assert out["decoded_from"] == encoded


@pytest.mark.anyio
async def test_not_found_when_upstream_errors(monkeypatch):
    def failing(**kwargs):
        return {"status": "error", "error_code": "TIMEOUT", "message": "timed out"}

    monkeypatch.setattr(server_module, "run_search", failing)
    monkeypatch.setenv("OC", "test")
    out = await _read(create_server(), "lexlink://law/아무법")
    assert out["error"] == "not_found"
    assert out["lookup_error"] == "timed out"


# --- version reporting -------------------------------------------------------

def _pyproject_version() -> str:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def test_version_matches_pyproject():
    assert lexlink.__version__ == _pyproject_version()


def test_server_reports_lexlink_version(server):
    assert server._mcp_server.version == lexlink.__version__
    opts = server._mcp_server.create_initialization_options()
    assert opts.server_version == lexlink.__version__
    assert opts.server_version != "1.26.0"
