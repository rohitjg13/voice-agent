"""Organization / profile / subscription queries for the dashboard API."""

import json
from typing import Any
from uuid import UUID

import structlog

from orchestrator.db import require_pool
from orchestrator.services.dashboard_auth import AuthContext

logger = structlog.get_logger()


async def get_me(ctx: AuthContext) -> dict[str, Any]:
    out: dict[str, Any] = {
        "user": {"id": str(ctx.user_id), "email": ctx.email},
        "org": None,
        "subscription": None,
    }
    if ctx.org_id is None:
        return out

    pool = require_pool()
    org = await pool.fetchrow(
        "SELECT id, name FROM organizations WHERE id = $1", ctx.org_id
    )
    if org:
        out["org"] = {"id": str(org["id"]), "name": org["name"], "role": ctx.role}

    sub = await pool.fetchrow(
        """
        SELECT s.plan_id, s.status, s.current_period_start, s.current_period_end,
               p.name AS plan_name, p.limits
        FROM subscriptions s JOIN plans p ON p.id = s.plan_id
        WHERE s.org_id = $1
        """,
        ctx.org_id,
    )
    if sub:
        out["subscription"] = {
            "plan_id": sub["plan_id"],
            "plan_name": sub["plan_name"],
            "status": sub["status"],
            "current_period_start": sub["current_period_start"],
            "current_period_end": sub["current_period_end"],
            "limits": json.loads(sub["limits"]),
        }
    return out


async def create_org(user_id: UUID, email: str, name: str) -> UUID:
    """Create org + owner membership (+ trial subscription). One org per user."""
    pool = require_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Profile normally exists via the auth.users trigger; upsert covers
        # users created before the trigger was installed.
        await conn.execute(
            "INSERT INTO profiles (id, email) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
            user_id,
            email,
        )
        org_id: UUID = await conn.fetchval(
            "INSERT INTO organizations (name) VALUES ($1) RETURNING id", name
        )
        await conn.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES ($1, $2, 'owner')",
            org_id,
            user_id,
        )
        await conn.execute(
            "INSERT INTO subscriptions (org_id, plan_id) VALUES ($1, 'trial') "
            "ON CONFLICT (org_id) DO NOTHING",
            org_id,
        )
    logger.info("org_created", org_id=str(org_id), user_id=str(user_id))
    return org_id
