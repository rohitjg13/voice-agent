from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class VapiMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class VapiRequest(BaseModel):
    """Vapi Custom LLM payload — OpenAI-compatible with an extra `call` field."""

    model_config = ConfigDict(extra="allow")

    model: str = "gpt-4o"
    messages: list[VapiMessage]
    stream: bool = True
    temperature: float | None = None
    max_tokens: int | None = None
    call: dict[str, Any] | None = None  # Vapi call metadata
