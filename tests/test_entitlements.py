"""Entitlement enforcement (402s) + stub billing endpoints."""

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
AGENT_ID = uuid4()
CAMPAIGN_ID = uuid4()


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


def _campaign_and_agent(org_db):
    org_db.responses["FROM campaigns c WHERE c.org_id"] = {
        "id": CAMPAIGN_ID,
        "name": "C",
        "status": "draft",
        "agent_id": AGENT_ID,
        "phone_number_id": uuid4(),
        "started_at": None,
        "completed_at": None,
        "created_at": None,
        "total_leads": 1,
        "done_leads": 0,
        "calling_leads": 0,
    }
    org_db.responses["FROM agents WHERE org_id"] = {
        "id": AGENT_ID,
        "name": "A",
        "template_name": "dental_saas",
        "status": "active",
        "vapi_assistant_id": "as_1",
        "created_at": None,
        "updated_at": None,
        "config": json.dumps(load_pack("dental_saas").model_dump()),
    }


async def test_agent_create_blocked_at_plan_limit(client, org_db):
    org_db.responses.update(subscription_rows(limits={"max_agents": 1}, agents=1))
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "Second", "template_name": "dental_saas"},
        headers=bearer(mint()),
    )
    assert resp.status_code == 402
    assert "upgrade" in resp.json()["detail"].lower()


async def test_agent_create_blocked_without_subscription(client, org_db):
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "X", "template_name": "dental_saas"},
        headers=bearer(mint()),
    )
    assert resp.status_code == 402


async def test_campaign_start_blocked_over_minutes(client, org_db):
    _campaign_and_agent(org_db)
    org_db.responses.update(
        subscription_rows(
            limits={"max_active_campaigns": 5, "included_minutes": 30},
            period_seconds=30 * 60,
        )
    )
    resp = await client.post(
        f"/api/v1/campaigns/{CAMPAIGN_ID}/start", headers=bearer(mint())
    )
    assert resp.status_code == 402
    assert "minutes" in resp.json()["detail"].lower()


async def test_campaign_start_blocked_at_campaign_limit(client, org_db):
    _campaign_and_agent(org_db)
    org_db.responses.update(
        subscription_rows(limits={"max_active_campaigns": 1}, active_campaigns=1)
    )
    resp = await client.post(
        f"/api/v1/campaigns/{CAMPAIGN_ID}/start", headers=bearer(mint())
    )
    assert resp.status_code == 402


async def test_subscription_endpoint_shape(client, org_db):
    org_db.responses.update(subscription_rows(agents=1, period_seconds=120))
    resp = await client.get("/api/v1/billing/subscription", headers=bearer(mint()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_id"] == "trial"
    assert body["usage"]["minutes_used"] == 2.0
    assert body["limits"]["max_agents"] == 5


async def test_list_plans(client, org_db):
    org_db.responses["FROM plans ORDER BY price_cents"] = [
        {"id": "trial", "name": "Trial", "price_cents": 0, "limits": json.dumps({"max_agents": 1})}
    ]
    resp = await client.get("/api/v1/billing/plans", headers=bearer(mint()))
    assert resp.status_code == 200
    assert resp.json()[0]["limits"]["max_agents"] == 1


async def test_fake_checkout_activates_plan(client, org_db):
    org_db.responses["SELECT id FROM plans WHERE id"] = {"id": "growth"}
    resp = await client.post(
        "/api/v1/billing/checkout",
        json={"plan_id": "growth"},
        headers=bearer(mint()),
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "active", "plan_id": "growth"}
    (upsert,) = org_db.queries("INSERT INTO subscriptions")
    assert upsert[1] == (ORG_ID, "growth")


async def test_checkout_unknown_plan_404(client, org_db):
    resp = await client.post(
        "/api/v1/billing/checkout",
        json={"plan_id": "enterprise-mega"},
        headers=bearer(mint()),
    )
    assert resp.status_code == 404
