"""Persist + query call records.

Writes come from the webhook (degrade gracefully — a DB outage must not 500
Vapi's webhook); reads serve the dashboard (require_pool → 503).
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from orchestrator.db import get_pool, require_pool
from orchestrator.models.call_record import CallRecord

logger = structlog.get_logger()


async def save_call_record(record: CallRecord) -> None:
    """UPSERT on vapi_call_id — idempotent against Vapi webhook retries."""
    pool = get_pool()
    if pool is None:
        logger.warning("call_record_skipped", reason="no_db_pool", vapi_call_id=record.vapi_call_id)
        return

    await pool.execute(
        """
        INSERT INTO calls
            (org_id, agent_id, campaign_id, lead_id, vapi_call_id, direction,
             customer_number, started_at, ended_at, duration_seconds, ended_reason,
             stage_reached, outcome, booked, objections, transcript, summary, cost_usd)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
        ON CONFLICT (vapi_call_id) DO UPDATE
        SET ended_at = EXCLUDED.ended_at,
            duration_seconds = EXCLUDED.duration_seconds,
            ended_reason = EXCLUDED.ended_reason,
            stage_reached = EXCLUDED.stage_reached,
            outcome = EXCLUDED.outcome,
            booked = EXCLUDED.booked,
            objections = EXCLUDED.objections,
            transcript = EXCLUDED.transcript,
            summary = EXCLUDED.summary,
            cost_usd = EXCLUDED.cost_usd
        """,
        record.org_id,
        record.agent_id,
        record.campaign_id,
        record.lead_id,
        record.vapi_call_id,
        record.direction,
        record.customer_number,
        record.started_at,
        record.ended_at,
        record.duration_seconds,
        record.ended_reason,
        record.stage_reached,
        record.outcome,
        record.booked,
        json.dumps(record.objections),
        json.dumps(record.transcript),
        record.summary,
        record.cost_usd,
    )
    logger.info("call_record_saved", vapi_call_id=record.vapi_call_id, outcome=record.outcome)


_LEAD_STATUS_BY_OUTCOME = {"no_answer": "no_answer", "failed": "failed", "voicemail": "no_answer"}


async def link_lead(vapi_call_id: str, outcome: str | None) -> None:
    """Flip the dialed lead terminal and stamp campaign/lead onto the call row."""
    pool = get_pool()
    if pool is None:
        return
    lead_status = _LEAD_STATUS_BY_OUTCOME.get(outcome or "", "completed")
    row = await pool.fetchrow(
        """
        UPDATE leads SET status = $2, updated_at = NOW()
        WHERE vapi_call_id = $1
        RETURNING id, campaign_id
        """,
        vapi_call_id,
        lead_status,
    )
    if row:
        await pool.execute(
            "UPDATE calls SET campaign_id = $2, lead_id = $3 WHERE vapi_call_id = $1",
            vapi_call_id,
            row["campaign_id"],
            row["id"],
        )
        logger.info("lead_completed", vapi_call_id=vapi_call_id, status=lead_status)


_LIST_COLUMNS = """
    id, agent_id, campaign_id, vapi_call_id, direction, customer_number,
    started_at, duration_seconds, ended_reason, stage_reached, outcome,
    booked, summary, created_at
"""


async def list_calls(
    org_id: UUID,
    limit: int = 50,
    before: datetime | None = None,
    outcome: str | None = None,
) -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch(
        f"""
        SELECT {_LIST_COLUMNS}
        FROM calls
        WHERE org_id = $1
          AND ($2::timestamptz IS NULL OR created_at < $2)
          AND ($3::text IS NULL OR outcome = $3)
        ORDER BY created_at DESC
        LIMIT $4
        """,
        org_id,
        before,
        outcome,
        limit,
    )
    return [dict(r) for r in rows]


async def get_call(org_id: UUID, call_id: UUID) -> dict[str, Any] | None:
    pool = require_pool()
    row = await pool.fetchrow(
        "SELECT * FROM calls WHERE org_id = $1 AND id = $2", org_id, call_id
    )
    if row is None:
        return None
    out = dict(row)
    for field in ("objections", "transcript"):
        if isinstance(out.get(field), str):
            out[field] = json.loads(out[field])
    return out


async def list_appointments(org_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch(
        """
        SELECT id, call_id, booked, prospect_name, prospect_email,
               requested_time, summary, created_at
        FROM appointments
        WHERE org_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        org_id,
        limit,
    )
    return [dict(r) for r in rows]
