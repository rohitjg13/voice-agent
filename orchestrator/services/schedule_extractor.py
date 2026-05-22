"""
After each user turn in SCHEDULE, extract whether they just provided their
email and/or name. One Haiku call. Returns {"email": str|None, "name": str|None}.
"""

import json

import anthropic
import structlog

from orchestrator.config import settings
from orchestrator.services.appointment_extractor import sanitize_email

logger = structlog.get_logger()


_PROMPT = """\
The user said: "{message}"

Did they explicitly state an EMAIL ADDRESS or a NAME (their own first/last name)?

Return ONLY this JSON (no markdown):
{{"email": "<email or null>", "name": "<name or null>"}}

Rules:
  - Email: handle speech artifacts ("at" -> @, "dot" -> .). Lowercase, no spaces. null if no email.
  - Name: ONLY if they said their name explicitly (e.g. "I'm Sarah", "Sarah Johnson", "this is Mike").
    Do NOT infer names from email usernames. Do NOT use titles like "doctor" or "mister" alone.
    null if no name.
"""


async def extract_schedule_info(message: str) -> dict[str, str | None]:
    result: dict[str, str | None] = {"email": None, "name": None}
    if not settings.anthropic_api_key or not message:
        return result

    try:
        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            max_retries=2,
        )
        response = await client.messages.create(
            model=settings.classifier_model,
            max_tokens=80,
            messages=[{"role": "user", "content": _PROMPT.format(message=message)}],
        )
        raw = response.content[0].text.strip()  # type: ignore[union-attr]
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]).strip()
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("schedule_extract_failed", error=str(exc))
        return result

    email_raw = data.get("email")
    if isinstance(email_raw, str) and email_raw.lower() != "null":
        result["email"] = sanitize_email(email_raw)

    name_raw = data.get("name")
    if isinstance(name_raw, str) and name_raw.lower() != "null" and name_raw.strip():
        result["name"] = name_raw.strip()

    return result
