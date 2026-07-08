"""Live entitlement checks: plan limits vs current usage, enforced with 402s
at action points (agent create, campaign start, lead import, dialer loop)."""

import json
from typing import NoReturn
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel

from orchestrator.db import require_pool


class Entitlements(BaseModel):
    plan_id: str
    plan_name: str
    status: str
    limits: dict[str, int]
    usage: dict[str, float]


def _payment_required(message: str) -> NoReturn:
    raise HTTPException(status_code=402, detail=message)


async def get_entitlements(org_id: UUID) -> Entitlements:
    pool = require_pool()
    sub = await pool.fetchrow(
        """
        SELECT s.plan_id, s.status, s.current_period_start, p.name, p.limits
        FROM subscriptions s JOIN plans p ON p.id = s.plan_id
        WHERE s.org_id = $1
        """,
        org_id,
    )
    if sub is None:
        _payment_required("No subscription — pick a plan to continue")

    usage = await pool.fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM agents WHERE org_id = $1 AND status != 'archived') AS agents,
          (SELECT COUNT(*) FROM campaigns WHERE org_id = $1 AND status = 'running') AS active_campaigns,
          (SELECT COALESCE(SUM(duration_seconds), 0) FROM calls
             WHERE org_id = $1 AND created_at >= $2) AS period_seconds
        """,
        org_id,
        sub["current_period_start"],
    )
    limits = json.loads(sub["limits"]) if isinstance(sub["limits"], str) else sub["limits"]
    return Entitlements(
        plan_id=sub["plan_id"],
        plan_name=sub["name"],
        status=sub["status"],
        limits=limits,
        usage={
            "agents": float(usage["agents"] or 0),
            "active_campaigns": float(usage["active_campaigns"] or 0),
            "minutes_used": round((usage["period_seconds"] or 0) / 60, 1),
        },
    )


async def check_can_create_agent(org_id: UUID) -> None:
    e = await get_entitlements(org_id)
    if e.status != "active":
        _payment_required("Subscription is not active")
    max_agents = e.limits.get("max_agents", 1)
    if e.usage["agents"] >= max_agents:
        _payment_required(f"{e.plan_name} plan allows {max_agents} agent(s) — upgrade to add more")


async def check_can_start_campaign(org_id: UUID) -> None:
    e = await get_entitlements(org_id)
    if e.status != "active":
        _payment_required("Subscription is not active")
    max_campaigns = e.limits.get("max_active_campaigns", 1)
    if e.usage["active_campaigns"] >= max_campaigns:
        _payment_required(
            f"{e.plan_name} plan allows {max_campaigns} active campaign(s) — pause one or upgrade"
        )
    included = e.limits.get("included_minutes", 0)
    if included and e.usage["minutes_used"] >= included:
        _payment_required(
            f"{e.plan_name} plan includes {included} call minutes — used up this period, upgrade to continue"
        )


async def max_leads_per_campaign(org_id: UUID) -> int:
    e = await get_entitlements(org_id)
    return e.limits.get("max_leads_per_campaign", 1000)
