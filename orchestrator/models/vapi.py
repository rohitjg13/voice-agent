from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class VapiMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Deliberately not a Literal: an unexpected role ("tool", "function", …)
    # must not 422 the whole request — a rejected turn is dead air on a live
    # call. Downstream code filters to user/assistant.
    role: str
    content: str = ""

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_content(cls, v: Any) -> Any:
        """Accept OpenAI content-parts arrays and null, flattening to text."""
        if v is None:
            return ""
        if isinstance(v, list):
            return "".join(
                str(part.get("text", ""))
                for part in v
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return v


class VapiRequest(BaseModel):
    """Vapi Custom LLM payload — OpenAI-compatible with an extra `call` field."""

    model_config = ConfigDict(extra="allow")

    model: str = "gpt-4o"
    messages: list[VapiMessage] = []
    stream: bool = True
    temperature: float | None = None
    max_tokens: int | None = None
    call: dict[str, Any] | None = None  # Vapi call metadata
