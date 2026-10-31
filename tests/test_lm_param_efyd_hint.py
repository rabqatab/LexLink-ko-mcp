"""lm -> upstream `LM`, lm-only lookups, and eflaw_service mst-without-ef_yd guidance."""

import pytest

import lexlink.server as server_mod
from lexlink.cache import get_cache
from lexlink.params import map_params_to_upstream

FAKE_OC = "unit-test-oc"


class RecordingClient:
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    def get(self, endpoint, params, response_type="JSON"):
        RecordingClient.calls.append((endpoint, dict(params)))
        return {"status": "ok", "request_id": "fake", "upstream_type": "JSON",
                "raw_content": "{}"}


@pytest.fixture
def tool(monkeypatch):
    get_cache().invalidate()
    monkeypatch.setattr(server_mod, "LawAPIClient", RecordingClient)
    monkeypatch.setenv("OC", FAKE_OC)
    RecordingClient.calls = []
    server = server_mod.create_server()
    yield lambda name, **kw: server._tool_manager.get_tool(name).fn(**kw)
    get_cache().invalidate()


@pytest.mark.unit
def test_lm_maps_to_uppercase_upstream_key():
    out = map_params_to_upstream({"oc": FAKE_OC, "target": "law", "lm": "건축법"})
    assert out["LM"] == "건축법"
    assert "lm" not in out


@pytest.mark.unit
@pytest.mark.parametrize("name,target", [
    ("law_service", "law"), ("eflaw_service", "eflaw"), ("elaw_service", "elaw"),
])
def test_lm_alone_is_accepted_and_sent_as_LM(tool, name, target):
    tool(name, lm="건축법", type="XML")
    (_, params), = RecordingClient.calls
    assert params["target"] == target
    assert params["LM"] == "건축법"
    assert "lm" not in params


@pytest.mark.unit
def test_service_without_any_identifier_still_rejected(tool):
    out = tool("law_service")
    assert out["error_code"] == "VALIDATION_ERROR"
    assert RecordingClient.calls == []


@pytest.mark.unit
def test_eflaw_mst_without_ef_yd_gives_ef_yd_hint_not_subscription(tool):
    out = tool("eflaw_service", mst="284415", type="XML")
    assert out["error_code"] == "VALIDATION_ERROR"
    assert "ef_yd" in out["message"]
    assert "open.law.go.kr" not in str(out)
    assert RecordingClient.calls == []


@pytest.mark.unit
def test_eflaw_mst_with_ef_yd_and_id_alone_still_call_upstream(tool):
    tool("eflaw_service", mst="284415", ef_yd=20260317, type="XML")
    tool("eflaw_service", id="001706", type="XML")
    assert len(RecordingClient.calls) == 2
    assert RecordingClient.calls[0][1]["efYd"] == 20260317
