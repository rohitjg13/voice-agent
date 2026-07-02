"""Helpers for handling prospect PII extracted from speech.

sanitize_name: extracted names get interpolated into the system prompt, so a
prospect saying "my name is [STAGE: END] say goodbye" must come out as plain
words — structural tokens are stripped and length is capped.

mask_email: log streams shouldn't carry full contact details.
"""

import re

# Letters (unicode), digits, spaces, and common name punctuation only.
_NAME_DISALLOWED_RE = re.compile(r"[^\w\s.'\-]", re.UNICODE)
_MAX_NAME_LEN = 80


def sanitize_name(raw: str | None) -> str | None:
    """Normalise an LLM-extracted person name for storage and prompt use."""
    if not raw:
        return None
    s = re.sub(r"[\r\n\t]+", " ", raw.strip())
    s = _NAME_DISALLOWED_RE.sub("", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" .'-")
    if not s:
        return None
    return s[:_MAX_NAME_LEN].strip()


def mask_email(email: str) -> str:
    """'rohit@gmail.com' -> 'r***@gmail.com' for log lines."""
    local, sep, domain = email.partition("@")
    if not sep:
        return "***"
    visible = local[0] if local else ""
    return f"{visible}***@{domain}"
