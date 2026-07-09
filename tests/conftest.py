"""Test-suite fixtures.

The settings singleton is built from the developer's .env at import time, so
without a reset the suite would behave differently on every machine — real
Upstash/Anthropic credentials in a local .env would make tests hit live
services (and bill for it). Every external integration is blanked before each
test; tests that need a value opt in with their own monkeypatch.setattr(...),
which runs after this autouse fixture.
"""

import pytest

from orchestrator.config import settings

_HERMETIC_DEFAULTS = {
    "anthropic_api_key": "",
    "openai_api_key": "",
    "upstash_redis_rest_url": "",
    "upstash_redis_rest_token": "",
    "database_url": "",
    "vapi_llm_secret": "",
    "vapi_server_secret": "",
    "supabase_url": "",
    "supabase_jwt_secret": "",
    "vapi_api_key": "",
    "public_base_url": "",
    "environment": "development",
    "allow_insecure_public_endpoints": False,
}


@pytest.fixture(autouse=True)
def _isolate_external_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for field, value in _HERMETIC_DEFAULTS.items():
        monkeypatch.setattr(settings, field, value)
