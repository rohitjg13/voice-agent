"""CSV lead import: header aliasing, E.164 normalization, DNC pre-filter,
per-row error report. Dupes (in-file or in-DB) are skipped, not errors."""

import csv
import io
import re
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import structlog

from orchestrator.db import require_pool
from orchestrator.services.compliance import check_dnc

logger = structlog.get_logger()

_PHONE_RE = re.compile(r"^\+[0-9]{8,15}$")

_HEADER_ALIASES = {
    "phone": "phone",
    "phone_number": "phone",
    "phonenumber": "phone",
    "number": "phone",
    "mobile": "phone",
    "name": "name",
    "full_name": "name",
    "contact": "name",
    "company": "company",
    "organization": "company",
    "practice": "company",
    "email": "email",
    "email_address": "email",
}


def normalize_phone(raw: str) -> str | None:
    """→ E.164 or None. ponytail: bare 10-digit numbers default to +1 (US)."""
    cleaned = re.sub(r"[\s\-().]+", "", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        if len(cleaned) == 10:
            cleaned = "+1" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("1"):
            cleaned = "+" + cleaned
        else:
            return None
    return cleaned if _PHONE_RE.match(cleaned) else None


def _field_map(fieldnames: Sequence[str] | None) -> dict[str, str]:
    """{canonical: actual_header} from whatever headers the CSV uses."""
    out: dict[str, str] = {}
    for header in fieldnames or []:
        canonical = _HEADER_ALIASES.get(header.strip().lower().replace(" ", "_"))
        if canonical and canonical not in out:
            out[canonical] = header
    return out


async def import_leads(
    org_id: UUID, campaign_id: UUID, csv_bytes: bytes, max_rows: int = 1000
) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig", errors="replace")))
    fields = _field_map(reader.fieldnames)
    if "phone" not in fields:
        return {"imported": 0, "skipped": [{"row": 1, "reason": "no phone column found"}]}

    pool = require_pool()
    imported = 0
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row_num, row in enumerate(reader, start=2):
        if imported >= max_rows:
            skipped.append({"row": row_num, "reason": "over row limit"})
            continue
        phone = normalize_phone(row.get(fields["phone"]) or "")
        if phone is None:
            skipped.append({"row": row_num, "reason": "invalid phone"})
            continue
        if phone in seen:
            skipped.append({"row": row_num, "reason": "duplicate in file"})
            continue
        seen.add(phone)
        if not await check_dnc(phone):
            skipped.append({"row": row_num, "reason": "do-not-call list"})
            continue

        result: str = await pool.execute(
            """
            INSERT INTO leads (org_id, campaign_id, name, company, email, phone_e164)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (campaign_id, phone_e164) DO NOTHING
            """,
            org_id,
            campaign_id,
            (row.get(fields["name"], "") or "").strip() or None if "name" in fields else None,
            (row.get(fields["company"], "") or "").strip() or None if "company" in fields else None,
            (row.get(fields["email"], "") or "").strip() or None if "email" in fields else None,
            phone,
        )
        if result.endswith(" 0"):
            skipped.append({"row": row_num, "reason": "already in campaign"})
        else:
            imported += 1

    logger.info(
        "leads_imported",
        campaign_id=str(campaign_id),
        imported=imported,
        skipped=len(skipped),
    )
    return {"imported": imported, "skipped": skipped}
