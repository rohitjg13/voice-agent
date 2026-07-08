"""Shared test fakes. FakeDB stands in for the asyncpg pool AND connection —
route canned results by query substring, record every call for assertions."""

import json
from typing import Any

_DEFAULT_LIMITS = {
    "max_agents": 5,
    "included_minutes": 500,
    "max_active_campaigns": 5,
    "max_leads_per_campaign": 500,
}


def subscription_rows(
    limits: dict[str, int] | None = None,
    agents: int = 0,
    active_campaigns: int = 0,
    period_seconds: int = 0,
    status: str = "active",
) -> dict[str, Any]:
    """FakeDB responses for the entitlements queries (subscription + usage)."""
    return {
        "FROM subscriptions s JOIN plans p": {
            "plan_id": "trial",
            "name": "Trial",
            "plan_name": "Trial",
            "status": status,
            "current_period_start": None,
            "current_period_end": None,
            "limits": json.dumps(limits or _DEFAULT_LIMITS),
        },
        # longer than any other fragment matching the usage query → wins routing
        "AND status != 'archived') AS agents": {
            "agents": agents,
            "active_campaigns": active_campaigns,
            "period_seconds": period_seconds,
        },
    }


class _Ctx:
    def __init__(self, value: Any) -> None:
        self._value = value

    async def __aenter__(self) -> Any:
        return self._value

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeDB:
    def __init__(self, responses: dict[str, Any] | None = None):
        # {query substring: canned result (or zero-arg callable producing one)}
        self.responses = responses or {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _lookup(self, query: str) -> Any:
        # longest matching fragment wins — most specific route
        best: str | None = None
        for frag in self.responses:
            if frag in query and (best is None or len(frag) > len(best)):
                best = frag
        if best is None:
            return None
        result = self.responses[best]
        return result() if callable(result) else result

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append((query, args))
        return self._lookup(query)

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append((query, args))
        return self._lookup(query)

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append((query, args))
        return self._lookup(query) or []

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append((query, args))
        return self._lookup(query) or "OK"  # e.g. {"UPDATE agents": "UPDATE 1"}

    # pool.acquire() / conn.transaction() both just hand back self / a no-op ctx
    def acquire(self) -> _Ctx:
        return _Ctx(self)

    def transaction(self) -> _Ctx:
        return _Ctx(None)

    def queries(self, fragment: str) -> list[tuple[str, tuple[Any, ...]]]:
        return [(q, a) for q, a in self.calls if fragment in q]
