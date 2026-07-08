"""Knowledge upload → chunk → embed → insert, scoped to the owning org/agent."""

import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator import db
from orchestrator.config import settings
from orchestrator.main import app
from packs.pack_loader import load_pack
from tests.fakes import FakeDB
from tests.test_dashboard_auth import SECRET, bearer, mint

ORG_ID = uuid4()
AGENT_ID = uuid4()

_DOC = (
    "Our pricing starts at two hundred dollars per month for small practices.\n\n"
    "Implementation takes about two weeks with a dedicated onboarding specialist "
    "guiding your front office team through data migration and training sessions."
)


def _agent_row():
    return {
        "id": AGENT_ID,
        "name": "A",
        "template_name": "dental_saas",
        "status": "draft",
        "vapi_assistant_id": None,
        "created_at": None,
        "updated_at": None,
        "config": json.dumps(load_pack("dental_saas").model_dump()),
    }


@pytest.fixture
def org_db(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    async def fake_embed(text: str) -> list[float]:
        return [0.0] * 1536

    monkeypatch.setattr("orchestrator.services.rag.embed", fake_embed)
    fdb = FakeDB(
        {
            "FROM org_members": {"org_id": ORG_ID, "role": "owner"},
            "FROM agents WHERE org_id": _agent_row(),
        }
    )
    db.set_pool(fdb)
    yield fdb
    db.set_pool(None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_upload_inserts_chunks(client, org_db):
    resp = await client.post(
        f"/api/v1/agents/{AGENT_ID}/knowledge",
        files={"file": ("pricing.md", _DOC.encode(), "text/markdown")},
        headers=bearer(mint()),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source"] == "pricing.md"
    assert body["chunks"] >= 2
    inserts = org_db.queries("INSERT INTO knowledge_chunks")
    assert len(inserts) == body["chunks"]
    # every row carries tenant scoping
    for _q, args in inserts:
        assert args[4] == ORG_ID
        assert args[5] == AGENT_ID


async def test_upload_rejects_bad_extension(client, org_db):
    resp = await client.post(
        f"/api/v1/agents/{AGENT_ID}/knowledge",
        files={"file": ("evil.exe", b"x" * 100, "application/octet-stream")},
        headers=bearer(mint()),
    )
    assert resp.status_code == 400


async def test_upload_404_for_foreign_agent(client, org_db):
    org_db.responses["FROM agents WHERE org_id"] = None
    resp = await client.post(
        f"/api/v1/agents/{uuid4()}/knowledge",
        files={"file": ("a.md", _DOC.encode(), "text/markdown")},
        headers=bearer(mint()),
    )
    assert resp.status_code == 404


async def test_upload_503_without_embeddings_key(client, org_db, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    resp = await client.post(
        f"/api/v1/agents/{AGENT_ID}/knowledge",
        files={"file": ("a.md", _DOC.encode(), "text/markdown")},
        headers=bearer(mint()),
    )
    assert resp.status_code == 503


async def test_list_knowledge(client, org_db):
    org_db.responses["GROUP BY source"] = [{"source": "pricing.md", "chunks": 3}]
    resp = await client.get(
        f"/api/v1/agents/{AGENT_ID}/knowledge", headers=bearer(mint())
    )
    assert resp.status_code == 200
    assert resp.json() == [{"source": "pricing.md", "chunks": 3}]


async def test_delete_knowledge(client, org_db):
    resp = await client.delete(
        f"/api/v1/agents/{AGENT_ID}/knowledge/pricing.md", headers=bearer(mint())
    )
    assert resp.status_code == 204
    assert org_db.queries("DELETE FROM knowledge_chunks")
