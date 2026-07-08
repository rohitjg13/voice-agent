"""Authenticated dashboard API — everything under /api/v1."""

from fastapi import APIRouter

from orchestrator.routers.dashboard import (
    agents,
    analytics,
    billing,
    calls,
    campaigns,
    knowledge,
    orgs,
    packs,
    phone_numbers,
)

router = APIRouter(prefix="/api/v1")
router.include_router(orgs.router)
router.include_router(agents.router)
router.include_router(knowledge.router)
router.include_router(calls.router)
router.include_router(analytics.router)
router.include_router(campaigns.router)
router.include_router(phone_numbers.router)
router.include_router(billing.router)
router.include_router(packs.router)
