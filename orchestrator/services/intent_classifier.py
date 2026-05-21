"""
Classifies the prospect's last utterance into an Intent + objection_id.
Uses a single Claude Haiku call with a structured output format.
"""

import structlog

import anthropic
from orchestrator.config import settings
from orchestrator.models.call_state import Intent
from packs._schema.pack import IndustryPack

logger = structlog.get_logger()

_FALLBACK = (Intent.NEUTRAL, "none")

_PROMPT_TEMPLATE = """\
You are classifying a prospect's response during a cold sales call.

Return EXACTLY this format (one line, no explanation):
<intent>:<objection_id>

intent must be one of:
  interested      - shows curiosity, asks positive questions, wants to learn more
  not_interested  - declines, says not interested, wants to hang up
  objection       - raises a concern, challenge, or obstacle
  agree           - agrees to meet, schedule, or move forward
  question        - asks a neutral question about the product or company
  goodbye         - actively tries to end the call
  neutral         - anything else / unclear

objection_id (only when intent is "objection", otherwise use "none"):
{objection_ids}

Examples:
  "We're happy with what we have"        -> objection:already_have_software
  "How much does it cost?"               -> objection:too_expensive
  "That sounds interesting, tell me more"-> interested:none
  "Sure, let's schedule a call"          -> agree:none
  "I'm in a meeting, call me back"       -> objection:call_back_later
  "What does your software do?"          -> question:none
  "Not interested, thanks"               -> not_interested:none
  "OK"                                   -> neutral:none

Prospect said: "{message}"
"""


def _build_prompt(message: str, pack: IndustryPack) -> str:
    objection_lines = "\n".join(
        f"  {o.id:<28} - {o.label}" for o in pack.objections
    )
    objection_lines += "\n  other                        - objection that doesn't fit above"
    return _PROMPT_TEMPLATE.format(objection_ids=objection_lines, message=message)


def _parse_classification(raw: str, valid_objection_ids: set[str]) -> tuple[Intent, str]:
    """Parse 'intent:objection_id' from LLM output. Falls back to NEUTRAL on any error."""
    raw = raw.strip().lower()
    parts = raw.split(":", 1)
    if len(parts) != 2:
        logger.warning("classifier_bad_format", raw=raw)
        return _FALLBACK

    intent_str, objection_id = parts[0].strip(), parts[1].strip()

    try:
        intent = Intent(intent_str)
    except ValueError:
        logger.warning("classifier_unknown_intent", raw=raw)
        return _FALLBACK

    # Normalise unknown objection IDs to "generic"
    if intent == Intent.OBJECTION and objection_id not in valid_objection_ids:
        objection_id = "generic"

    return intent, objection_id


async def classify_intent(
    message: str,
    pack: IndustryPack,
) -> tuple[Intent, str]:
    """Return (Intent, objection_id). objection_id is 'none' when intent != OBJECTION."""
    if not settings.anthropic_api_key:
        return _FALLBACK

    valid_ids = {o.id for o in pack.objections} | {"other", "generic", "none"}

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.classifier_model,
            max_tokens=20,
            messages=[{"role": "user", "content": _build_prompt(message, pack)}],
        )
        raw = response.content[0].text  # type: ignore[union-attr]
        result = _parse_classification(raw, valid_ids)
        logger.info("intent_classified", message=message[:60], intent=result[0], objection_id=result[1])
        return result
    except Exception as exc:
        logger.warning("classifier_error", error=str(exc))
        return _FALLBACK
