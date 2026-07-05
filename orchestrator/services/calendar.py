"""Create a real calendar event for a booked appointment.

Best-effort by design: a calendar failure must never drop the captured
appointment row or fail the webhook — it degrades to DB-only, the same way
db.py degrades without a pool.

Which provider runs is chosen per-pack (``pack.calendar.provider``) so one
client can use Cal.com and another Google Calendar. The non-secret target
(event type / calendar id) lives in the pack YAML; the credentials live in env
(orchestrator.config). Both providers are real; neither is a stub.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

import structlog

from orchestrator.config import settings
from orchestrator.models.appointment import Appointment
from orchestrator.services.llm_http import shared_async_http_client
from packs._schema.pack import CalendarConfig, IndustryPack

logger = structlog.get_logger()

_GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar.events"


@dataclass
class CalendarResult:
    provider: str
    event_id: str
    event_url: str | None


async def book_appointment(pack: IndustryPack, appt: Appointment) -> Appointment:
    """Create a calendar event for a booked appointment, returning an enriched copy.

    No-ops (returns ``appt`` unchanged) when there's nothing bookable: the call
    didn't book, the pack has no provider, or we're missing a time or email.
    Any provider error is swallowed — the appointment is still saved DB-side.
    """
    cfg = pack.calendar
    start = appt.start_time

    # end_time is meaningful whenever we resolved a concrete start — independent
    # of the provider — so DB-only mode (provider "none", or a skipped/failed
    # invite) still persists a complete [start, end] window.
    if start is not None and appt.end_time is None:
        appt = appt.model_copy(
            update={"end_time": start + timedelta(minutes=cfg.duration_minutes)}
        )

    if (
        cfg.provider == "none"
        or not appt.booked
        or start is None
        or not appt.prospect_email
    ):
        return appt

    end = start + timedelta(minutes=cfg.duration_minutes)
    tz = pack.scheduling.timezone

    try:
        if cfg.provider == "cal_com":
            result = await _book_calcom(cfg, appt, start, end, tz)
        elif cfg.provider == "google":
            result = await _book_google(cfg, appt, start, end, tz)
        else:  # pragma: no cover - schema Literal already constrains this
            return appt
    except Exception as exc:
        logger.warning(
            "calendar_book_failed",
            provider=cfg.provider,
            call_id=appt.call_id,
            error=str(exc),
        )
        return appt

    if result is None:
        return appt

    logger.info(
        "calendar_event_created",
        provider=result.provider,
        call_id=appt.call_id,
        event_id=result.event_id,
    )
    return appt.model_copy(update={
        "end_time": end,
        "calendar_provider": result.provider,
        "calendar_event_id": result.event_id,
        "calendar_event_url": result.event_url,
    })


# ── Cal.com ──────────────────────────────────────────────────────────────────


async def _book_calcom(
    cfg: CalendarConfig, appt: Appointment, start: datetime, end: datetime, tz: str
) -> CalendarResult | None:
    if not settings.calcom_api_key:
        logger.warning("calcom_skipped", reason="no_api_key", call_id=appt.call_id)
        return None
    if cfg.event_type_id is None:
        logger.warning("calcom_skipped", reason="no_event_type_id", call_id=appt.call_id)
        return None

    body = {
        "eventTypeId": cfg.event_type_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timeZone": tz,
        "language": "en",
        "responses": {
            "name": appt.prospect_name or "Prospect",
            "email": appt.prospect_email,
        },
        "metadata": {"call_id": appt.call_id, "pack": appt.pack_name},
    }

    client = shared_async_http_client()
    resp = await client.post(
        f"{settings.calcom_base_url}/bookings",
        params={"apiKey": settings.calcom_api_key},
        json=body,
    )
    if resp.status_code >= 300:
        logger.warning(
            "calcom_book_rejected",
            status=resp.status_code,
            body=resp.text[:500],
            call_id=appt.call_id,
        )
        return None

    booking = resp.json()
    # Cal.com has wrapped the booking under "booking" in some API versions.
    if isinstance(booking, dict) and isinstance(booking.get("booking"), dict):
        booking = booking["booking"]
    uid = booking.get("uid") if isinstance(booking, dict) else None
    bid = booking.get("id") if isinstance(booking, dict) else None
    return CalendarResult(
        provider="cal_com",
        event_id=str(bid or uid or ""),
        event_url=f"https://cal.com/booking/{uid}" if uid else None,
    )


# ── Google Calendar ──────────────────────────────────────────────────────────


async def _book_google(
    cfg: CalendarConfig, appt: Appointment, start: datetime, end: datetime, tz: str
) -> CalendarResult | None:
    if not settings.google_calendar_credentials_json:
        logger.warning("google_calendar_skipped", reason="no_credentials", call_id=appt.call_id)
        return None
    if not cfg.calendar_id:
        logger.warning("google_calendar_skipped", reason="no_calendar_id", call_id=appt.call_id)
        return None

    token = await _google_access_token()
    if not token:
        return None

    body = {
        "summary": appt.summary or f"{appt.pack_name} intro call",
        "description": (appt.summary or "") + f"\n\nBooked via voice agent (call {appt.call_id}).",
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        "attendees": [{"email": appt.prospect_email}],
    }

    client = shared_async_http_client()
    resp = await client.post(
        f"https://www.googleapis.com/calendar/v3/calendars/{cfg.calendar_id}/events",
        params={"sendUpdates": "all"},
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    if resp.status_code >= 300:
        logger.warning(
            "google_calendar_rejected",
            status=resp.status_code,
            body=resp.text[:500],
            call_id=appt.call_id,
        )
        return None

    event = resp.json()
    return CalendarResult(
        provider="google",
        event_id=str(event.get("id", "")),
        event_url=event.get("htmlLink"),
    )


def _load_service_account_info() -> dict[str, Any]:
    """Accept either a raw JSON blob or a path to the service-account file."""
    raw = settings.google_calendar_credentials_json.strip()
    if raw.startswith("{"):
        return cast(dict[str, Any], json.loads(raw))
    with open(raw) as fh:
        return cast(dict[str, Any], json.load(fh))


async def _google_access_token() -> str | None:
    """Mint a service-account access token. Refresh is blocking → offload it."""
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account
    except ImportError:
        logger.warning("google_calendar_skipped", reason="google_auth_not_installed")
        return None

    try:
        info = _load_service_account_info()
        creds = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
            info, scopes=[_GOOGLE_SCOPE]
        )
        await asyncio.to_thread(
            creds.refresh, google.auth.transport.requests.Request()
        )
        return cast("str | None", creds.token)
    except Exception as exc:
        logger.warning("google_calendar_token_failed", error=str(exc))
        return None
