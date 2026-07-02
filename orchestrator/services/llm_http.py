"""Shared HTTP connection pool for LLM SDK clients.

Every anthropic/openai client constructed per-request would otherwise open a
fresh TCP+TLS connection — 100-300 ms added to every conversational turn.
Passing one long-lived httpx.AsyncClient into the SDK constructors keeps the
constructors cheap (so tests can still patch them) while reusing connections.
"""

import httpx

_client: httpx.AsyncClient | None = None


def shared_async_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _client
