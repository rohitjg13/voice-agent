"""Vapi REST wrapper — payload shapes and error mapping (httpx mocked)."""

from uuid import uuid4

import pytest

from orchestrator.config import settings
from orchestrator.services import vapi_client
from packs.pack_loader import load_pack


@pytest.fixture
def vapi_settings(monkeypatch):
    monkeypatch.setattr(settings, "vapi_api_key", "vapi-test-key")
    monkeypatch.setattr(settings, "public_base_url", "https://app.example.com")
    monkeypatch.setattr(settings, "vapi_server_secret", "hook-secret")


async def test_create_assistant_payload(vapi_settings, httpx_mock):
    httpx_mock.add_response(
        url="https://api.vapi.ai/assistant", json={"id": "as_123"}
    )
    pack = load_pack("dental_saas")
    assistant_id = await vapi_client.create_assistant(
        pack, "My Agent", uuid4(), uuid4()
    )
    assert assistant_id == "as_123"

    req = httpx_mock.get_request()
    assert req.headers["authorization"] == "Bearer vapi-test-key"
    import json

    body = json.loads(req.content)
    assert body["model"]["provider"] == "custom-llm"
    assert body["model"]["url"] == "https://app.example.com/vapi/llm"
    assert body["server"]["url"] == "https://app.example.com/vapi/server"
    assert body["server"]["secret"] == "hook-secret"
    assert set(body["metadata"]) == {"org_id", "agent_id"}
    assert body["firstMessage"] == pack.stages.opener


async def test_create_assistant_requires_base_url(vapi_settings, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "")
    with pytest.raises(vapi_client.VapiError) as exc:
        await vapi_client.create_assistant(load_pack("dental_saas"), "A", uuid4(), uuid4())
    assert exc.value.status == 503


async def test_api_error_raises(vapi_settings, httpx_mock):
    httpx_mock.add_response(
        url="https://api.vapi.ai/assistant", status_code=400, text="bad payload"
    )
    with pytest.raises(vapi_client.VapiError) as exc:
        await vapi_client.create_assistant(load_pack("dental_saas"), "A", uuid4(), uuid4())
    assert exc.value.status == 400


async def test_no_api_key_fails_closed():
    with pytest.raises(vapi_client.VapiError) as exc:
        await vapi_client.create_call("as_1", "pn_1", "+15550001111")
    assert exc.value.status == 503


async def test_create_call_payload(vapi_settings, httpx_mock):
    httpx_mock.add_response(url="https://api.vapi.ai/call", json={"id": "call_9"})
    call = await vapi_client.create_call("as_1", "pn_1", "+15550001111")
    assert call["id"] == "call_9"

    import json

    body = json.loads(httpx_mock.get_request().content)
    assert body == {
        "assistantId": "as_1",
        "phoneNumberId": "pn_1",
        "customer": {"number": "+15550001111"},
    }
