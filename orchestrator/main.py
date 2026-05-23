from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from orchestrator import db
from orchestrator.config import settings
from orchestrator.routers import vapi

logger = structlog.get_logger()


def _warn_if_auth_misconfigured() -> None:
    """In production, an empty Vapi secret means the endpoint is publicly callable.

    Doesn't refuse to boot (per current ops choice) but emits a loud structured
    warning so operators see the misconfiguration in their log stream.
    """
    if settings.environment.lower() not in {"production", "prod"}:
        return
    if not settings.vapi_llm_secret.strip():
        logger.warning(
            "auth_misconfigured_at_startup",
            endpoint="vapi_llm",
            reason="empty_secret_in_production",
        )
    if not settings.vapi_server_secret.strip():
        logger.warning(
            "auth_misconfigured_at_startup",
            endpoint="vapi_server",
            reason="empty_secret_in_production",
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _warn_if_auth_misconfigured()
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(title="Voice Agent Platform", version="0.1.0", lifespan=lifespan)

app.include_router(vapi.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
