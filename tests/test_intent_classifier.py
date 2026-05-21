from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.models.call_state import Intent
from orchestrator.services.intent_classifier import _parse_classification, classify_intent
from packs.pack_loader import clear_cache, load_pack

# ── valid objection IDs from the dental pack ──────────────────────────────────
_VALID_IDS = {
    "not_interested", "already_have_software", "too_expensive",
    "call_back_later", "gatekeeper", "other", "generic", "none",
}


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


# ── _parse_classification (pure, no I/O) ─────────────────────────────────────

def test_parse_interested():
    assert _parse_classification("interested:none", _VALID_IDS) == (Intent.INTERESTED, "none")


def test_parse_objection_known_id():
    assert _parse_classification("objection:too_expensive", _VALID_IDS) == (Intent.OBJECTION, "too_expensive")


def test_parse_objection_unknown_id_normalises_to_generic():
    result = _parse_classification("objection:totally_made_up", _VALID_IDS)
    assert result == (Intent.OBJECTION, "generic")


def test_parse_not_interested():
    assert _parse_classification("not_interested:none", _VALID_IDS) == (Intent.NOT_INTERESTED, "none")


def test_parse_agree():
    assert _parse_classification("agree:none", _VALID_IDS) == (Intent.AGREE, "none")


def test_parse_whitespace_and_case_tolerant():
    assert _parse_classification("  NEUTRAL:none  ", _VALID_IDS) == (Intent.NEUTRAL, "none")


def test_parse_missing_colon_falls_back():
    assert _parse_classification("interested", _VALID_IDS) == (Intent.NEUTRAL, "none")


def test_parse_unknown_intent_falls_back():
    assert _parse_classification("confused:none", _VALID_IDS) == (Intent.NEUTRAL, "none")


def test_parse_empty_string_falls_back():
    assert _parse_classification("", _VALID_IDS) == (Intent.NEUTRAL, "none")


# ── classify_intent (mocked LLM) ─────────────────────────────────────────────

def _mock_response(text: str) -> MagicMock:
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


@pytest.mark.asyncio
async def test_classify_happy_path():
    pack = load_pack("dental_saas")
    with patch("orchestrator.services.intent_classifier.anthropic.AsyncAnthropic") as mock_cls:
        instance = mock_cls.return_value
        instance.messages.create = AsyncMock(return_value=_mock_response("objection:too_expensive"))

        intent, obj_id = await classify_intent("How much does it cost?", pack)

    assert intent == Intent.OBJECTION
    assert obj_id == "too_expensive"


@pytest.mark.asyncio
async def test_classify_interested():
    pack = load_pack("dental_saas")
    with patch("orchestrator.services.intent_classifier.anthropic.AsyncAnthropic") as mock_cls:
        instance = mock_cls.return_value
        instance.messages.create = AsyncMock(return_value=_mock_response("interested:none"))

        intent, obj_id = await classify_intent("That sounds great!", pack)

    assert intent == Intent.INTERESTED
    assert obj_id == "none"


@pytest.mark.asyncio
async def test_classify_api_error_falls_back_to_neutral():
    pack = load_pack("dental_saas")
    with patch("orchestrator.services.intent_classifier.anthropic.AsyncAnthropic") as mock_cls:
        instance = mock_cls.return_value
        instance.messages.create = AsyncMock(side_effect=Exception("network error"))

        intent, obj_id = await classify_intent("whatever", pack)

    assert intent == Intent.NEUTRAL
    assert obj_id == "none"


@pytest.mark.asyncio
async def test_classify_malformed_response_falls_back():
    pack = load_pack("dental_saas")
    with patch("orchestrator.services.intent_classifier.anthropic.AsyncAnthropic") as mock_cls:
        instance = mock_cls.return_value
        instance.messages.create = AsyncMock(return_value=_mock_response("I'm not sure what this means"))

        intent, obj_id = await classify_intent("huh", pack)

    assert intent == Intent.NEUTRAL


@pytest.mark.asyncio
async def test_classify_no_api_key_falls_back(monkeypatch: pytest.MonkeyPatch):
    pack = load_pack("dental_saas")
    monkeypatch.setattr("orchestrator.services.intent_classifier.settings.anthropic_api_key", "")
    intent, obj_id = await classify_intent("hello", pack)
    assert intent == Intent.NEUTRAL
    assert obj_id == "none"


@pytest.mark.asyncio
async def test_classify_gatekeeper_objection():
    pack = load_pack("dental_saas")
    with patch("orchestrator.services.intent_classifier.anthropic.AsyncAnthropic") as mock_cls:
        instance = mock_cls.return_value
        instance.messages.create = AsyncMock(return_value=_mock_response("objection:gatekeeper"))

        intent, obj_id = await classify_intent("You need to talk to the doctor", pack)

    assert intent == Intent.OBJECTION
    assert obj_id == "gatekeeper"
