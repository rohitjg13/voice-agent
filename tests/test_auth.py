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


# ── coverage for the bugs called out in code_review.json ─────────────────────


@pytest.mark.asyncio
async def test_llm_auth_trailing_whitespace_in_secret_passes(monkeypatch):
    """Trailing whitespace in .env / Fly secret must not break auth."""
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "abc ")
    await verify_llm_auth(authorization="Bearer abc")


@pytest.mark.asyncio
async def test_llm_auth_whitespace_only_secret_treated_as_disabled(monkeypatch):
    """A whitespace-only secret is indistinguishable from empty — disable auth."""
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "   ")
    await verify_llm_auth(authorization=None)


@pytest.mark.asyncio
async def test_llm_auth_tab_separator_passes(monkeypatch):
    """`Bearer\\tsecret` must be accepted (split() handles any whitespace run)."""
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    await verify_llm_auth(authorization="Bearer\tsupersecret")


@pytest.mark.asyncio
async def test_llm_auth_bearer_only_no_token_rejects(monkeypatch):
    """`Bearer ` (prefix only, empty token) must 401."""
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    with pytest.raises(HTTPException) as exc:
        await verify_llm_auth(authorization="Bearer ")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_llm_auth_401_has_www_authenticate_header(monkeypatch):
    """RFC 7235 §4.1: 401 responses must include a WWW-Authenticate challenge."""
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    with pytest.raises(HTTPException) as exc:
        await verify_llm_auth(authorization=None)
    assert exc.value.headers is not None
    assert exc.value.headers["WWW-Authenticate"].lower().startswith("bearer")


@pytest.mark.parametrize("header", [
    None,
    "",
    "supersecret",           # missing scheme
    "Basic supersecret",     # wrong scheme
    "Bearer ",               # empty token
    "Bearer wrong",          # bad token
])
@pytest.mark.asyncio
async def test_llm_auth_detail_is_generic(monkeypatch, header):
    """Every 401 path must return the same opaque detail (no oracle)."""
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "supersecret")
    with pytest.raises(HTTPException) as exc:
        await verify_llm_auth(authorization=header)
    assert exc.value.detail == "Unauthorized"


@pytest.mark.asyncio
async def test_server_auth_trailing_whitespace_in_secret_passes(monkeypatch):
    """Symmetry with llm-side: trailing whitespace must not break server auth."""
    monkeypatch.setattr(
        "orchestrator.services.auth.settings.vapi_server_secret", "webhooksecret "
    )
    await verify_server_auth(x_vapi_secret="webhooksecret")


@pytest.mark.asyncio
async def test_server_auth_401_has_www_authenticate_header(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.services.auth.settings.vapi_server_secret", "webhooksecret"
    )
    with pytest.raises(HTTPException) as exc:
        await verify_server_auth(x_vapi_secret=None)
    assert exc.value.headers is not None
    assert "WWW-Authenticate" in exc.value.headers
    assert exc.value.detail == "Unauthorized"
