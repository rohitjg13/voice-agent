"""Shared-secret verification for Vapi → backend traffic.

Each verifier:
  - Allows the request through if the configured secret is empty/whitespace (dev mode).
  - Returns a generic 401 if the secret is set but the header is missing or wrong.
    The real reason (missing / wrong-scheme / empty-token / bad-token) goes to
    structlog so operators can debug misconfiguration without exposing an oracle
    to unauthenticated callers.
"""

import hmac
from typing import Any, NoReturn

import structlog
from fastapi import Header, HTTPException, status

from orchestrator.config import settings

logger = structlog.get_logger()

_WWW_AUTH_BEARER = 'Bearer realm="vapi"'


def _consteq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _unauthorized(reason: str, **fields: Any) -> NoReturn:
    """Log the real reason, raise a generic 401 with WWW-Authenticate."""
    logger.warning("auth_failed", reason=reason, **fields)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": _WWW_AUTH_BEARER},
    )


async def verify_llm_auth(
    authorization: str | None = Header(default=None),
) -> None:
    """Vapi Custom LLM passes the configured API key as `Authorization: Bearer <key>`.

    Auth-scheme matching is case-insensitive per RFC 7235. Token/secret are both
    stripped so trailing/leading whitespace in either side doesn't break auth.
    """
    expected = settings.vapi_llm_secret.strip()
    if not expected:
        return  # auth disabled (dev / CI)

    if not authorization:
        _unauthorized("missing_header", endpoint="vapi_llm")

    parts = authorization.split(None, 1)  # splits on any whitespace run
    if len(parts) < 2:
        _unauthorized("missing_token", endpoint="vapi_llm")

    scheme, token = parts[0], parts[1].strip()
    if scheme.lower() != "bearer":
        _unauthorized("wrong_scheme", endpoint="vapi_llm", scheme=scheme)
    if not token:
        _unauthorized("empty_token", endpoint="vapi_llm")
    if not _consteq(token, expected):
        _unauthorized("bad_token", endpoint="vapi_llm")


async def verify_server_auth(
    x_vapi_secret: str | None = Header(default=None),
) -> None:
    """Vapi server webhooks send the configured secret as `x-vapi-secret: <value>`."""
    expected = settings.vapi_server_secret.strip()
    if not expected:
        return  # auth disabled (dev / CI)

    received = (x_vapi_secret or "").strip()
    if not received:
        _unauthorized("missing_header", endpoint="vapi_server")
    if not _consteq(received, expected):
        _unauthorized("bad_secret", endpoint="vapi_server")
