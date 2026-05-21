import json
import time
import uuid
from collections.abc import AsyncIterator

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from orchestrator.config import settings
from orchestrator.models.vapi import VapiRequest

router = APIRouter()

# Replaced in step 6 with pack-composed prompt
_HARDCODED_SYSTEM = (
    "You are a professional cold-calling AI agent named Alex. "
    "Be warm, concise, and natural — never robotic. "
    "Keep every reply under 40 words. "
    "Your goal is to book a 15-minute discovery call."
)


async def _stream_openai_sse(
    messages: list[dict[str, str]],
    system: str,
) -> AsyncIterator[str]:
    """Yields OpenAI-compatible SSE chunks from an Anthropic streaming call."""
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    # Opening chunk — role delta
    yield _sse(chunk_id, created, {"role": "assistant"}, finish_reason=None)

    async with client.messages.stream(
        model=settings.generation_model,
        system=system,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=settings.max_tokens if hasattr(settings, "max_tokens") else 256,
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
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/vapi/llm")
async def vapi_llm(request: VapiRequest) -> StreamingResponse:
    # Strip injected system messages — we own the system prompt
    messages = [
        {"role": m.role, "content": m.content}
        for m in request.messages
        if m.role in ("user", "assistant")
    ]

    if not messages:
        raise HTTPException(status_code=422, detail="messages must contain at least one user turn")

    return StreamingResponse(
        _stream_openai_sse(messages, _HARDCODED_SYSTEM),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
