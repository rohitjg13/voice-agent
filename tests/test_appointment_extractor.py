from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.services.appointment_extractor import (
    _strip_fences,
    extract_appointment,
)

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
