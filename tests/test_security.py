"""Hardening regression tests: request limits, PII in responses, malformed
input robustness, production auth enforcement, and SSE failure recovery."""

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app, enforce_auth_config
from orchestrator.middleware import BodySizeLimitMiddleware
from orchestrator.models.vapi import VapiMessage
from orchestrator.routers.vapi import (
    _sanitize_call_id,
    _to_anthropic_messages,
    _wrap_as_sse,
)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ── request body size limit ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oversized_body_rejected_with_413():
    async with _client() as client:
        resp = await client.post(
            "/vapi/server",
            content=b"x" * 1_000_001,
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_normal_body_passes_size_limit():
    async with _client() as client:
        resp = await client.post("/vapi/server", json={"message": {"type": "status-update"}})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chunked_body_over_limit_rejected():
    """No Content-Length header — the streamed-body counter must catch it."""

    async def reads_body_app(scope, receive, send):  # type: ignore[no-untyped-def]
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = BodySizeLimitMiddleware(reads_body_app, max_bytes=10)
    scope = {"type": "http", "method": "POST", "path": "/x", "headers": []}

    chunks = [b"a" * 8, b"b" * 8]
    sent: list[dict] = []

    async def receive():  # type: ignore[no-untyped-def]
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message):  # type: ignore[no-untyped-def]
        sent.append(dict(message))

    await mw(scope, receive, send)
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


# ── DNC response must not echo the phone number ──────────────────────────────


@pytest.mark.asyncio
async def test_dnc_rejection_does_not_leak_phone_number(monkeypatch):
    from orchestrator.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    blocked = "+15551234567"
    async with _client() as client:
        resp = await client.post(
            "/vapi/llm",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "call": {"id": "call-1", "customer": {"number": blocked}},
            },
        )
    assert resp.status_code == 403
    assert blocked not in resp.text
    assert "555" not in resp.text


@pytest.mark.asyncio
async def test_llm_endpoint_503_when_model_unconfigured():
    """Fail fast with a real status code instead of erroring mid-SSE."""
    async with _client() as client:
        resp = await client.post(
            "/vapi/llm",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
    assert resp.status_code == 503


# ── call_id hardening ─────────────────────────────────────────────────────────


def test_call_id_passthrough_for_normal_ids():
    assert _sanitize_call_id("6a41179c-9bcc-4bde-a794-04a6f9c88b0a") == (
        "6a41179c-9bcc-4bde-a794-04a6f9c88b0a"
    )


def test_call_id_strips_unsafe_characters():
    assert _sanitize_call_id("abc\r\n key:{injection}") == "abckey:injection"


def test_call_id_length_capped():
    assert len(_sanitize_call_id("a" * 500)) == 128


def test_call_id_falls_back_on_garbage():
    assert _sanitize_call_id(None) == "dev-call"
    assert _sanitize_call_id("🔥🔥🔥") == "dev-call"
    assert _sanitize_call_id({"nested": "dict"}, default="unknown") == "nested:dict"


# ── message normalisation for the Anthropic API ──────────────────────────────


def _msg(role: str, content: str) -> VapiMessage:
    return VapiMessage(role=role, content=content)


def test_assistant_first_history_gets_user_seed():
    """Real Vapi cold calls start with the assistant speaking — Anthropic
    requires the first message to be from the user."""
    out = _to_anthropic_messages([_msg("assistant", "Hi, this is Alex")])
    assert out[0] == {"role": "user", "content": "(call connected)"}
    assert out[1]["role"] == "assistant"


def test_consecutive_same_role_messages_merged():
    out = _to_anthropic_messages(
        [
            _msg("user", "Hello?"),
            _msg("user", "Anyone there?"),
            _msg("assistant", "Hi!"),
        ]
    )
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert "Hello?" in out[0]["content"] and "Anyone there?" in out[0]["content"]


def test_empty_and_foreign_role_messages_dropped():
    out = _to_anthropic_messages(
        [
            _msg("system", "be nice"),
            _msg("user", "   "),
            _msg("tool", "result"),
            _msg("user", "hi"),
        ]
    )
    assert out == [{"role": "user", "content": "hi"}]


def test_empty_history_yields_seed_turn():
    out = _to_anthropic_messages([])
    assert out == [{"role": "user", "content": "(call connected)"}]


def test_vapi_message_coerces_content_parts():
    m = VapiMessage(
        role="user",
        content=[{"type": "text", "text": "hel"}, {"type": "text", "text": "lo"}],
    )
    assert m.content == "hello"


def test_vapi_message_coerces_null_content():
    assert VapiMessage(role="user", content=None).content == ""


# ── SSE stream failure recovery (no dead air) ────────────────────────────────


@pytest.mark.asyncio
async def test_sse_recovers_from_midstream_generation_failure():
    async def failing_iter():
        yield "Hello"
        raise RuntimeError("upstream died")

    captured: dict[str, str] = {}

    async def on_complete(text: str) -> None:
        captured["text"] = text

    lines = [line async for line in _wrap_as_sse(failing_iter(), on_complete=on_complete)]
    joined = "".join(lines)

    assert "data: [DONE]" in joined  # stream still terminates cleanly
    assert "lost you" in joined  # recovery line was spoken
    assert captured["text"].startswith("Hello")


@pytest.mark.asyncio
async def test_sse_survives_failing_completion_hook():
    async def one_chunk():
        yield "Hi"

    async def exploding_hook(text: str) -> None:
        raise RuntimeError("audit failed")

    lines = [line async for line in _wrap_as_sse(one_chunk(), on_complete=exploding_hook)]
    assert "data: [DONE]" in "".join(lines)


# ── webhook robustness: malformed payloads must not 500 ─────────────────────


@pytest.mark.asyncio
async def test_webhook_non_dict_message_ignored():
    async with _client() as client:
        resp = await client.post("/vapi/server", json={"message": "garbage"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}


@pytest.mark.asyncio
async def test_webhook_end_of_call_with_malformed_fields():
    payload = {
        "message": {
            "type": "end-of-call-report",
            "call": "not-a-dict",
            "messages": [
                {"role": "bot", "message": "Hi there"},
                "garbage-entry",
                {"role": "user", "content": 12345},
                {"role": "user", "content": "sounds good"},
            ],
        }
    }
    async with _client() as client:
        resp = await client.post("/vapi/server", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"


@pytest.mark.asyncio
async def test_webhook_messages_wrong_type():
    payload = {"message": {"type": "end-of-call-report", "messages": "garbage"}}
    async with _client() as client:
        resp = await client.post("/vapi/server", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "no-messages"}


# ── production auth enforcement ──────────────────────────────────────────────


def test_production_with_empty_secrets_refuses_to_boot(monkeypatch):
    from orchestrator.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError, match="Refusing to start"):
        enforce_auth_config()


def test_production_with_secrets_boots(monkeypatch):
    from orchestrator.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "vapi_llm_secret", "s1")
    monkeypatch.setattr(settings, "vapi_server_secret", "s2")
    enforce_auth_config()  # must not raise


def test_production_insecure_override_boots_with_warning(monkeypatch):
    from orchestrator.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "allow_insecure_public_endpoints", True)
    enforce_auth_config()  # must not raise


def test_development_with_empty_secrets_boots():
    enforce_auth_config()  # hermetic defaults: development, no secrets
