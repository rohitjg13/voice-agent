import structlog
from fastapi import FastAPI

from orchestrator.routers import vapi

logger = structlog.get_logger()

app = FastAPI(title="Voice Agent Platform", version="0.1.0")

app.include_router(vapi.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
