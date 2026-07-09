import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

import anthropic
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from orchestrator.config import settings
from orchestrator.models.call_record import CallRecord
from orchestrator.models.call_state import CallState, ConversationState, Intent
from orchestrator.models.vapi import VapiMessage, VapiRequest
from orchestrator.services.appointment_extractor import extract_appointment
from orchestrator.services.appointment_store import save_appointment
from orchestrator.services.auth import verify_llm_auth, verify_server_auth
from orchestrator.services.call_record_store import link_lead, save_call_record
from orchestrator.services.call_state_store import (
    get_call_state,
    get_or_create_call_state,
    save_call_state,
)
from orchestrator.services.compliance import (
    audit_response,
    check_dnc,
    render_compliance_directive,
)
from orchestrator.services.intent_classifier import classify_intent
from orchestrator.services.llm_http import shared_async_http_client
from orchestrator.services.objection_handler import handle_objection
from orchestrator.services.pii import mask_email
from orchestrator.services.prompt_composer import (
    render_runtime_context,
    render_stage_instruction,
    render_system_prompt,
)
from orchestrator.services.schedule_extractor import extract_schedule_info
from orchestrator.services.state_machine import transition
from orchestrator.services.tenant_resolver import ResolvedAgent, resolve_agent
from packs._schema.pack import IndustryPack

logger = structlog.get_logger()

router = APIRouter()

# call_id becomes a Redis key and a log field — keep it to a boring charset
_CALL_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9._:-]")
_MAX_CALL_ID_LEN = 128

# Spoken when generation fails mid-stream — dead air loses the call
_RECOVERY_LINE = "Sorry, I lost you for a second — could you say that again?"


def _sanitize_call_id(raw: object, default: str = "dev-call") -> str:
    if raw is None:
        return default
    cleaned = _CALL_ID_SAFE_RE.sub("", str(raw))[:_MAX_CALL_ID_LEN]
    return cleaned or default


def _to_anthropic_messages(raw: list[VapiMessage]) -> list[dict[str, str]]:
    """Shape Vapi's OpenAI-style history for the Anthropic API.

    Anthropic requires alternating roles starting with 'user'. Real Vapi calls
    start with the assistant (the agent speaks first on a cold call) and can
    contain consecutive same-role fragments or empty partials — all of which
    would 400 and drop the call.
    """
    merged: list[dict[str, str]] = []
    for m in raw:
        if m.role not in ("user", "assistant") or not m.content.strip():
            continue
        if merged and merged[-1]["role"] == m.role:
            merged[-1]["content"] += "\n" + m.content
        else:
            merged.append({"role": m.role, "content": m.content})

    if not merged or merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": "(call connected)"})
    return merged


async def _stream_anthropic_text(
    messages: list[dict[str, str]],
    system: str,
) -> AsyncIterator[str]:
    """Yield raw text chunks from Claude."""
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        max_retries=2,  # more retries = more dead air; failures fall back to _RECOVERY_LINE
        timeout=settings.generation_timeout_seconds,
        http_client=shared_async_http_client(),
    )
    async with client.messages.stream(
        model=settings.generation_model,
        system=system,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=256,
        temperature=settings.generation_temperature,
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _wrap_as_sse(
    text_iter: AsyncIterator[str],
    on_complete: Callable[[str], Awaitable[None]] | None = None,
) -> AsyncIterator[str]:
    """Wrap text chunks in OpenAI SSE format. Calls on_complete(full_text) after stream ends.

    A generation failure mid-stream must still end in a well-formed SSE stream —
    otherwise the voice pipeline goes silent — so errors degrade to a spoken
    recovery line instead of propagating.
    """
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    buffer: list[str] = []

    yield _sse(chunk_id, created, {"role": "assistant"}, finish_reason=None)

    try:
        async for text in text_iter:
            buffer.append(text)
            yield _sse(chunk_id, created, {"content": text}, finish_reason=None)
    except Exception:
        logger.exception("generation_stream_failed")
        buffer.append(_RECOVERY_LINE)
        yield _sse(chunk_id, created, {"content": _RECOVERY_LINE}, finish_reason=None)

    yield _sse(chunk_id, created, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"

    if on_complete:
        try:
            await on_complete("".join(buffer))
        except Exception:
            logger.exception("post_stream_hook_failed")


def _sse(
    chunk_id: str,
    created: int,
    delta: dict[str, str],
    finish_reason: str | None,
) -> str:
    payload = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": settings.generation_model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _make_audit_callback(
    pack: IndustryPack,
    call_state: CallState,
    call_id: str,
) -> Callable[[str], Awaitable[None]]:
    """Returns an on_complete callback that audits the response and persists state."""

    async def _audit(full_text: str) -> None:
        violations, disclosure_now = audit_response(full_text, pack, call_state)

        if violations:
            for v in violations:
                logger.warning("compliance_violation", call_id=call_id, kind=v.kind, detail=v.detail)
                call_state.compliance_violations.append(f"{v.kind}:{v.detail}")

        if disclosure_now:
            logger.info("disclosure_given", call_id=call_id)
            call_state.disclosure_given = True

        # Persist any updates from the audit
        if violations or disclosure_now:
            await save_call_state(call_id, call_state)

    return _audit


@router.post(
    "/vapi/llm",
    dependencies=[Depends(verify_llm_auth)],
    operation_id="vapi_llm",
)
@router.post(
    "/vapi/llm/chat/completions",
    dependencies=[Depends(verify_llm_auth)],
    operation_id="vapi_llm_chat_completions",
)
async def vapi_llm(request: VapiRequest) -> StreamingResponse:
    if not settings.anthropic_api_key:
        # Fail before the stream starts — an exception mid-SSE can't become a status code
        raise HTTPException(status_code=503, detail="Generation model not configured")

    resolved = await resolve_agent(request.call)
    pack = resolved.pack

    # ── DNC pre-flight ────────────────────────────────────────────────────────
    customer = (request.call or {}).get("customer")
    phone = customer.get("number") if isinstance(customer, dict) else None
    if not await check_dnc(phone if isinstance(phone, str) else None):
        # Number stays out of the response body (and off any error tracker);
        # check_dnc already logged it for the compliance audit trail.
        raise HTTPException(status_code=403, detail="Call refused by do-not-call policy")

    # Identify call — Vapi provides call.id; fall back to "dev-call" for local testing
    call_id = _sanitize_call_id((request.call or {}).get("id"))

    # Fetch or initialise per-call state
    call_state = await get_or_create_call_state(
        call_id, pack.name, org_id=resolved.org_id, agent_id=resolved.agent_id
    )

    last_user_msg = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )

    # ── Schedule sub-state extraction (concurrent with classification) ───────
    # When already in SCHEDULE, the email/name extractor can run alongside the
    # intent classifier — two sequential Haiku round-trips would be audible lag.
    schedule_task: asyncio.Task[dict[str, str | None]] | None = None
    if call_state.stage == ConversationState.SCHEDULE and last_user_msg:
        schedule_task = asyncio.create_task(extract_schedule_info(last_user_msg))

    # ── Intent classification ─────────────────────────────────────────────────
    if last_user_msg:
        intent, objection_id = await classify_intent(last_user_msg, pack)
    else:
        intent, objection_id = Intent.NEUTRAL, "none"

    # ── State transition ──────────────────────────────────────────────────────
    call_state = transition(call_state, intent, objection_id=objection_id)

    # FSM won't leave SCHEDULE until both email and name are collected.
    if last_user_msg and (
        schedule_task or call_state.stage == ConversationState.SCHEDULE
    ):
        info = await (schedule_task or extract_schedule_info(last_user_msg))
        if info.get("email") and not call_state.collected_email:
            call_state.collected_email = info["email"]
            logger.info(
                "schedule_email_collected",
                call_id=call_id,
                email=mask_email(info["email"] or ""),
            )
        if info.get("name") and not call_state.collected_name:
            call_state.collected_name = info["name"]
            logger.info("schedule_name_collected", call_id=call_id)
        # If we just collected the last missing piece, FSM should advance to END
        # on the NEXT turn; this turn still serves the confirm-and-close prompt.

    await save_call_state(call_id, call_state)

    # ── Objection context (only when in OBJECTION stage) ─────────────────────
    objection_ctx = None
    if call_state.stage == ConversationState.OBJECTION:
        objection_ctx = await handle_objection(pack, call_state, last_user_msg or "")

    # ── Compose system prompt ─────────────────────────────────────────────────
    parts = [
        render_system_prompt(pack),
        render_runtime_context(pack),
        render_stage_instruction(pack, call_state, objection_ctx=objection_ctx),
        render_compliance_directive(pack, call_state),
    ]
    system = "\n\n".join(p for p in parts if p)

    messages = _to_anthropic_messages(request.messages)

    audit_cb = _make_audit_callback(pack, call_state, call_id)

    return StreamingResponse(
        _wrap_as_sse(_stream_anthropic_text(messages, system), on_complete=audit_cb),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Vapi server webhook (end-of-call reports, status updates) ────────────────


def _normalise_vapi_messages(raw_messages: object) -> list[dict[str, str]]:
    """Vapi uses 'bot'/'user' roles; convert to OpenAI-style 'assistant'/'user'.

    Webhook payloads are only shared-secret authenticated, so shape is verified
    field by field — a malformed report must not 500 the endpoint.
    """
    if not isinstance(raw_messages, list):
        return []
    normalised: list[dict[str, str]] = []
    for m in raw_messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("message") or m.get("content") or ""
        if role == "bot":
            role = "assistant"
        if role in ("user", "assistant") and isinstance(content, str) and content:
            normalised.append({"role": role, "content": content})
    return normalised


@router.post("/vapi/server", dependencies=[Depends(verify_server_auth)])
async def vapi_server(payload: dict[str, Any]) -> dict[str, Any]:
    """Receive Vapi server-side events. We only act on end-of-call-report."""
    message = payload.get("message")
    if not isinstance(message, dict):
        logger.warning("vapi_server_malformed_payload")
        return {"status": "ignored"}

    msg_type = message.get("type")
    logger.info("vapi_server_event", type=msg_type)

    if msg_type != "end-of-call-report":
        return {"status": "ignored"}

    call = message.get("call")
    call_id = _sanitize_call_id(
        call.get("id") if isinstance(call, dict) else None, default="unknown"
    )

    transcript_messages = _normalise_vapi_messages(message.get("messages"))
    if not transcript_messages:
        logger.warning("end_of_call_no_messages", call_id=call_id)
        return {"status": "no-messages"}

    resolved = await resolve_agent(call if isinstance(call, dict) else None)
    pack = resolved.pack
    appt = await extract_appointment(call_id, pack.name, transcript_messages)
    appt.org_id = resolved.org_id
    appt.agent_id = resolved.agent_id
    await save_appointment(appt)

    record = await _build_call_record(
        message, call, call_id, resolved, appt.booked, transcript_messages
    )
    await save_call_record(record)
    await link_lead(call_id, record.outcome)
    return {"status": "saved", "booked": appt.booked}


def _parse_ts(raw: object) -> datetime | None:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _derive_outcome(ended_reason: str | None, booked: bool) -> str:
    if booked:
        return "booked"
    reason = (ended_reason or "").lower()
    if "no-answer" in reason or "busy" in reason:
        return "no_answer"
    if "voicemail" in reason:
        return "voicemail"
    if "error" in reason or "failed" in reason:
        return "failed"
    return "completed"


async def _build_call_record(
    message: dict[str, Any],
    call: object,
    call_id: str,
    resolved: ResolvedAgent,
    booked: bool,
    transcript: list[dict[str, str]],
) -> CallRecord:
    """Field-by-field defensive parse — a malformed report must not 500."""
    try:
        state = await get_call_state(call_id)
    except Exception as exc:
        # State enriches the record (stage/objections); a dead Redis must not
        # cost us the call record itself.
        logger.warning("call_state_fetch_failed", call_id=call_id, error=str(exc))
        state = None
    customer = call.get("customer") if isinstance(call, dict) else None
    number = customer.get("number") if isinstance(customer, dict) else None
    duration = message.get("durationSeconds")
    cost = message.get("cost")
    ended_reason = message.get("endedReason")
    summary = message.get("summary")
    return CallRecord(
        vapi_call_id=call_id,
        org_id=resolved.org_id or (state.org_id if state else None),
        agent_id=resolved.agent_id or (state.agent_id if state else None),
        customer_number=number if isinstance(number, str) else None,
        started_at=_parse_ts(message.get("startedAt")),
        ended_at=_parse_ts(message.get("endedAt")),
        duration_seconds=int(duration) if isinstance(duration, int | float) else None,
        ended_reason=ended_reason if isinstance(ended_reason, str) else None,
        stage_reached=state.stage.value if state else None,
        outcome=_derive_outcome(
            ended_reason if isinstance(ended_reason, str) else None, booked
        ),
        booked=booked,
        objections=sorted(state.objection_strikes) if state else [],
        transcript=transcript,
        summary=summary if isinstance(summary, str) else None,
        cost_usd=float(cost) if isinstance(cost, int | float) else None,
    )
