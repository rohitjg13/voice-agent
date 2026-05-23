import pytest
from fastapi import HTTPException

from orchestrator.services.auth import verify_llm_auth, verify_server_auth

# ── /vapi/llm bearer auth ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_auth_disabled_passes_without_header(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "")
    await verify_llm_auth(authorization=None)  # no exception


@pytest.mark.asyncio
async def test_llm_auth_disabled_passes_with_garbage_header(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "")
    await verify_llm_auth(authorization="anything")


@pytest.mark.asyncio
async def test_llm_auth_valid_token_passes(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    await verify_llm_auth(authorization="Bearer supersecret")


@pytest.mark.asyncio
async def test_llm_auth_missing_header_rejects(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    with pytest.raises(HTTPException) as exc:
        await verify_llm_auth(authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_llm_auth_wrong_token_rejects(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    with pytest.raises(HTTPException) as exc:
        await verify_llm_auth(authorization="Bearer wrong")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_llm_auth_missing_bearer_prefix_rejects(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    with pytest.raises(HTTPException) as exc:
        await verify_llm_auth(authorization="supersecret")  # no "Bearer "
    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [
    "Bearer supersecret",   # canonical
    "bearer supersecret",   # lowercase (some proxies normalise)
    "BEARER supersecret",   # uppercase
    "BeArEr supersecret",   # mixed
])
async def test_llm_auth_scheme_is_case_insensitive(monkeypatch, header):
    """RFC 7235: the auth-scheme is case-insensitive."""
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    await verify_llm_auth(authorization=header)


@pytest.mark.asyncio
async def test_llm_auth_wrong_scheme_rejects(monkeypatch):
    """A non-Bearer scheme (e.g. Basic, Token) must be rejected."""
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    with pytest.raises(HTTPException) as exc:
        await verify_llm_auth(authorization="Basic supersecret")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_llm_auth_empty_token_after_scheme_rejects(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    with pytest.raises(HTTPException) as exc:
        await verify_llm_auth(authorization="Bearer    ")  # whitespace-only token
    assert exc.value.status_code == 401


# ── /vapi/server x-vapi-secret auth ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_server_auth_disabled_passes(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_server_secret", "")
    await verify_server_auth(x_vapi_secret=None)


@pytest.mark.asyncio
async def test_server_auth_valid_passes(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_server_secret", "webhooksecret")
    await verify_server_auth(x_vapi_secret="webhooksecret")


@pytest.mark.asyncio
async def test_server_auth_missing_rejects(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_server_secret", "webhooksecret")
    with pytest.raises(HTTPException) as exc:
        await verify_server_auth(x_vapi_secret=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_server_auth_wrong_rejects(monkeypatch):
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_server_secret", "webhooksecret")
    with pytest.raises(HTTPException) as exc:
        await verify_server_auth(x_vapi_secret="wrong")
    assert exc.value.status_code == 401
