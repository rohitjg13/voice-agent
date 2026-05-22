"""
Adversarial simulator — drives a persona through a full call against /vapi/llm.

Bypasses Vapi/audio entirely. Uses httpx.ASGITransport to call the FastAPI app
in-process so CI can run a dozen full conversations in under a minute.
"""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
import structlog
import yaml
from httpx import ASGITransport, AsyncClient

from orchestrator.config import settings
from orchestrator.main import app
from orchestrator.models.call_state import CallState, ConversationState
from orchestrator.services.call_state_store import clear_mem_store, get_call_state

logger = structlog.get_logger()

_PERSONAS_PATH = Path(__file__).parent / "personas.yaml"


@dataclass
class Persona:
    name: str
    label: str
    description: str
    system_prompt: str


@dataclass
class SimResult:
    persona: str
    transcript: list[dict[str, str]]
    final_state: ConversationState | None
    turn_count: int
    reached_schedule: bool
    compliance_violations: list[str] = field(default_factory=list)


def load_personas() -> list[Persona]:
    raw = yaml.safe_load(_PERSONAS_PATH.read_text(encoding="utf-8"))
    return [Persona(**p) for p in raw]


def get_persona(name: str) -> Persona:
    for p in load_personas():
        if p.name == name:
            return p
    raise KeyError(f"No persona named '{name}'")


# ── SSE parsing ──────────────────────────────────────────────────────────────


async def _stream_to_text(response: Any) -> str:
    """Collect content from an OpenAI-compatible SSE stream into a single string."""
    parts: list[str] = []
    async for line in response.aiter_lines():
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if "content" in delta:
            parts.append(delta["content"])
    return "".join(parts)


# ── agent + persona turns ────────────────────────────────────────────────────


async def _agent_turn(
    client: AsyncClient,
    transcript: list[dict[str, str]],
    call_id: str,
) -> str:
    payload = {
        "model": "gpt-4o",
        "stream": True,
        "messages": transcript,
        "call": {"id": call_id},
    }
    async with client.stream("POST", "/vapi/llm", json=payload) as response:
        if response.status_code != 200:
            body = await response.aread()
            raise RuntimeError(f"agent returned {response.status_code}: {body!r}")
        return await _stream_to_text(response)


def _flip_for_persona(transcript: list[dict[str, str]]) -> list[dict[str, str]]:
    """Convert agent-POV roles to persona-POV (user <-> assistant)."""
    return [
        {
            "role": "user" if m["role"] == "assistant" else "assistant",
            "content": m["content"],
        }
        for m in transcript
    ]


async def _persona_turn(
    persona: Persona,
    transcript: list[dict[str, str]],
) -> str:
    """Have the persona LLM produce the next prospect reply."""
    # Drop the seed "Hello?" so persona history starts with the agent's first reply
    flipped = _flip_for_persona(transcript[1:])
    if not flipped or flipped[-1]["role"] != "user":
        # Defensive: if something's off, just have the persona say something neutral
        return "Okay."

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.classifier_model,
        max_tokens=80,
        system=persona.system_prompt,
        messages=flipped,  # type: ignore[arg-type]
    )
    return response.content[0].text  # type: ignore[union-attr]


# ── main simulation loop ──────────────────────────────────────────────────────


def _outcome_from_state(state: CallState | None, transcript: list[dict[str, str]]) -> bool:
    """Did the agent successfully book a meeting?"""
    if state and state.stage in (ConversationState.SCHEDULE, ConversationState.END):
        # SCHEDULE state, or END after going through SCHEDULE
        if state.stage == ConversationState.SCHEDULE:
            return True
        # Look back in transcript for schedule-related agent message
        last_three = " ".join(m["content"].lower() for m in transcript[-4:] if m["role"] == "assistant")
        if any(k in last_three for k in ("calendar", "invite", "scheduled", "send the email")):
            return True
    return False


async def run_simulation(persona: Persona, max_turns: int = 14) -> SimResult:
    """Drive one persona through a full conversation."""
    clear_mem_store()  # fresh state for this simulation
    call_id = f"sim-{persona.name}-{uuid.uuid4().hex[:6]}"
    transcript: list[dict[str, str]] = [{"role": "user", "content": "Hello?"}]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://sim", timeout=60.0) as client:
        for _ in range(max_turns):
            agent_msg = await _agent_turn(client, transcript, call_id)
            transcript.append({"role": "assistant", "content": agent_msg})

            state = await get_call_state(call_id)
            if state and state.stage == ConversationState.END:
                break

            persona_msg = await _persona_turn(persona, transcript)
            transcript.append({"role": "user", "content": persona_msg})

    state = await get_call_state(call_id)
    return SimResult(
        persona=persona.name,
        transcript=transcript,
        final_state=state.stage if state else None,
        turn_count=len(transcript) // 2,
        reached_schedule=_outcome_from_state(state, transcript),
        compliance_violations=list(state.compliance_violations) if state else [],
    )
