import json
import time
import uuid
from collections.abc import AsyncIterator

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from orchestrator.config import settings
from orchestrator.models.call_state import Intent
from orchestrator.models.vapi import VapiRequest
from orchestrator.services.call_state_store import get_or_create_call_state, save_call_state
from orchestrator.services.intent_classifier import classify_intent
from orchestrator.services.prompt_composer import render_stage_instruction, render_system_prompt
from orchestrator.services.state_machine import transition
from packs.pack_loader import load_pack

router = APIRouter()


async def _stream_openai_sse(
    messages: list[dict[str, str]],
    system: str,
) -> AsyncIterator[str]:
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    yield _sse(chunk_id, created, {"role": "assistant"}, finish_reason=None)

    async with client.messages.stream(
        model=settings.generation_model,
        system=system,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=256,
    ) as stream:
        async for text in stream.text_stream:
            yield _sse(chunk_id, created, {"content": text}, finish_reason=None)

    yield _sse(chunk_id, created, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


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


@router.post("/vapi/llm")
async def vapi_llm(request: VapiRequest) -> StreamingResponse:
    pack = load_pack(settings.active_pack)

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
    await save_call_state(call_id, call_state)

    # ── Compose system prompt ─────────────────────────────────────────────────
    system = render_system_prompt(pack) + "\n\n" + render_stage_instruction(pack, call_state)

    messages = [
        {"role": m.role, "content": m.content}
        for m in request.messages
        if m.role in ("user", "assistant")
    ]
    if not messages:
        raise HTTPException(status_code=422, detail="messages must contain at least one user turn")

    return StreamingResponse(
        _stream_openai_sse(messages, system),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
