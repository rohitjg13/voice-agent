"""Thin async wrapper over the Vapi REST API (assistants, phone numbers, calls).

Payloads are built minimal — Vapi rejects unknown fields, adds new ones
freely, so responses are treated as loose dicts. The Custom LLM bearer
secret (VAPI_LLM_SECRET) is configured once as a Custom LLM credential in
the Vapi dashboard; it is not part of the assistant payload.
"""

from typing import Any
from uuid import UUID

import httpx
import structlog

from orchestrator.config import settings
from packs._schema.pack import IndustryPack

logger = structlog.get_logger()

_BASE = "https://api.vapi.ai"
_TIMEOUT = 30.0


class VapiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Vapi API {status}: {detail}")


async def _request(
    method: str, path: str, json_body: dict[str, Any] | None = None
) -> Any:
    if not settings.vapi_api_key:
        raise VapiError(503, "VAPI_API_KEY not configured")
    # ponytail: fresh client per request — these are low-volume admin/dial ops
    async with httpx.AsyncClient(base_url=_BASE, timeout=_TIMEOUT) as client:
        resp = await client.request(
            method,
            path,
            json=json_body,
            headers={"Authorization": f"Bearer {settings.vapi_api_key}"},
        )
    if resp.status_code >= 400:
        logger.warning("vapi_api_error", path=path, status=resp.status_code)
        raise VapiError(resp.status_code, resp.text[:500])
    return resp.json()


def _assistant_payload(
    pack: IndustryPack, display_name: str, agent_id: UUID, org_id: UUID
) -> dict[str, Any]:
    base = settings.public_base_url.rstrip("/")
    payload: dict[str, Any] = {
        "name": display_name[:40],
        "model": {
            "provider": "custom-llm",
            "url": f"{base}/vapi/llm",
            "model": "coldline-orchestrator",
        },
        "transcriber": {"provider": "deepgram", "model": "nova-2"},
        "firstMessage": pack.stages.opener,
        "metadata": {"org_id": str(org_id), "agent_id": str(agent_id)},
        "server": {"url": f"{base}/vapi/server"},
    }
    if settings.vapi_server_secret:
        payload["server"]["secret"] = settings.vapi_server_secret
    if pack.agent.voice_id:
        payload["voice"] = {"provider": "11labs", "voiceId": pack.agent.voice_id}
    return payload


async def create_assistant(
    pack: IndustryPack, display_name: str, agent_id: UUID, org_id: UUID
) -> str:
    if not settings.public_base_url:
        raise VapiError(503, "PUBLIC_BASE_URL not configured")
    data = await _request(
        "POST", "/assistant", _assistant_payload(pack, display_name, agent_id, org_id)
    )
    assistant_id = str(data["id"])
    logger.info("vapi_assistant_created", assistant_id=assistant_id, agent_id=str(agent_id))
    return assistant_id


async def update_assistant(
    assistant_id: str,
    pack: IndustryPack,
    display_name: str,
    agent_id: UUID,
    org_id: UUID,
) -> None:
    if not settings.public_base_url:
        raise VapiError(503, "PUBLIC_BASE_URL not configured")
    await _request(
        "PATCH",
        f"/assistant/{assistant_id}",
        _assistant_payload(pack, display_name, agent_id, org_id),
    )
    logger.info("vapi_assistant_updated", assistant_id=assistant_id)


async def buy_phone_number(area_code: str | None = None) -> dict[str, Any]:
    """Provision a free Vapi number. Returns {id, number, ...}."""
    body: dict[str, Any] = {"provider": "vapi"}
    if area_code:
        body["numberDesiredAreaCode"] = area_code
    data = await _request("POST", "/phone-number", body)
    return data if isinstance(data, dict) else {}


async def create_call(
    assistant_id: str, phone_number_id: str, customer_number: str
) -> dict[str, Any]:
    """Start one outbound call. Returns the Vapi call object ({id, ...})."""
    data = await _request(
        "POST",
        "/call",
        {
            "assistantId": assistant_id,
            "phoneNumberId": phone_number_id,
            "customer": {"number": customer_number},
        },
    )
    return data if isinstance(data, dict) else {}
