from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.services.appointment_extractor import (
    _parse_start_iso,
    _strip_fences,
    extract_appointment,
    sanitize_email,
)

# ── _parse_start_iso (pure) ──────────────────────────────────────────────────

def test_parse_start_iso_with_offset():
    dt = _parse_start_iso("2026-07-09T14:00:00+05:30", "UTC")
    assert dt is not None and dt.utcoffset().total_seconds() == 5.5 * 3600


def test_parse_start_iso_z_suffix():
    dt = _parse_start_iso("2026-07-09T14:00:00Z", "Asia/Kolkata")
    assert dt is not None and dt.utcoffset().total_seconds() == 0


def test_parse_start_iso_naive_gets_pack_tz():
    dt = _parse_start_iso("2026-07-09T14:00:00", "Asia/Kolkata")
    assert dt is not None and dt.utcoffset().total_seconds() == 5.5 * 3600


@pytest.mark.parametrize("raw", [None, "", "null", "not a date", 123])
def test_parse_start_iso_invalid(raw):
    assert _parse_start_iso(raw, "UTC") is None

# ── sanitize_email (pure) ────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("rohit@gmail.com", "rohit@gmail.com"),
    ("Rohit@Gmail.com", "rohit@gmail.com"),
    ("rohit at gmail dot com", "rohit@gmail.com"),
    ("rohit AT gmail DOT com", "rohit@gmail.com"),
    ("j dot smith at acme dot io", "j.smith@acme.io"),
    ("sam underscore lee at x.com", "sam_lee@x.com"),
    ("first dash last at company dot co", "first-last@company.co"),
    ("  rohit  at  gmail  dot  com  ", "rohit@gmail.com"),
    ("rohit@gmail.com.", "rohit@gmail.com"),
    ("rohit@gmail.com,", "rohit@gmail.com"),
])
def test_sanitize_email_valid(raw, expected):
    assert sanitize_email(raw) == expected


@pytest.mark.parametrize("raw", [
    None,
    "",
    "   ",
    "not an email",
    "missing@tld",
    "@gmail.com",
    "rohit@",
])
def test_sanitize_email_invalid(raw):
    assert sanitize_email(raw) is None

# ── _strip_fences (pure) ─────────────────────────────────────────────────────

def test_strip_no_fences():
    assert _strip_fences('{"booked": true}') == '{"booked": true}'


def test_strip_json_fence():
    raw = '```json\n{"booked": true}\n```'
    assert _strip_fences(raw) == '{"booked": true}'


def test_strip_plain_fence():
    raw = '```\n{"booked": false}\n```'
    assert _strip_fences(raw) == '{"booked": false}'


def test_strip_leading_whitespace():
    raw = '   ```json\n{"x":1}\n```   '
    assert _strip_fences(raw) == '{"x":1}'


# ── extract_appointment (mocked LLM) ─────────────────────────────────────────


def _mock_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


@pytest.fixture(autouse=True)
def _stub_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "orchestrator.services.appointment_extractor.settings.anthropic_api_key",
        "sk-test",
    )


@pytest.mark.asyncio
async def test_extract_booked():
    messages = [
        {"role": "assistant", "content": "Would Thursday at 2pm work?"},
        {"role": "user", "content": "Yes, that's perfect. My email is jane@dental.com"},
        {"role": "assistant", "content": "Great, I'll send the invite."},
    ]
    extraction = (
        '{"booked": true, "prospect_name": "Jane", '
        '"prospect_email": "jane@dental.com", '
        '"requested_time": "Thursday at 2pm", '
        '"summary": "Demo booked for Thursday 2pm"}'
    )
    with patch("orchestrator.services.appointment_extractor.anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=_mock_response(extraction))
        appt = await extract_appointment("call-123", "dental_saas", messages)

    assert appt.booked is True
    assert appt.prospect_email == "jane@dental.com"
    assert appt.requested_time == "Thursday at 2pm"
    assert appt.call_id == "call-123"
    assert appt.transcript and "jane@dental.com" in appt.transcript


@pytest.mark.asyncio
async def test_extract_parses_start_iso():
    messages = [{"role": "user", "content": "Thursday at 2pm works, jane@dental.com"}]
    extraction = (
        '{"booked": true, "prospect_email": "jane@dental.com", '
        '"requested_time": "Thursday at 2pm", '
        '"start_iso": "2026-07-09T14:00:00+05:30", '
        '"summary": "Booked"}'
    )
    with patch("orchestrator.services.appointment_extractor.anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=_mock_response(extraction))
        appt = await extract_appointment(
            "call-iso", "dental_saas", messages, timezone="Asia/Kolkata"
        )

    assert appt.start_time is not None
    assert appt.start_time.hour == 14
    assert appt.start_time.utcoffset().total_seconds() == 5.5 * 3600


@pytest.mark.asyncio
async def test_extract_missing_start_iso_leaves_none():
    messages = [{"role": "user", "content": "Sure, sometime works"}]
    extraction = '{"booked": true, "requested_time": "sometime"}'
    with patch("orchestrator.services.appointment_extractor.anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=_mock_response(extraction))
        appt = await extract_appointment("call-noiso", "dental_saas", messages)

    assert appt.start_time is None


@pytest.mark.asyncio
async def test_extract_not_booked():
    messages = [
        {"role": "assistant", "content": "Could I schedule a demo?"},
        {"role": "user", "content": "No thanks, not interested."},
    ]
    extraction = '{"booked": false, "summary": "Prospect declined"}'
    with patch("orchestrator.services.appointment_extractor.anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=_mock_response(extraction))
        appt = await extract_appointment("call-456", "dental_saas", messages)

    assert appt.booked is False
    assert appt.prospect_email is None


@pytest.mark.asyncio
async def test_extract_handles_fenced_response():
    messages = [{"role": "user", "content": "Sure, Thursday works."}]
    extraction = '```json\n{"booked": true}\n```'
    with patch("orchestrator.services.appointment_extractor.anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=_mock_response(extraction))
        appt = await extract_appointment("call-789", "dental_saas", messages)

    assert appt.booked is True


@pytest.mark.asyncio
async def test_extract_handles_malformed_json():
    messages = [{"role": "user", "content": "Yes."}]
    with patch("orchestrator.services.appointment_extractor.anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=_mock_response("not json"))
        appt = await extract_appointment("call-bad", "dental_saas", messages)

    assert appt.booked is False  # safe default
    assert appt.transcript  # transcript still captured


@pytest.mark.asyncio
async def test_extract_empty_messages_returns_base(monkeypatch):
    appt = await extract_appointment("call-empty", "dental_saas", [])
    assert appt.booked is False
    assert appt.transcript == ""


@pytest.mark.asyncio
async def test_extract_no_api_key_returns_base(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.services.appointment_extractor.settings.anthropic_api_key",
        "",
    )
    messages = [{"role": "user", "content": "Yes."}]
    appt = await extract_appointment("call-x", "dental_saas", messages)
    assert appt.booked is False
    assert appt.transcript and "Yes." in appt.transcript
