"""End-to-end route-wiring tests.

Hits the live ASGI app via httpx so a future refactor that drops `dependencies=`
from one of the stacked @router.post decorators on `/vapi/llm` would be caught
in CI. The unit tests in test_auth.py call the dependency function directly,
which can't notice if the dependency was never attached to the route.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app


@pytest.mark.asyncio
async def test_vapi_llm_returns_401_without_authorization(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.services.auth.settings.vapi_llm_secret", "supersecret"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/vapi/llm", json={})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}
    assert resp.headers["www-authenticate"].lower().startswith("bearer")


@pytest.mark.asyncio
async def test_vapi_llm_chat_completions_returns_401_without_authorization(monkeypatch):
    """Guards the second stacked decorator — a refactor dropping
    `dependencies=` from one of the two @router.post lines must not let this
    path ship unauthenticated."""
    monkeypatch.setattr(
        "orchestrator.services.auth.settings.vapi_llm_secret", "supersecret"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/vapi/llm/chat/completions", json={})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


@pytest.mark.asyncio
async def test_vapi_server_returns_401_without_x_vapi_secret(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.services.auth.settings.vapi_server_secret", "webhooksecret"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/vapi/server", json={})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


@pytest.mark.asyncio
async def test_openapi_operation_ids_are_unique():
    """Stacked @router.post decorators must produce distinct OpenAPI operation IDs."""
    spec = app.openapi()
    op_ids = []
    for _path, methods in spec["paths"].items():
        for _verb, op in methods.items():
            if isinstance(op, dict) and "operationId" in op:
                op_ids.append(op["operationId"])
    assert len(op_ids) == len(set(op_ids)), f"duplicate operation IDs: {op_ids}"
