"""End-of-call webhook → calls row; dashboard call log endpoints."""

import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator import db
from orchestrator.config import settings
from orchestrator.main import app
from orchestrator.models.appointment import Appointment
from orchestrator.models.call_state import CallState, ConversationState
from orchestrator.services import call_state_store, tenant_resolver
from packs.pack_loader import load_pack
from tests.fakes import FakeDB
from tests.test_dashboard_auth import SECRET, bearer, mint

ORG_ID = uuid4()
AGENT_ID = uuid4()


def agent_row():
    return {
        "id": AGENT_ID,
        "org_id": ORG_ID,
        "config": json.dumps(load_pack("dental_saas").model_dump()),
    }


@pytest.fixture(autouse=True)
def _clean():
    tenant_resolver.clear_cache()
    call_state_store.clear_mem_store()
    yield
    tenant_resolver.clear_cache()
    call_state_store.clear_mem_store()
    db.set_pool(None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


def _report(call_id: str = "call-abc") -> dict:
    return {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": call_id,
                "assistantId": "as_1",
                "customer": {"number": "+15550001111"},
            },
            "startedAt": "2026-07-08T10:00:00Z",
            "endedAt": "2026-07-08T10:03:30Z",
            "durationSeconds": 210.5,
            "endedReason": "customer-ended-call",
            "cost": 0.42,
            "summary": "Discussed pricing, prospect booked a demo.",
            "messages": [
                {"role": "bot", "message": "Hi, this is Riley from DentaFlow."},
                {"role": "user", "message": "Sure, let's book Thursday."},
            ],
        }
    }


async def test_webhook_persists_call_record(client, monkeypatch):
    fdb = FakeDB({"WHERE vapi_assistant_id": agent_row()})
    db.set_pool(fdb)

    async def fake_extract(call_id, pack_name, messages):
        return Appointment(call_id=call_id, pack_name=pack_name, booked=True)

    monkeypatch.setattr("orchestrator.routers.vapi.extract_appointment", fake_extract)

    # Final per-call state left behind by the LLM turns
    await call_state_store.save_call_state(
        "call-abc",
        CallState(
            call_id="call-abc",
            pack_name="dental_saas",
            stage=ConversationState.END,
            objection_strikes={"price": 2},
        ),
    )

    resp = await client.post("/vapi/server", json=_report())
    assert resp.status_code == 200
    assert resp.json() == {"status": "saved", "booked": True}

    (insert,) = fdb.queries("INSERT INTO calls")
    args = insert[1]
    assert args[0] == ORG_ID              # org_id
    assert args[1] == AGENT_ID            # agent_id
    assert args[4] == "call-abc"          # vapi_call_id
    assert args[6] == "+15550001111"      # customer_number
    assert args[9] == 210                 # duration_seconds
    assert args[11] == "END"              # stage_reached
    assert args[12] == "booked"           # outcome
    assert args[13] is True               # booked
    assert json.loads(args[14]) == ["price"]  # objections
    # appointment write carries tenant scoping too
    (appt_insert,) = fdb.queries("INSERT INTO appointments")
    assert ORG_ID in appt_insert[1]


async def test_webhook_survives_minimal_report(client, monkeypatch):
    """No call state, no tenant match, sparse fields — still 200 + insert."""
    fdb = FakeDB()
    db.set_pool(fdb)

    async def fake_extract(call_id, pack_name, messages):
        return Appointment(call_id=call_id, pack_name=pack_name, booked=False)

    monkeypatch.setattr("orchestrator.routers.vapi.extract_appointment", fake_extract)

    resp = await client.post(
        "/vapi/server",
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call-min"},
                "messages": [{"role": "user", "message": "hello"}],
            }
        },
    )
    assert resp.status_code == 200
    (insert,) = fdb.queries("INSERT INTO calls")
    assert insert[1][0] is None           # org_id (legacy)
    assert insert[1][12] == "completed"   # outcome


async def test_list_calls_org_scoped(client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    row = {
        "id": uuid4(),
        "agent_id": AGENT_ID,
        "campaign_id": None,
        "vapi_call_id": "call-abc",
        "direction": "outbound",
        "customer_number": "+15550001111",
        "started_at": None,
        "duration_seconds": 210,
        "ended_reason": "customer-ended-call",
        "stage_reached": "END",
        "outcome": "booked",
        "booked": True,
        "summary": "s",
        "created_at": None,
    }
    fdb = FakeDB(
        {
            "FROM org_members": {"org_id": ORG_ID, "role": "owner"},
            "FROM calls": [row],
        }
    )
    db.set_pool(fdb)
    resp = await client.get("/api/v1/calls", headers=bearer(mint()))
    assert resp.status_code == 200
    assert resp.json()[0]["vapi_call_id"] == "call-abc"
    # the query was scoped to the caller's org
    (query, args) = fdb.queries("FROM calls")[0]
    assert args[0] == ORG_ID


async def test_get_call_404_cross_org(client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    db.set_pool(FakeDB({"FROM org_members": {"org_id": ORG_ID, "role": "owner"}}))
    resp = await client.get(f"/api/v1/calls/{uuid4()}", headers=bearer(mint()))
    assert resp.status_code == 404


async def test_list_calls_rejects_unknown_outcome(client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    db.set_pool(FakeDB({"FROM org_members": {"org_id": ORG_ID, "role": "owner"}}))
    resp = await client.get(
        "/api/v1/calls?outcome=exploded", headers=bearer(mint())
    )
    assert resp.status_code == 422
