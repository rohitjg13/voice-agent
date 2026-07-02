from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from orchestrator import db
from orchestrator.config import settings
from orchestrator.middleware import BodySizeLimitMiddleware
from orchestrator.routers import vapi

logger = structlog.get_logger()


def _is_production() -> bool:
    return settings.environment.lower() in {"production", "prod"}


def enforce_auth_config() -> None:
    """In production, an empty Vapi secret means the endpoint is publicly callable.

    Fail closed: refuse to boot unless ALLOW_INSECURE_PUBLIC_ENDPOINTS=true is
    set explicitly. A publicly reachable /vapi/llm lets anyone drive the agent
    and burn LLM quota; a crashed deploy is the cheaper failure.
    """
    if not _is_production():
        return

    missing = [
        endpoint
        for endpoint, secret in (
            ("vapi_llm", settings.vapi_llm_secret),
            ("vapi_server", settings.vapi_server_secret),
        )
        if not secret.strip()
    ]
    if not missing:
        return

    if settings.allow_insecure_public_endpoints:
        for endpoint in missing:
            logger.warning(
                "auth_disabled_in_production",
                endpoint=endpoint,
                reason="empty_secret_with_explicit_override",
            )
        return

    raise RuntimeError(
        f"Refusing to start: ENVIRONMENT={settings.environment} but no secret is set "
        f"for: {', '.join(missing)}. Set VAPI_LLM_SECRET / VAPI_SERVER_SECRET, or set "
        "ALLOW_INSECURE_PUBLIC_ENDPOINTS=true to accept publicly callable endpoints."
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    enforce_auth_config()
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(
    title="Voice Agent Platform",
    version="0.1.0",
    lifespan=lifespan,
    # Don't advertise the API surface on the public internet
    docs_url=None if _is_production() else "/docs",
    redoc_url=None if _is_production() else "/redoc",
    openapi_url=None if _is_production() else "/openapi.json",
)

app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)

app.include_router(vapi.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
