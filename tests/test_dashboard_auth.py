"""Dashboard auth: Supabase JWT verification + /api/v1/me + org creation.

Tokens are minted HS256 with a test secret — hermetic, no network.
"""

import time
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator import db
from orchestrator.config import settings
from orchestrator.main import app
from tests.fakes import FakeDB

SECRET = "test-jwt-secret-0123456789abcdef0123456789abcdef"


def mint(sub=None, secret=SECRET, exp_offset=3600, email="u@example.com"):
    now = int(time.time())
    return jwt.encode(
        {
            "sub": str(sub or uuid4()),
            "email": email,
            "aud": "authenticated",
            "iat": now,
            "exp": now + exp_offset,
        },
        secret,
        algorithm="HS256",
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def hs256(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)


@pytest.fixture
def fake_db():
    fdb = FakeDB()
    db.set_pool(fdb)  # FakeDB quacks like the pool
    yield fdb
    db.set_pool(None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_me_401_without_header(client, hs256):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].lower().startswith("bearer")


async def test_me_401_with_garbage_token(client, hs256):
    resp = await client.get("/api/v1/me", headers=bearer("not.a.jwt"))
    assert resp.status_code == 401


async def test_me_401_with_expired_token(client, hs256):
    resp = await client.get("/api/v1/me", headers=bearer(mint(exp_offset=-10)))
    assert resp.status_code == 401


async def test_me_401_with_wrong_secret(client, hs256):
    resp = await client.get(
        "/api/v1/me", headers=bearer(mint(secret="other-secret-" + "x" * 32))
    )
    assert resp.status_code == 401


async def test_fails_closed_when_unconfigured(client, fake_db):
    # No supabase_jwt_secret and no supabase_url → even a well-formed token is rejected
    resp = await client.get("/api/v1/me", headers=bearer(mint()))
    assert resp.status_code == 401


async def test_503_when_db_unavailable(client, hs256):
    db.set_pool(None)
    resp = await client.get("/api/v1/me", headers=bearer(mint()))
    assert resp.status_code == 503


async def test_me_without_org(client, hs256, fake_db):
    resp = await client.get("/api/v1/me", headers=bearer(mint()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["org"] is None
    assert body["subscription"] is None
    assert body["user"]["email"] == "u@example.com"


async def test_me_with_org_and_role(client, hs256, fake_db):
    org_id = uuid4()
    fake_db.responses = {
        "FROM org_members": {"org_id": org_id, "role": "owner"},
        "FROM organizations": {"id": org_id, "name": "Acme Dental"},
        "FROM subscriptions": None,
    }
    resp = await client.get("/api/v1/me", headers=bearer(mint()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["org"] == {"id": str(org_id), "name": "Acme Dental", "role": "owner"}


async def test_create_org(client, hs256, fake_db):
    org_id = uuid4()
    fake_db.responses = {"INSERT INTO organizations": org_id}
    resp = await client.post(
        "/api/v1/orgs", json={"name": "Acme"}, headers=bearer(mint())
    )
    assert resp.status_code == 201
    assert resp.json() == {"org_id": str(org_id)}
    # owner membership + trial subscription written
    assert fake_db.queries("INSERT INTO org_members")
    assert fake_db.queries("INSERT INTO subscriptions")


async def test_create_org_409_when_already_member(client, hs256, fake_db):
    fake_db.responses = {"FROM org_members": {"org_id": uuid4(), "role": "owner"}}
    resp = await client.post(
        "/api/v1/orgs", json={"name": "Second"}, headers=bearer(mint())
    )
    assert resp.status_code == 409


async def test_create_org_validates_name(client, hs256, fake_db):
    resp = await client.post("/api/v1/orgs", json={"name": ""}, headers=bearer(mint()))
    assert resp.status_code == 422
