import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import anthropic
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from orchestrator.config import settings
from orchestrator.models.call_state import CallState, ConversationState, Intent
from orchestrator.models.vapi import VapiRequest
from orchestrator.services.appointment_extractor import extract_appointment
from orchestrator.services.appointment_store import save_appointment
from orchestrator.services.auth import verify_llm_auth, verify_server_auth
from orchestrator.services.call_state_store import (
    get_or_create_call_state,
    save_call_state,
)
from orchestrator.services.compliance import (
    audit_response,
    check_dnc,
    render_compliance_directive,
)
from orchestrator.services.intent_classifier import classify_intent
from orchestrator.services.objection_handler import handle_objection
from orchestrator.services.prompt_composer import (
    render_runtime_context,
    render_stage_instruction,
    render_system_prompt,
)
from orchestrator.services.schedule_extractor import extract_schedule_info
from orchestrator.services.state_machine import transition
from packs._schema.pack import IndustryPack
from packs.pack_loader import load_pack

logger = structlog.get_logger()

router = APIRouter()


async def _stream_anthropic_text(
    messages: list[dict[str, str]],
    system: str,
) -> AsyncIterator[str]:
    """Yield raw text chunks from Claude."""
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        max_retries=4,  # 2 by default; overloaded_error transient under voice load
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
    """Wrap text chunks in OpenAI SSE format. Calls on_complete(full_text) after stream ends."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    buffer: list[str] = []

    yield _sse(chunk_id, created, {"role": "assistant"}, finish_reason=None)

    async for text in text_iter:
        buffer.append(text)
        yield _sse(chunk_id, created, {"content": text}, finish_reason=None)

    yield _sse(chunk_id, created, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"

    if on_complete:
        await on_complete("".join(buffer))


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
    pack = load_pack(settings.active_pack)

    # ── DNC pre-flight ────────────────────────────────────────────────────────
    customer = (request.call or {}).get("customer") or {}
    phone = customer.get("number")
    if not await check_dnc(phone):
        raise HTTPException(
            status_code=403,
            detail=f"Phone number {phone} is on the do-not-call list",
        )

    # Identify call — Vapi provides call.id; fall back to "dev" for local testing
    call_id: str = (request.call or {}).get("id", "dev-call")

    # Fetch or initialise per-call state
    call_state = await get_or_create_call_state(call_id, pack.name)

    # ── Intent classification ─────────────────────────────────────────────────
    last_user_msg = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )
    if last_user_msg:
        intent, objection_id = await classify_intent(last_user_msg, pack)
    else:
        intent, objection_id = Intent.NEUTRAL, "none"

    # ── State transition ──────────────────────────────────────────────────────
    call_state = transition(call_state, intent, objection_id=objection_id)

    # ── Schedule sub-state extraction ─────────────────────────────────────────
    # When in SCHEDULE, scan the last user message for email/name and persist.
    # FSM won't leave SCHEDULE until both are collected.
    if call_state.stage == ConversationState.SCHEDULE and last_user_msg:
        info = await extract_schedule_info(last_user_msg)
        if info.get("email") and not call_state.collected_email:
            call_state.collected_email = info["email"]
            logger.info("schedule_email_collected", call_id=call_id, email=info["email"])
        if info.get("name") and not call_state.collected_name:
            call_state.collected_name = info["name"]
            logger.info("schedule_name_collected", call_id=call_id, name=info["name"])
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

    messages = [
        {"role": m.role, "content": m.content}
        for m in request.messages
        if m.role in ("user", "assistant")
    ]
    if not messages:
        raise HTTPException(status_code=422, detail="messages must contain at least one user turn")

    audit_cb = _make_audit_callback(pack, call_state, call_id)

    return StreamingResponse(
        _wrap_as_sse(_stream_anthropic_text(messages, system), on_complete=audit_cb),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Vapi server webhook (end-of-call reports, status updates) ────────────────


def _normalise_vapi_messages(raw_messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Vapi uses 'bot'/'user' roles; convert to OpenAI-style 'assistant'/'user'."""
    normalised: list[dict[str, str]] = []
    for m in raw_messages:
        role = m.get("role")
        content = m.get("message") or m.get("content") or ""
        if role == "bot":
            role = "assistant"
        if role in ("user", "assistant") and content:
            normalised.append({"role": role, "content": content})
    return normalised


@router.post("/vapi/server", dependencies=[Depends(verify_server_auth)])
async def vapi_server(payload: dict[str, Any]) -> dict[str, Any]:
    """Receive Vapi server-side events. We only act on end-of-call-report."""
    message: dict[str, Any] = payload.get("message") or {}
    msg_type = message.get("type")
    logger.info("vapi_server_event", type=msg_type)

    if msg_type != "end-of-call-report":
        return {"status": "ignored"}

    call: dict[str, Any] = message.get("call") or {}
    call_id = call.get("id", "unknown")

    transcript_messages = _normalise_vapi_messages(message.get("messages") or [])
    if not transcript_messages:
        logger.warning("end_of_call_no_messages", call_id=call_id)
        return {"status": "no-messages"}

    pack = load_pack(settings.active_pack)
    appt = await extract_appointment(call_id, pack.name, transcript_messages)
    await save_appointment(appt)
    return {"status": "saved", "booked": appt.booked}
