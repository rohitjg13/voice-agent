"""End-of-call webhook orchestration: booking vs. idempotent reuse.

Calls the handler function directly (bypassing the shared-secret dependency)
and patches the collaborators, so these assert the flow around book_appointment
without needing a DB or a live Vapi payload.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.models.appointment import Appointment
from orchestrator.routers import vapi
from orchestrator.services.appointment_store import CalendarRef

_PAYLOAD = {
    "message": {
        "type": "end-of-call-report",
        "call": {"id": "call-xyz"},
        "messages": [
            {"role": "user", "message": "yes, book me for Thursday"},
            {"role": "bot", "message": "great, you're all set"},
        ],
    }
}


def _pack() -> MagicMock:
    pack = MagicMock()
    pack.name = "dental_saas"
    pack.scheduling.timezone = "UTC"
    return pack


def _extracted() -> Appointment:
    return Appointment(
        call_id="call-xyz",
        pack_name="dental_saas",
        booked=True,
        prospect_email="jane@dental.com",
    )


@pytest.mark.asyncio
async def test_webhook_books_when_no_existing_event():
    booked = _extracted().model_copy(
        update={"calendar_event_url": "https://cal.com/booking/new"}
    )
    with (
        patch.object(vapi, "load_pack", return_value=_pack()),
        patch.object(vapi, "extract_appointment", AsyncMock(return_value=_extracted())),
        patch.object(vapi, "get_calendar_ref", AsyncMock(return_value=None)),
        patch.object(vapi, "book_appointment", AsyncMock(return_value=booked)) as book,
        patch.object(vapi, "save_appointment", AsyncMock()) as save,
    ):
        result = await vapi.vapi_server(_PAYLOAD)

    book.assert_awaited_once()
    save.assert_awaited_once()
    assert result["calendar_event_url"] == "https://cal.com/booking/new"


@pytest.mark.asyncio
async def test_webhook_reuses_existing_event_and_skips_booking():
    """A redelivered report must not create a second invite."""
    existing = CalendarRef(
        provider="cal_com",
        event_id="999",
        event_url="https://cal.com/booking/abc123",
        end_time=None,
    )
    with (
        patch.object(vapi, "load_pack", return_value=_pack()),
        patch.object(vapi, "extract_appointment", AsyncMock(return_value=_extracted())),
        patch.object(vapi, "get_calendar_ref", AsyncMock(return_value=existing)),
        patch.object(vapi, "book_appointment", AsyncMock()) as book,
        patch.object(vapi, "save_appointment", AsyncMock()) as save,
    ):
        result = await vapi.vapi_server(_PAYLOAD)

    book.assert_not_called()
    # The stored reference is carried onto the re-saved row, not nulled out.
    saved = save.call_args.args[0]
    assert saved.calendar_event_id == "999"
    assert saved.calendar_provider == "cal_com"
    assert result["calendar_event_url"] == "https://cal.com/booking/abc123"


@pytest.mark.asyncio
async def test_webhook_reuses_when_provider_set_but_id_missing():
    """A prior 2xx booking recorded the provider but no id → still skip re-booking."""
    existing = CalendarRef(
        provider="cal_com", event_id="", event_url=None, end_time=None
    )
    with (
        patch.object(vapi, "load_pack", return_value=_pack()),
        patch.object(vapi, "extract_appointment", AsyncMock(return_value=_extracted())),
        patch.object(vapi, "get_calendar_ref", AsyncMock(return_value=existing)),
        patch.object(vapi, "book_appointment", AsyncMock()) as book,
        patch.object(vapi, "save_appointment", AsyncMock()) as save,
    ):
        await vapi.vapi_server(_PAYLOAD)

    book.assert_not_called()
    assert save.call_args.args[0].calendar_provider == "cal_com"


@pytest.mark.asyncio
async def test_webhook_books_when_existing_row_has_no_event():
    """A row exists (e.g. prior DB-only save) but no invite yet → still books."""
    existing = CalendarRef(
        provider=None, event_id=None, event_url=None, end_time=None
    )
    booked = _extracted().model_copy(
        update={"calendar_event_url": "https://cal.com/booking/new"}
    )
    with (
        patch.object(vapi, "load_pack", return_value=_pack()),
        patch.object(vapi, "extract_appointment", AsyncMock(return_value=_extracted())),
        patch.object(vapi, "get_calendar_ref", AsyncMock(return_value=existing)),
        patch.object(vapi, "book_appointment", AsyncMock(return_value=booked)) as book,
        patch.object(vapi, "save_appointment", AsyncMock()),
    ):
        result = await vapi.vapi_server(_PAYLOAD)

    book.assert_awaited_once()
    assert result["calendar_event_url"] == "https://cal.com/booking/new"
