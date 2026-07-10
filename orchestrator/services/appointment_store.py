"""Persist Appointment rows to Supabase."""

from dataclasses import dataclass
from datetime import datetime

import structlog

from orchestrator.db import get_pool
from orchestrator.models.appointment import Appointment

logger = structlog.get_logger()


@dataclass
class CalendarRef:
    """The calendar-invite columns already stored for a call, if any."""

    provider: str | None
    event_id: str | None
    event_url: str | None
    end_time: datetime | None


async def get_calendar_ref(call_id: str) -> CalendarRef | None:
    """Return the stored calendar reference for a call, or None if no row / no DB.

    Used to make end-of-call booking idempotent: if a prior delivery of the same
    report already created an invite, the caller reuses it instead of booking a
    second event. Returns None (⇒ proceed to book) when there's no DB pool.
    """
    pool = get_pool()
    if pool is None:
        return None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT calendar_provider, calendar_event_id, calendar_event_url, end_time
            FROM appointments
            WHERE call_id = $1
            """,
            call_id,
        )
    if row is None:
        return None
    return CalendarRef(
        provider=row["calendar_provider"],
        event_id=row["calendar_event_id"],
        event_url=row["calendar_event_url"],
        end_time=row["end_time"],
    )


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
                 requested_time, summary, transcript,
                 start_time, end_time,
                 calendar_provider, calendar_event_id, calendar_event_url)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (call_id) DO UPDATE
            SET booked             = EXCLUDED.booked,
                prospect_name      = EXCLUDED.prospect_name,
                prospect_email     = EXCLUDED.prospect_email,
                requested_time     = EXCLUDED.requested_time,
                summary            = EXCLUDED.summary,
                transcript         = EXCLUDED.transcript,
                start_time         = EXCLUDED.start_time,
                end_time           = EXCLUDED.end_time,
                calendar_provider  = EXCLUDED.calendar_provider,
                calendar_event_id  = EXCLUDED.calendar_event_id,
                calendar_event_url = EXCLUDED.calendar_event_url,
                updated_at         = NOW()
            """,
            appt.call_id,
            appt.pack_name,
            appt.booked,
            appt.prospect_name,
            appt.prospect_email,
            appt.requested_time,
            appt.summary,
            appt.transcript,
            appt.start_time,
            appt.end_time,
            appt.calendar_provider,
            appt.calendar_event_id,
            appt.calendar_event_url,
        )
    logger.info("appointment_saved", call_id=appt.call_id, booked=appt.booked)
