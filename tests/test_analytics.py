"""Analytics aggregates — shaped from canned SQL results, always org-scoped."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator import db
from orchestrator.config import settings
from orchestrator.main import app
from tests.fakes import FakeDB
from tests.test_dashboard_auth import SECRET, bearer, mint

ORG_ID = uuid4()


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


async def test_overview_shapes_aggregates(client, org_db):
    org_db.responses.update(
        {
            "AS total_calls": {
                "total_calls": 40,
                "booked": 10,
                "total_seconds": 4800,
                "avg_seconds": 120.0,
            },
            "GROUP BY outcome": [
                {"outcome": "booked", "n": 10},
                {"outcome": "completed", "n": 25},
                {"outcome": "no_answer", "n": 5},
            ],
            "jsonb_array_elements_text": [
                {"obj": "price", "n": 12},
                {"obj": "timing", "n": 4},
            ],
        }
    )
    resp = await client.get("/api/v1/analytics/overview", headers=bearer(mint()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 40
    assert body["booked"] == 10
    assert body["book_rate"] == 0.25
    assert body["total_minutes"] == 80.0
    assert body["avg_duration_seconds"] == 120.0
    assert body["outcomes"]["completed"] == 25
    assert body["top_objections"][0] == {"objection": "price", "count": 12}
    # every aggregate query is org-scoped
    for _query, args in org_db.queries("FROM calls"):
        assert args[0] == ORG_ID


async def test_overview_empty_org(client, org_db):
    org_db.responses["AS total_calls"] = {
        "total_calls": 0,
        "booked": 0,
        "total_seconds": 0,
        "avg_seconds": 0,
    }
    resp = await client.get("/api/v1/analytics/overview", headers=bearer(mint()))
    assert resp.status_code == 200
    assert resp.json()["book_rate"] == 0.0


async def test_timeseries(client, org_db):
    org_db.responses["date_trunc"] = [
        {"day": "2026-07-01T00:00:00+00:00", "calls": 5, "booked": 1},
        {"day": "2026-07-02T00:00:00+00:00", "calls": 8, "booked": 3},
    ]
    resp = await client.get("/api/v1/analytics/timeseries", headers=bearer(mint()))
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert resp.json()[1]["booked"] == 3


async def test_days_param_clamped(client, org_db):
    resp = await client.get(
        "/api/v1/analytics/overview?days=9999", headers=bearer(mint())
    )
    assert resp.status_code == 422
