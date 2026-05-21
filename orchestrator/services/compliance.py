"""
Compliance subsystem:
  - Pre-call DNC (do-not-call) check
  - Post-response audit for banned words
  - Required disclosure detection
"""

import re

import structlog

from orchestrator.models.call_state import CallState
from orchestrator.models.compliance import ComplianceViolation
from packs._schema.pack import IndustryPack

logger = structlog.get_logger()

# Placeholder DNC blocklist — in production this would hit FTC DNC Registry or our own table
_DNC_TEST_BLOCKLIST: set[str] = {"+15551234567", "555-DNC-CALL"}


def _normalise_phone(phone: str) -> str:
    """Strip spaces/dashes/parens for blocklist comparison."""
    return re.sub(r"[\s\-().]+", "", phone)


async def check_dnc(phone_number: str | None) -> bool:
    """Return True if the call is allowed. False = on do-not-call list."""
    if not phone_number:
        return True  # no number = direct API test, allow

    normalised = _normalise_phone(phone_number)
    if phone_number in _DNC_TEST_BLOCKLIST or normalised in {
        _normalise_phone(p) for p in _DNC_TEST_BLOCKLIST
    }:
        logger.warning("dnc_blocked", phone=phone_number)
        return False
    return True


def scan_for_banned_words(text: str, never_say: list[str]) -> list[ComplianceViolation]:
    """Find every banned phrase in the text (case-insensitive, whole substring)."""
    violations: list[ComplianceViolation] = []
    text_lower = text.lower()
    for phrase in never_say:
        if phrase.lower() in text_lower:
            violations.append(ComplianceViolation(kind="banned_word", detail=phrase))
    return violations


def disclosure_was_given(text: str, required: str, threshold: float = 0.6) -> bool:
    """Heuristic match — disclosure phrasing varies but key words should be present."""
    if not required:
        return True
    required_words = {w for w in re.findall(r"\w+", required.lower()) if len(w) > 3}
    text_words = set(re.findall(r"\w+", text.lower()))
    if not required_words:
        return True
    overlap = required_words & text_words
    return len(overlap) / len(required_words) >= threshold


def audit_response(
    text: str,
    pack: IndustryPack,
    call_state: CallState,
) -> tuple[list[ComplianceViolation], bool]:
    """Return (violations, disclosure_now_given_in_this_response)."""
    violations = scan_for_banned_words(text, pack.compliance.never_say)
    disclosure_given_now = False
    if not call_state.disclosure_given and pack.compliance.required_disclosure:
        disclosure_given_now = disclosure_was_given(text, pack.compliance.required_disclosure)
    return violations, disclosure_given_now


def render_compliance_directive(pack: IndustryPack, call_state: CallState) -> str:
    """One-line directive appended to the system prompt to keep disclosure state honest."""
    if not pack.compliance.required_disclosure:
        return ""
    if call_state.disclosure_given:
        return "[COMPLIANCE: Required disclosure has already been given — do not repeat it.]"
    return (
        "[COMPLIANCE: Required disclosure has NOT yet been delivered. "
        f"Include this phrase early in the conversation: \"{pack.compliance.required_disclosure}\"]"
    )
