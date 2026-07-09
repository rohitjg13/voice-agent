"""Stub billing: real plans/subscriptions model, fake checkout.
Stripe later replaces only the checkout handler (+ adds a webhook)."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orchestrator.db import require_pool
from orchestrator.services import entitlements
from orchestrator.services.dashboard_auth import OrgCtx

router = APIRouter()


class CheckoutBody(BaseModel):
    plan_id: str


@router.get("/billing/plans")
async def list_plans(ctx: OrgCtx) -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch("SELECT id, name, price_cents, limits FROM plans ORDER BY price_cents")
    out = []
    for r in rows:
        limits = json.loads(r["limits"]) if isinstance(r["limits"], str) else r["limits"]
        out.append({"id": r["id"], "name": r["name"], "price_cents": r["price_cents"], "limits": limits})
    return out


@router.get("/billing/subscription")
async def subscription(ctx: OrgCtx) -> dict[str, Any]:
    e = await entitlements.get_entitlements(ctx.org_id)
    return e.model_dump()


@router.post("/billing/checkout")
async def checkout(body: CheckoutBody, ctx: OrgCtx) -> dict[str, str]:
    """Fake checkout: activates the plan immediately and resets the period."""
    pool = require_pool()
    plan = await pool.fetchrow("SELECT id FROM plans WHERE id = $1", body.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Unknown plan")
    await pool.execute(
        """
        INSERT INTO subscriptions (org_id, plan_id, status, provider,
                                   current_period_start, current_period_end)
        VALUES ($1, $2, 'active', 'stub', NOW(), NOW() + INTERVAL '30 days')
        ON CONFLICT (org_id) DO UPDATE
        SET plan_id = EXCLUDED.plan_id,
            status = 'active',
            current_period_start = NOW(),
            current_period_end = NOW() + INTERVAL '30 days',
            updated_at = NOW()
        """,
        ctx.org_id,
        body.plan_id,
    )
    return {"status": "active", "plan_id": body.plan_id}
