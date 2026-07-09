"""Persist Appointment rows to Supabase."""

import structlog

from orchestrator.db import get_pool
from orchestrator.models.appointment import Appointment

logger = structlog.get_logger()


async def save_appointment(appt: Appointment) -> None:
    pool = get_pool()
    if pool is None:
        logger.warning("appointment_save_skipped", reason="no_db_pool", call_id=appt.call_id)
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO appointments
                (call_id, pack_name, booked, prospect_name, prospect_email,
                 requested_time, summary, transcript, org_id, agent_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (call_id) DO UPDATE
            SET booked         = EXCLUDED.booked,
                prospect_name  = EXCLUDED.prospect_name,
                prospect_email = EXCLUDED.prospect_email,
                requested_time = EXCLUDED.requested_time,
                summary        = EXCLUDED.summary,
                transcript     = EXCLUDED.transcript,
                org_id         = EXCLUDED.org_id,
                agent_id       = EXCLUDED.agent_id,
                updated_at     = NOW()
            """,
            appt.call_id,
            appt.pack_name,
            appt.booked,
            appt.prospect_name,
            appt.prospect_email,
            appt.requested_time,
            appt.summary,
            appt.transcript,
            appt.org_id,
            appt.agent_id,
        )
    logger.info("appointment_saved", call_id=appt.call_id, booked=appt.booked)
