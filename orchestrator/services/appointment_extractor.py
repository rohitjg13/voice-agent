"""Extract structured appointment data from a finished call transcript."""

import json

import anthropic
import structlog

from orchestrator.config import settings
from orchestrator.models.appointment import Appointment

logger = structlog.get_logger()


_PROMPT = """\
Analyze this cold-call transcript and extract booking info.

Return ONLY a JSON object (no markdown fences, no commentary) with exactly these fields:
  - booked: true if the prospect explicitly agreed to a meeting/demo/call, false otherwise
  - prospect_name: the prospect's name if stated, else null
  - prospect_email: email address if given, else null
  - requested_time: the agreed time as raw text (e.g. "Thursday at 2pm"), else null
  - summary: one short sentence describing the outcome

Transcript:
{transcript}
"""


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        # ```json\n...\n``` or ```\n...\n```
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw


async def extract_appointment(
    call_id: str,
    pack_name: str,
    messages: list[dict[str, str]],
) -> Appointment:
    transcript = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

    base = Appointment(call_id=call_id, pack_name=pack_name, transcript=transcript)

    if not settings.anthropic_api_key or not messages:
        return base

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=3)
        response = await client.messages.create(
            model=settings.classifier_model,
            max_tokens=300,
            messages=[{"role": "user", "content": _PROMPT.format(transcript=transcript)}],
        )
        raw = _strip_fences(response.content[0].text)  # type: ignore[union-attr]
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("appointment_extract_failed", error=str(exc), call_id=call_id)
        return base

    return base.model_copy(update={
        "booked": bool(data.get("booked", False)),
        "prospect_name": data.get("prospect_name"),
        "prospect_email": data.get("prospect_email"),
        "requested_time": data.get("requested_time"),
        "summary": data.get("summary"),
    })
