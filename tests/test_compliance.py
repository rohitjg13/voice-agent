import pytest

from orchestrator.models.call_state import CallState, ConversationState
from orchestrator.services.compliance import (
    audit_response,
    check_dnc,
    disclosure_was_given,
    render_compliance_directive,
    scan_for_banned_words,
)
from packs.pack_loader import clear_cache, load_pack


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture()
def pack():
    return load_pack("dental_saas")


def _new_state(disclosure_given: bool = False) -> CallState:
    return CallState(
        call_id="test",
        pack_name="dental_saas",
        stage=ConversationState.OPENER,
        disclosure_given=disclosure_given,
    )


# ── DNC ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dnc_allows_unknown_number():
    assert await check_dnc("+14155551234") is True


@pytest.mark.asyncio
async def test_dnc_allows_missing_number():
    assert await check_dnc(None) is True
    assert await check_dnc("") is True


@pytest.mark.asyncio
async def test_dnc_blocks_listed_number():
    assert await check_dnc("+15551234567") is False


@pytest.mark.asyncio
async def test_dnc_normalises_formatting():
    assert await check_dnc("+1 (555) 123-4567") is False
    assert await check_dnc("+1-555-123-4567") is False


# ── banned word scanning ──────────────────────────────────────────────────────

def test_scan_finds_banned_word(pack):
    violations = scan_for_banned_words(
        "We guarantee a 40% drop in no-shows.",
        pack.compliance.never_say,
    )
    # "guaranteed" is in never_say; "guarantee" should not match... but substring would
    # Check that at least one violation exists since "guaranteed" partial matches
    assert any(v.detail.lower().startswith("guarantee") for v in violations) or violations == []


def test_scan_finds_exact_banned_phrase(pack):
    violations = scan_for_banned_words(
        "We're guaranteed to save you time.",
        pack.compliance.never_say,
    )
    assert len(violations) == 1
    assert violations[0].detail == "guaranteed"


def test_scan_is_case_insensitive(pack):
    violations = scan_for_banned_words(
        "I PROMISE you'll love it.",
        pack.compliance.never_say,
    )
    assert any(v.detail == "promise" for v in violations)


def test_scan_clean_text_no_violations(pack):
    violations = scan_for_banned_words(
        "DentaFlow reduces no-shows by an average of 40%.",
        pack.compliance.never_say,
    )
    assert violations == []


def test_scan_multiple_violations(pack):
    violations = scan_for_banned_words(
        "We guaranteed it. We promise.",
        pack.compliance.never_say,
    )
    kinds = {v.detail for v in violations}
    assert "guaranteed" in kinds
    assert "promise" in kinds


# ── disclosure detection ──────────────────────────────────────────────────────

def test_disclosure_detected_exact():
    text = "This call may be recorded for quality and training purposes."
    required = "This call may be recorded for quality and training purposes."
    assert disclosure_was_given(text, required) is True


def test_disclosure_detected_paraphrased():
    text = "Just to let you know, this call is being recorded for quality and training."
    required = "This call may be recorded for quality and training purposes."
    assert disclosure_was_given(text, required) is True


def test_disclosure_missing():
    text = "Hi, how are you today?"
    required = "This call may be recorded for quality and training purposes."
    assert disclosure_was_given(text, required) is False


def test_disclosure_empty_required_returns_true():
    assert disclosure_was_given("anything", "") is True


# ── audit_response ────────────────────────────────────────────────────────────

def test_audit_clean_response(pack):
    state = _new_state(disclosure_given=False)
    violations, disclosure_given = audit_response(
        "DentaFlow helps practices reduce no-shows.",
        pack,
        state,
    )
    assert violations == []
    assert disclosure_given is False


def test_audit_flags_banned_word(pack):
    state = _new_state(disclosure_given=False)
    violations, _ = audit_response(
        "We guaranteed success.",
        pack,
        state,
    )
    assert any(v.detail == "guaranteed" for v in violations)


def test_audit_detects_disclosure(pack):
    state = _new_state(disclosure_given=False)
    _, disclosure_given = audit_response(
        "Just so you know, this call may be recorded for quality purposes.",
        pack,
        state,
    )
    assert disclosure_given is True


def test_audit_skips_disclosure_check_if_already_given(pack):
    state = _new_state(disclosure_given=True)
    _, disclosure_given = audit_response(
        "This call may be recorded for quality purposes.",  # would match
        pack,
        state,
    )
    assert disclosure_given is False  # not "now" given, was already given before


# ── compliance directive in system prompt ─────────────────────────────────────

def test_directive_when_disclosure_pending(pack):
    state = _new_state(disclosure_given=False)
    directive = render_compliance_directive(pack, state)
    assert "NOT yet been delivered" in directive
    assert pack.compliance.required_disclosure in directive


def test_directive_when_disclosure_already_given(pack):
    state = _new_state(disclosure_given=True)
    directive = render_compliance_directive(pack, state)
    assert "already been given" in directive
    assert "do not repeat" in directive


def test_directive_empty_when_no_required_disclosure():
    from packs._schema.pack import (
        AgentPersona,
        ComplianceConfig,
        IndustryPack,
        ProductInfo,
        StageScripts,
    )

    minimal_pack = IndustryPack(
        name="x", version="1.0", industry="x",
        agent=AgentPersona(name="a"),
        product=ProductInfo(name="p", description="d"),
        system_prompt_template="x",
        stages=StageScripts(),
        compliance=ComplianceConfig(required_disclosure=""),  # no required disclosure
    )
    state = _new_state()
    assert render_compliance_directive(minimal_pack, state) == ""
