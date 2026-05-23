"""Test-suite fixtures.

Resets Vapi auth secrets to empty before every test so that a developer's local
.env can't accidentally turn auth on for tests that don't expect it. Tests that
need auth enabled opt in via their own monkeypatch.setattr(...).
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_vapi_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_llm_secret", "")
    monkeypatch.setattr("orchestrator.services.auth.settings.vapi_server_secret", "")
