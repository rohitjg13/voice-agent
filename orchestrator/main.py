from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from orchestrator import db
from orchestrator.routers import vapi

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(title="Voice Agent Platform", version="0.1.0", lifespan=lifespan)

app.include_router(vapi.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
