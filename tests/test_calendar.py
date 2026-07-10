from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from orchestrator.models.appointment import Appointment
from orchestrator.services import calendar as cal
from packs._schema.pack import CalendarConfig, IndustryPack

TZ = ZoneInfo("Asia/Kolkata")
# Relative to wall-clock so the past-time guard doesn't silently flip these
# tests as the calendar advances. START is comfortably in the future.
START = (datetime.now(TZ) + timedelta(days=2)).replace(microsecond=0)


def _pack(provider: str, **cal_kwargs) -> IndustryPack:
    return IndustryPack(
        name="dental_saas",
        version="1.0",
        industry="dental",
        agent={"name": "Alex"},
        product={"name": "DentaFlow", "description": "PMS"},
        system_prompt_template="hi",
        stages={},
        scheduling={"timezone": "Asia/Kolkata"},
        calendar=CalendarConfig(provider=provider, **cal_kwargs),
    )


def _appt(**overrides) -> Appointment:
    base = dict(
        call_id="call-1",
        pack_name="dental_saas",
        booked=True,
        prospect_name="Jane",
        prospect_email="jane@dental.com",
        start_time=START,
    )
    base.update(overrides)
    return Appointment(**base)


def _http_response(status: int, payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.text = "err"
    return resp


def _mock_client(resp: MagicMock) -> MagicMock:
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    return client


# ── no-op guards ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,appt_kwargs", [
    ("none", {}),                          # provider disabled
    ("cal_com", {"booked": False}),        # didn't book
    ("cal_com", {"start_time": None}),     # no resolved time
    ("cal_com", {"prospect_email": None}), # no email to invite
])
async def test_book_creates_no_invite(provider, appt_kwargs):
    pack = _pack(provider, event_type_id=1)
    appt = _appt(**appt_kwargs)
    out = await cal.book_appointment(pack, appt)
    assert out.calendar_event_id is None
    assert out.calendar_provider is None
    assert out.calendar_event_url is None


# ── end_time is filled even when no invite is created ────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,appt_kwargs", [
    ("none", {}),                          # DB-only pack
    ("cal_com", {"prospect_email": None}), # invite skipped, slot still known
])
async def test_end_time_derived_without_invite(provider, appt_kwargs):
    pack = _pack(provider, event_type_id=1, duration_minutes=45)
    out = await cal.book_appointment(pack, _appt(**appt_kwargs))
    assert out.end_time == START + timedelta(minutes=45)
    assert out.calendar_event_id is None


@pytest.mark.asyncio
async def test_no_end_time_without_start():
    pack = _pack("cal_com", event_type_id=1)
    out = await cal.book_appointment(pack, _appt(start_time=None))
    assert out.end_time is None


@pytest.mark.asyncio
async def test_past_start_time_creates_no_invite(monkeypatch):
    """A resolved time in the past must not create a real event (Google would)."""
    monkeypatch.setattr(cal.settings, "calcom_api_key", "cal_live_x")
    past = datetime.now(TZ) - timedelta(days=1)
    pack = _pack("cal_com", event_type_id=42, duration_minutes=30)
    client = _mock_client(_http_response(200, {"id": 1, "uid": "x"}))
    with patch.object(cal, "shared_async_http_client", return_value=client):
        out = await cal.book_appointment(pack, _appt(start_time=past))
    client.post.assert_not_called()
    assert out.calendar_event_id is None
    # The slot window is still recorded even though no invite was sent.
    assert out.end_time == past + timedelta(minutes=30)


# ── Cal.com ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calcom_success(monkeypatch):
    monkeypatch.setattr(cal.settings, "calcom_api_key", "cal_live_x")
    pack = _pack("cal_com", event_type_id=42, duration_minutes=15)
    resp = _http_response(200, {"id": 999, "uid": "abc123"})
    client = _mock_client(resp)

    with patch.object(cal, "shared_async_http_client", return_value=client):
        out = await cal.book_appointment(pack, _appt())

    assert out.calendar_provider == "cal_com"
    assert out.calendar_event_id == "999"
    assert out.calendar_event_url == "https://cal.com/booking/abc123"
    assert out.end_time == START + timedelta(minutes=15)

    body = client.post.call_args.kwargs["json"]
    assert body["eventTypeId"] == 42
    assert body["responses"]["email"] == "jane@dental.com"
    assert body["timeZone"] == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_calcom_wrapped_booking(monkeypatch):
    monkeypatch.setattr(cal.settings, "calcom_api_key", "cal_live_x")
    pack = _pack("cal_com", event_type_id=42)
    resp = _http_response(201, {"booking": {"id": 7, "uid": "wrapped"}})
    with patch.object(cal, "shared_async_http_client", return_value=_mock_client(resp)):
        out = await cal.book_appointment(pack, _appt())
    assert out.calendar_event_id == "7"
    assert out.calendar_event_url == "https://cal.com/booking/wrapped"


@pytest.mark.asyncio
async def test_calcom_2xx_without_id_still_records_provider(monkeypatch):
    """A 2xx booking with an unparseable body: we can't capture an id, but the
    invite was created — record the provider so a redelivery won't double-book.
    """
    monkeypatch.setattr(cal.settings, "calcom_api_key", "cal_live_x")
    pack = _pack("cal_com", event_type_id=42)
    resp = _http_response(200, {})  # no id, no uid
    with patch.object(cal, "shared_async_http_client", return_value=_mock_client(resp)):
        out = await cal.book_appointment(pack, _appt())
    assert out.calendar_provider == "cal_com"
    assert out.calendar_event_id == ""
    assert out.calendar_event_url is None


@pytest.mark.asyncio
async def test_calcom_rejected_keeps_appointment(monkeypatch):
    monkeypatch.setattr(cal.settings, "calcom_api_key", "cal_live_x")
    pack = _pack("cal_com", event_type_id=42)
    resp = _http_response(400, {})
    with patch.object(cal, "shared_async_http_client", return_value=_mock_client(resp)):
        out = await cal.book_appointment(pack, _appt())
    assert out.calendar_event_id is None
    assert out.calendar_provider is None


@pytest.mark.asyncio
async def test_calcom_missing_api_key_skips(monkeypatch):
    monkeypatch.setattr(cal.settings, "calcom_api_key", "")
    pack = _pack("cal_com", event_type_id=42)
    client = _mock_client(_http_response(200, {}))
    with patch.object(cal, "shared_async_http_client", return_value=client):
        out = await cal.book_appointment(pack, _appt())
    assert out.calendar_event_id is None
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_calcom_missing_event_type_skips(monkeypatch):
    monkeypatch.setattr(cal.settings, "calcom_api_key", "cal_live_x")
    pack = _pack("cal_com")  # no event_type_id
    client = _mock_client(_http_response(200, {}))
    with patch.object(cal, "shared_async_http_client", return_value=client):
        out = await cal.book_appointment(pack, _appt())
    assert out.calendar_event_id is None
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_provider_exception_swallowed(monkeypatch):
    monkeypatch.setattr(cal.settings, "calcom_api_key", "cal_live_x")
    pack = _pack("cal_com", event_type_id=42)
    client = MagicMock()
    client.post = AsyncMock(side_effect=RuntimeError("network down"))
    with patch.object(cal, "shared_async_http_client", return_value=client):
        out = await cal.book_appointment(pack, _appt())
    assert out.calendar_event_id is None  # error swallowed, row still savable


# ── Google Calendar ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_success(monkeypatch):
    monkeypatch.setattr(cal.settings, "google_calendar_credentials_json", '{"x": 1}')
    pack = _pack("google", calendar_id="ops@clinic.com", duration_minutes=30)
    resp = _http_response(200, {"id": "evt_1", "htmlLink": "https://cal.google/evt_1"})
    client = _mock_client(resp)

    with (
        patch.object(cal, "shared_async_http_client", return_value=client),
        patch.object(cal, "_google_access_token", AsyncMock(return_value="tok")),
    ):
        out = await cal.book_appointment(pack, _appt())

    assert out.calendar_provider == "google"
    assert out.calendar_event_id == "evt_1"
    assert out.calendar_event_url == "https://cal.google/evt_1"
    assert out.end_time == START + timedelta(minutes=30)

    assert client.post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"
    body = client.post.call_args.kwargs["json"]
    assert body["attendees"] == [{"email": "jane@dental.com"}]
    assert body["start"]["timeZone"] == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_google_missing_credentials_skips(monkeypatch):
    monkeypatch.setattr(cal.settings, "google_calendar_credentials_json", "")
    pack = _pack("google", calendar_id="ops@clinic.com")
    with patch.object(cal, "_google_access_token", AsyncMock(return_value="tok")) as tok:
        out = await cal.book_appointment(pack, _appt())
    assert out.calendar_event_id is None
    tok.assert_not_called()


@pytest.mark.asyncio
async def test_google_token_failure_keeps_appointment(monkeypatch):
    monkeypatch.setattr(cal.settings, "google_calendar_credentials_json", '{"x": 1}')
    pack = _pack("google", calendar_id="ops@clinic.com")
    with patch.object(cal, "_google_access_token", AsyncMock(return_value=None)):
        out = await cal.book_appointment(pack, _appt())
    assert out.calendar_event_id is None
