"""Tenant resolution chain: assistantId → metadata.agent_id → YAML fallback."""

import json
from uuid import uuid4

import pytest

from orchestrator import db
from orchestrator.services import tenant_resolver
from orchestrator.services.tenant_resolver import resolve_agent
from packs.pack_loader import load_pack
from tests.fakes import FakeDB


@pytest.fixture(autouse=True)
def _clean():
    tenant_resolver.clear_cache()
    yield
    tenant_resolver.clear_cache()
    db.set_pool(None)


def agent_row(org_id, agent_id):
    return {
        "id": agent_id,
        "org_id": org_id,
        "config": json.dumps(load_pack("dental_saas").model_dump()),
    }


async def test_no_call_falls_back_to_active_pack():
    resolved = await resolve_agent(None)
    assert resolved.pack.name == load_pack("dental_saas").name
    assert resolved.org_id is None
    assert resolved.agent_id is None


async def test_no_pool_falls_back():
    resolved = await resolve_agent({"assistantId": "as_123"})
    assert resolved.org_id is None


async def test_assistant_id_resolves_tenant():
    org_id, agent_id = uuid4(), uuid4()
    db.set_pool(FakeDB({"WHERE vapi_assistant_id": agent_row(org_id, agent_id)}))
    resolved = await resolve_agent({"assistantId": "as_123"})
    assert resolved.org_id == org_id
    assert resolved.agent_id == agent_id
    assert resolved.pack.name  # validated IndustryPack


async def test_unknown_assistant_id_falls_back():
    db.set_pool(FakeDB())
    resolved = await resolve_agent({"assistantId": "as_unknown"})
    assert resolved.org_id is None


async def test_metadata_agent_id_resolves():
    org_id, agent_id = uuid4(), uuid4()
    db.set_pool(FakeDB({"FROM agents WHERE id": agent_row(org_id, agent_id)}))
    resolved = await resolve_agent({"metadata": {"agent_id": str(agent_id)}})
    assert resolved.agent_id == agent_id


async def test_bad_metadata_agent_id_falls_back():
    db.set_pool(FakeDB())
    resolved = await resolve_agent({"metadata": {"agent_id": "not-a-uuid"}})
    assert resolved.org_id is None


async def test_db_error_falls_back():
    class Boom:
        async def fetchrow(self, *a):
            raise RuntimeError("db down")

    db.set_pool(Boom())
    resolved = await resolve_agent({"assistantId": "as_123"})
    assert resolved.org_id is None
    assert resolved.pack.name


async def test_cache_avoids_second_lookup():
    org_id, agent_id = uuid4(), uuid4()
    fdb = FakeDB({"WHERE vapi_assistant_id": agent_row(org_id, agent_id)})
    db.set_pool(fdb)
    await resolve_agent({"assistantId": "as_1"})
    await resolve_agent({"assistantId": "as_1"})
    assert len(fdb.queries("vapi_assistant_id")) == 1
