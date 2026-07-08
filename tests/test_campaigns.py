"""Campaign CRUD + lifecycle endpoints."""

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
PHONE_ID = uuid4()


def campaign_row(status="draft", phone_number_id=PHONE_ID):
    return {
        "id": CAMPAIGN_ID,
        "name": "Q3 outreach",
        "status": status,
        "agent_id": AGENT_ID,
        "phone_number_id": phone_number_id,
        "started_at": None,
        "completed_at": None,
        "created_at": None,
        "total_leads": 5,
        "done_leads": 2,
        "calling_leads": 1,
    }


def agent_row(published=True):
    return {
        "id": AGENT_ID,
        "name": "A",
        "template_name": "dental_saas",
        "status": "active" if published else "draft",
        "vapi_assistant_id": "as_1" if published else None,
        "created_at": None,
        "updated_at": None,
        "config": json.dumps(load_pack("dental_saas").model_dump()),
    }


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


async def test_create_campaign(client, org_db):
    org_db.responses["FROM agents WHERE org_id"] = agent_row()
    org_db.responses["INSERT INTO campaigns"] = {"id": CAMPAIGN_ID, "status": "draft"}
    resp = await client.post(
        "/api/v1/campaigns",
        json={"name": "Q3 outreach", "agent_id": str(AGENT_ID)},
        headers=bearer(mint()),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "draft"


async def test_create_campaign_foreign_agent_404(client, org_db):
    resp = await client.post(
        "/api/v1/campaigns",
        json={"name": "X", "agent_id": str(uuid4())},
        headers=bearer(mint()),
    )
    assert resp.status_code == 404


async def test_get_campaign_with_leads(client, org_db):
    org_db.responses["FROM campaigns c WHERE c.org_id"] = campaign_row()
    org_db.responses["FROM leads WHERE campaign_id"] = [
        {
            "id": uuid4(),
            "name": "Jane",
            "company": "Acme",
            "email": None,
            "phone_e164": "+14155550100",
            "status": "queued",
            "attempts": 0,
            "last_error": None,
            "vapi_call_id": None,
            "updated_at": None,
        }
    ]
    resp = await client.get(f"/api/v1/campaigns/{CAMPAIGN_ID}", headers=bearer(mint()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_leads"] == 5
    assert body["leads"][0]["phone_e164"] == "+14155550100"


async def test_upload_leads_csv(client, org_db):
    org_db.responses["FROM campaigns c WHERE c.org_id"] = campaign_row()
    org_db.responses.update(subscription_rows())
    org_db.responses["INSERT INTO leads"] = "INSERT 0 1"
    resp = await client.post(
        f"/api/v1/campaigns/{CAMPAIGN_ID}/leads",
        files={"file": ("leads.csv", b"phone,name\n4155550100,Jane\n", "text/csv")},
        headers=bearer(mint()),
    )
    assert resp.status_code == 201
    assert resp.json()["imported"] == 1


async def test_start_requires_phone_number(client, org_db):
    org_db.responses["FROM campaigns c WHERE c.org_id"] = campaign_row(
        phone_number_id=None
    )
    resp = await client.post(
        f"/api/v1/campaigns/{CAMPAIGN_ID}/start", headers=bearer(mint())
    )
    assert resp.status_code == 409


async def test_start_requires_published_agent(client, org_db):
    org_db.responses["FROM campaigns c WHERE c.org_id"] = campaign_row()
    org_db.responses["FROM agents WHERE org_id"] = agent_row(published=False)
    resp = await client.post(
        f"/api/v1/campaigns/{CAMPAIGN_ID}/start", headers=bearer(mint())
    )
    assert resp.status_code == 409


async def test_start_and_pause(client, org_db):
    org_db.responses["FROM campaigns c WHERE c.org_id"] = campaign_row()
    org_db.responses["FROM agents WHERE org_id"] = agent_row(published=True)
    org_db.responses.update(subscription_rows())
    resp = await client.post(
        f"/api/v1/campaigns/{CAMPAIGN_ID}/start", headers=bearer(mint())
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "running"}

    org_db.responses["FROM campaigns c WHERE c.org_id"] = campaign_row(status="running")
    resp = await client.post(
        f"/api/v1/campaigns/{CAMPAIGN_ID}/pause", headers=bearer(mint())
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "paused"}


async def test_pause_409_when_not_running(client, org_db):
    org_db.responses["FROM campaigns c WHERE c.org_id"] = campaign_row(status="draft")
    resp = await client.post(
        f"/api/v1/campaigns/{CAMPAIGN_ID}/pause", headers=bearer(mint())
    )
    assert resp.status_code == 409


async def test_campaign_404_cross_org(client, org_db):
    resp = await client.get(f"/api/v1/campaigns/{uuid4()}", headers=bearer(mint()))
    assert resp.status_code == 404
