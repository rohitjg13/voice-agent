"""Shared-secret verification for Vapi → backend traffic.

Each verifier:
  - Allows the request through if the configured secret is empty (dev mode).
  - Returns 401 if the secret is set but the header is missing or wrong.
"""

import hmac

from fastapi import Header, HTTPException, status

from orchestrator.config import settings


def _consteq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


async def verify_llm_auth(
    authorization: str | None = Header(default=None),
) -> None:
    """Vapi Custom LLM passes the configured API key as `Authorization: Bearer <key>`.

    Auth-scheme matching is case-insensitive per RFC 7235 — accepts 'Bearer',
    'bearer', 'BEARER', etc. so intermediaries that normalise the header don't break us.
    """
    expected = settings.vapi_llm_secret
    if not expected:
        return  # auth disabled

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    if not _consteq(token.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )


async def verify_server_auth(
    x_vapi_secret: str | None = Header(default=None),
) -> None:
    """Vapi server webhooks send the configured secret as `x-vapi-secret: <value>`."""
    expected = settings.vapi_server_secret
    if not expected:
        return  # auth disabled

    if not x_vapi_secret or not _consteq(x_vapi_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing x-vapi-secret header",
        )
