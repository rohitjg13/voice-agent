from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from orchestrator.db import require_pool
from orchestrator.services import agent_config_store, entitlements, lead_import
from orchestrator.services.dashboard_auth import OrgCtx

router = APIRouter()

_MAX_CSV_BYTES = 2_000_000

_CAMPAIGN_COLUMNS = """
    c.id, c.name, c.status, c.agent_id, c.phone_number_id,
    c.started_at, c.completed_at, c.created_at,
    (SELECT COUNT(*) FROM leads l WHERE l.campaign_id = c.id) AS total_leads,
    (SELECT COUNT(*) FROM leads l WHERE l.campaign_id = c.id
        AND l.status IN ('completed', 'failed', 'no_answer', 'dnc')) AS done_leads,
    (SELECT COUNT(*) FROM leads l WHERE l.campaign_id = c.id
        AND l.status = 'calling') AS calling_leads
"""


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    agent_id: UUID
    phone_number_id: UUID | None = None


async def _owned_campaign(ctx: OrgCtx, campaign_id: UUID) -> dict[str, Any]:
    pool = require_pool()
    row = await pool.fetchrow(
        f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns c WHERE c.org_id = $1 AND c.id = $2",
        ctx.org_id,
        campaign_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return dict(row)


@router.get("/campaigns")
async def list_campaigns(ctx: OrgCtx) -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch(
        f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns c WHERE c.org_id = $1 ORDER BY c.created_at DESC",
        ctx.org_id,
    )
    return [dict(r) for r in rows]


@router.post("/campaigns", status_code=201)
async def create_campaign(body: CampaignCreate, ctx: OrgCtx) -> dict[str, Any]:
    agent = await agent_config_store.get_agent(ctx.org_id, body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    pool = require_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO campaigns (org_id, agent_id, phone_number_id, name)
        VALUES ($1, $2, $3, $4)
        RETURNING id, status
        """,
        ctx.org_id,
        body.agent_id,
        body.phone_number_id,
        body.name,
    )
    return {"id": str(row["id"]), "name": body.name, "status": row["status"]}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: UUID, ctx: OrgCtx) -> dict[str, Any]:
    campaign = await _owned_campaign(ctx, campaign_id)
    pool = require_pool()
    leads = await pool.fetch(
        """
        SELECT id, name, company, email, phone_e164, status, attempts,
               last_error, vapi_call_id, updated_at
        FROM leads WHERE campaign_id = $1 ORDER BY updated_at DESC LIMIT 500
        """,
        campaign_id,
    )
    campaign["leads"] = [dict(r) for r in leads]
    return campaign


@router.post("/campaigns/{campaign_id}/leads", status_code=201)
async def upload_leads(
    campaign_id: UUID, file: UploadFile, ctx: OrgCtx
) -> dict[str, Any]:
    campaign = await _owned_campaign(ctx, campaign_id)
    if campaign["status"] == "completed":
        raise HTTPException(status_code=409, detail="Campaign already completed")
    data = await file.read(_MAX_CSV_BYTES + 1)
    if len(data) > _MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV too large (2 MB max)")
    max_rows = await entitlements.max_leads_per_campaign(ctx.org_id)
    return await lead_import.import_leads(ctx.org_id, campaign_id, data, max_rows=max_rows)


@router.post("/campaigns/{campaign_id}/start")
async def start_campaign(campaign_id: UUID, ctx: OrgCtx) -> dict[str, str]:
    campaign = await _owned_campaign(ctx, campaign_id)
    if campaign["status"] == "completed":
        raise HTTPException(status_code=409, detail="Campaign already completed")
    if campaign["phone_number_id"] is None:
        raise HTTPException(status_code=409, detail="Attach a phone number first")

    agent = await agent_config_store.get_agent(ctx.org_id, campaign["agent_id"])
    if agent is None or not agent["vapi_assistant_id"]:
        raise HTTPException(status_code=409, detail="Publish the agent to Vapi first")

    await entitlements.check_can_start_campaign(ctx.org_id)

    pool = require_pool()
    await pool.execute(
        """
        UPDATE campaigns
        SET status = 'running', started_at = COALESCE(started_at, NOW()), updated_at = NOW()
        WHERE id = $1
        """,
        campaign_id,
    )
    return {"status": "running"}


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: UUID, ctx: OrgCtx) -> dict[str, str]:
    campaign = await _owned_campaign(ctx, campaign_id)
    if campaign["status"] != "running":
        raise HTTPException(status_code=409, detail="Campaign is not running")
    pool = require_pool()
    await pool.execute(
        "UPDATE campaigns SET status = 'paused', updated_at = NOW() WHERE id = $1",
        campaign_id,
    )
    return {"status": "paused"}
