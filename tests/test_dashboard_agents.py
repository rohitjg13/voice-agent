"""Templates + agents CRUD endpoints (org-scoped)."""

import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator import db
from orchestrator.config import settings
from orchestrator.main import app
from packs.pack_loader import load_pack
from tests.fakes import FakeDB, subscription_rows
from tests.test_dashboard_auth import SECRET, bearer, mint

ORG_ID = uuid4()


def pack_config_json() -> str:
    return json.dumps(load_pack("dental_saas").model_dump())


@pytest.fixture
def org_db(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    fdb = FakeDB({"FROM org_members": {"org_id": ORG_ID, "role": "owner"}})
    db.set_pool(fdb)
    yield fdb
    db.set_pool(None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_list_templates(client, org_db):
    org_db.responses["ORDER BY name"] = [
        {"name": "dental_saas", "version": "1.0", "config": pack_config_json()}
    ]
    resp = await client.get("/api/v1/templates", headers=bearer(mint()))
    assert resp.status_code == 200
    (tpl,) = resp.json()
    assert tpl["name"] == "dental_saas"
    assert tpl["industry"]


async def test_create_agent_from_template(client, org_db):
    agent_id = uuid4()
    org_db.responses.update(subscription_rows())
    org_db.responses["FROM pack_templates WHERE name"] = {"config": pack_config_json()}
    org_db.responses["INSERT INTO agents"] = {"id": agent_id, "status": "draft"}
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "My Agent", "template_name": "dental_saas"},
        headers=bearer(mint()),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == str(agent_id)
    assert body["status"] == "draft"
    # config copied from the template
    (insert,) = org_db.queries("INSERT INTO agents")
    assert insert[1][0] == ORG_ID


async def test_create_agent_unknown_template(client, org_db):
    org_db.responses.update(subscription_rows())
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "X", "template_name": "nope"},
        headers=bearer(mint()),
    )
    assert resp.status_code == 404


async def test_get_agent_includes_config(client, org_db):
    agent_id = uuid4()
    org_db.responses["FROM agents WHERE org_id"] = {
        "id": agent_id,
        "name": "My Agent",
        "template_name": "dental_saas",
        "status": "draft",
        "vapi_assistant_id": None,
        "created_at": None,
        "updated_at": None,
        "config": pack_config_json(),
    }
    resp = await client.get(f"/api/v1/agents/{agent_id}", headers=bearer(mint()))
    assert resp.status_code == 200
    assert resp.json()["config"]["agent"]["name"]


async def test_get_agent_404_cross_org(client, org_db):
    resp = await client.get(f"/api/v1/agents/{uuid4()}", headers=bearer(mint()))
    assert resp.status_code == 404


async def test_put_agent_valid_config(client, org_db):
    org_db.responses["UPDATE agents"] = "UPDATE 1"
    config = load_pack("dental_saas").model_dump()
    config["agent"]["name"] = "Rewritten Rep"
    resp = await client.put(
        f"/api/v1/agents/{uuid4()}", json=config, headers=bearer(mint())
    )
    assert resp.status_code == 200


async def test_put_agent_invalid_config_422(client, org_db):
    resp = await client.put(
        f"/api/v1/agents/{uuid4()}",
        json={"name": "broken"},  # missing required IndustryPack fields
        headers=bearer(mint()),
    )
    assert resp.status_code == 422


async def test_agents_403_without_org(client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    db.set_pool(FakeDB())  # no org_members row
    try:
        resp = await client.get("/api/v1/agents", headers=bearer(mint()))
        assert resp.status_code == 403
    finally:
        db.set_pool(None)


async def test_agents_401_unauthenticated(client, org_db):
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 401
