"""Extract structured appointment data from a finished call transcript."""

import json
import re

import anthropic
import structlog

from orchestrator.config import settings
from orchestrator.models.appointment import Appointment

logger = structlog.get_logger()


_SPEECH_TO_EMAIL_REPLACEMENTS = [
    (r"\s+at\s+the\s+rate\s+(?:of\s+)?", "@"),
    (r"\s+at\s+(?=\S)", "@"),
    (r"\s+@\s+", "@"),
    (r"\s+dot\s+", "."),
    (r"\s+period\s+", "."),
    (r"\s+underscore\s+", "_"),
    (r"\s+under\s+score\s+", "_"),
    (r"\s+(?:dash|hyphen|minus)\s+", "-"),
    (r"\s+plus\s+", "+"),
]

_EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def sanitize_email(raw: str | None) -> str | None:
    """Normalise spoken-style emails. Returns None when the result isn't a plausible address."""
    if not raw:
        return None
    s = raw.strip().lower()

    for pattern, repl in _SPEECH_TO_EMAIL_REPLACEMENTS:
        s = re.sub(pattern, repl, s)

    # Remove any remaining whitespace
    s = re.sub(r"\s+", "", s)
    # Strip trailing punctuation the LLM might include
    s = s.rstrip(".,;:!?")

    return s if _EMAIL_RE.match(s) else None


_PROMPT = """\
Analyze this cold-call transcript and extract booking info.

Return ONLY a JSON object (no markdown fences, no commentary) with exactly these fields:
  - booked: true if the prospect explicitly agreed to a meeting/demo/call, false otherwise
  - prospect_name: the name the prospect explicitly stated (NOT inferred from the email), else null
  - prospect_email: email address if given, normalised from speech artifacts, else null
  - requested_time: the agreed time as raw text (e.g. "Monday May 25 at 10 AM"), else null
  - summary: one short sentence describing the outcome

Email normalisation rules — the transcript is from speech-to-text, so emails arrive spoken aloud:
  "rohit at gmail dot com"      → "rohit@gmail.com"
  "j dot smith at acme dot io"  → "j.smith@acme.io"
  "rohit jg at gmail dot com"   → "rohitjg@gmail.com"
  "sam underscore lee at x.com" → "sam_lee@x.com"
Strip ALL whitespace from the final email. Lowercase it.

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

    # LLM should already normalise, but sanitise as a backstop.
    raw_email = data.get("prospect_email")
    clean_email = sanitize_email(raw_email) if raw_email else None
    if raw_email and not clean_email:
        logger.warning("appointment_email_unparseable", raw=raw_email, call_id=call_id)

    return base.model_copy(update={
        "booked": bool(data.get("booked", False)),
        "prospect_name": data.get("prospect_name"),
        "prospect_email": clean_email,
        "requested_time": data.get("requested_time"),
        "summary": data.get("summary"),
    })
