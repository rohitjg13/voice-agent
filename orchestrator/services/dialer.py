"""Background dialer: claims queued leads and creates Vapi outbound calls.

ponytail: one asyncio task, no queue infra. FOR UPDATE SKIP LOCKED makes lead
claims safe even if Fly runs two machines; the semaphore is per-campaign
in-flight count, kept far below Vapi's ~10 concurrent-call org limit.
"""

import asyncio
from typing import Any

import structlog

from orchestrator.config import settings
from orchestrator.db import get_pool
from orchestrator.services import vapi_client

logger = structlog.get_logger()

_STUCK_MINUTES = 30


async def dialer_loop() -> None:
    logger.info("dialer_started", concurrency=settings.dialer_max_concurrency)
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("dialer_tick_failed", error=str(exc))
        await asyncio.sleep(settings.dialer_poll_seconds)


async def tick() -> None:
    pool = get_pool()
    if pool is None:
        return

    # Reap leads whose end-of-call report never arrived
    await pool.execute(
        """
        UPDATE leads SET status = 'failed', last_error = 'stuck: no end-of-call report',
                         updated_at = NOW()
        WHERE status = 'calling' AND claimed_at < NOW() - make_interval(mins => $1)
        """,
        _STUCK_MINUTES,
    )

    campaigns = await pool.fetch(
        """
        SELECT c.id, c.org_id, a.vapi_assistant_id, p.vapi_phone_number_id
        FROM campaigns c
        JOIN agents a ON a.id = c.agent_id
        LEFT JOIN phone_numbers p ON p.id = c.phone_number_id
        WHERE c.status = 'running'
        """
    )
    for campaign in campaigns:
        await _dial_campaign(pool, campaign)


async def _over_included_minutes(pool: Any, org_id: Any) -> bool:
    row = await pool.fetchrow(
        """
        SELECT (p.limits ->> 'included_minutes')::int AS included,
               (SELECT COALESCE(SUM(duration_seconds), 0) FROM calls
                  WHERE org_id = $1 AND created_at >= s.current_period_start) AS used_seconds
        FROM subscriptions s JOIN plans p ON p.id = s.plan_id
        WHERE s.org_id = $1
        """,
        org_id,
    )
    if row is None or not row["included"]:
        return False
    return bool((row["used_seconds"] or 0) / 60 >= row["included"])


async def _dial_campaign(pool: Any, campaign: Any) -> None:
    if not campaign["vapi_assistant_id"] or not campaign["vapi_phone_number_id"]:
        return

    # Plan minutes exhausted mid-campaign → auto-pause instead of burning money
    if await _over_included_minutes(pool, campaign["org_id"]):
        await pool.execute(
            "UPDATE campaigns SET status = 'paused', updated_at = NOW() WHERE id = $1",
            campaign["id"],
        )
        logger.warning("campaign_paused_over_minutes", campaign_id=str(campaign["id"]))
        return

    in_flight: int = await pool.fetchval(
        "SELECT COUNT(*) FROM leads WHERE campaign_id = $1 AND status = 'calling'",
        campaign["id"],
    )
    slots = settings.dialer_max_concurrency - in_flight
    if slots > 0:
        async with pool.acquire() as conn, conn.transaction():
            claimed = await conn.fetch(
                """
                UPDATE leads
                SET status = 'calling', claimed_at = NOW(), attempts = attempts + 1,
                    updated_at = NOW()
                WHERE id IN (
                    SELECT id FROM leads
                    WHERE campaign_id = $1 AND status = 'queued'
                    ORDER BY updated_at
                    LIMIT $2
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, phone_e164
                """,
                campaign["id"],
                slots,
            )
        for lead in claimed:
            try:
                call = await vapi_client.create_call(
                    campaign["vapi_assistant_id"],
                    campaign["vapi_phone_number_id"],
                    lead["phone_e164"],
                )
                await pool.execute(
                    "UPDATE leads SET vapi_call_id = $2, updated_at = NOW() WHERE id = $1",
                    lead["id"],
                    str(call.get("id") or ""),
                )
                logger.info("lead_dialed", lead_id=str(lead["id"]))
            except Exception as exc:
                await pool.execute(
                    """
                    UPDATE leads SET status = 'failed', last_error = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    lead["id"],
                    str(exc)[:300],
                )
                logger.warning("lead_dial_failed", lead_id=str(lead["id"]), error=str(exc))

    remaining: int = await pool.fetchval(
        """
        SELECT COUNT(*) FROM leads
        WHERE campaign_id = $1 AND status IN ('queued', 'calling')
        """,
        campaign["id"],
    )
    if remaining == 0:
        await pool.execute(
            """
            UPDATE campaigns SET status = 'completed', completed_at = NOW(), updated_at = NOW()
            WHERE id = $1 AND status = 'running'
            """,
            campaign["id"],
        )
        logger.info("campaign_completed", campaign_id=str(campaign["id"]))
