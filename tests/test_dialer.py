"""Dialer tick: claim-with-concurrency, failure handling, reaper, completion."""

from uuid import uuid4

import pytest

from orchestrator import db
from orchestrator.config import settings
from orchestrator.services import dialer, vapi_client
from tests.fakes import FakeDB

CAMPAIGN_ID = uuid4()
LEAD_ID = uuid4()


def running_campaign():
    return {
        "id": CAMPAIGN_ID,
        "org_id": uuid4(),
        "vapi_assistant_id": "as_1",
        "vapi_phone_number_id": "pn_1",
    }


@pytest.fixture(autouse=True)
def _clean():
    yield
    db.set_pool(None)


@pytest.fixture
def calls_made(monkeypatch):
    made: list[tuple[str, str, str]] = []

    async def fake_create_call(assistant_id, phone_number_id, number):
        made.append((assistant_id, phone_number_id, number))
        return {"id": f"call_{len(made)}"}

    monkeypatch.setattr(vapi_client, "create_call", fake_create_call)
    return made


async def test_tick_noop_without_pool(calls_made):
    await dialer.tick()
    assert calls_made == []


async def test_tick_dials_claimed_leads(calls_made):
    fdb = FakeDB(
        {
            "WHERE c.status = 'running'": [running_campaign()],
            "campaign_id = $1 AND status = 'calling'": 0,
            "FOR UPDATE SKIP LOCKED": [
                {"id": LEAD_ID, "phone_e164": "+14155550100"},
                {"id": uuid4(), "phone_e164": "+14155550101"},
            ],
            "IN ('queued', 'calling')": 2,
        }
    )
    db.set_pool(fdb)
    await dialer.tick()
    assert len(calls_made) == 2
    assert calls_made[0] == ("as_1", "pn_1", "+14155550100")
    # vapi call ids written back; campaign not completed
    assert len(fdb.queries("SET vapi_call_id")) == 2
    assert not fdb.queries("SET status = 'completed'")
    # reaper ran
    assert fdb.queries("stuck: no end-of-call report")


async def test_tick_respects_concurrency(calls_made, monkeypatch):
    monkeypatch.setattr(settings, "dialer_max_concurrency", 2)
    fdb = FakeDB(
        {
            "WHERE c.status = 'running'": [running_campaign()],
            "campaign_id = $1 AND status = 'calling'": 2,  # already at the cap
            "IN ('queued', 'calling')": 3,
        }
    )
    db.set_pool(fdb)
    await dialer.tick()
    assert calls_made == []
    assert not fdb.queries("FOR UPDATE SKIP LOCKED")


async def test_dial_failure_marks_lead_failed(monkeypatch):
    async def boom(*args):
        raise vapi_client.VapiError(500, "vapi down")

    monkeypatch.setattr(vapi_client, "create_call", boom)
    fdb = FakeDB(
        {
            "WHERE c.status = 'running'": [running_campaign()],
            "campaign_id = $1 AND status = 'calling'": 0,
            "FOR UPDATE SKIP LOCKED": [{"id": LEAD_ID, "phone_e164": "+14155550100"}],
            "IN ('queued', 'calling')": 1,
        }
    )
    db.set_pool(fdb)
    await dialer.tick()
    failed = fdb.queries("SET status = 'failed', last_error = $2")
    assert failed and "vapi down" in failed[0][1][1]


async def test_all_terminal_completes_campaign(calls_made):
    fdb = FakeDB(
        {
            "WHERE c.status = 'running'": [running_campaign()],
            "campaign_id = $1 AND status = 'calling'": 0,
            "FOR UPDATE SKIP LOCKED": [],
            "IN ('queued', 'calling')": 0,
        }
    )
    db.set_pool(fdb)
    await dialer.tick()
    assert fdb.queries("SET status = 'completed'")


async def test_unpublished_campaign_skipped(calls_made):
    campaign = running_campaign() | {"vapi_assistant_id": None}
    fdb = FakeDB({"WHERE c.status = 'running'": [campaign]})
    db.set_pool(fdb)
    await dialer.tick()
    assert calls_made == []
