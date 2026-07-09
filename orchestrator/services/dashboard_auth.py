"""Supabase JWT verification for dashboard API traffic.

Unlike the Vapi endpoints (empty secret = dev mode), dashboard auth fails
closed in every environment: a misconfigured deployment must 401, never
expose tenant data. Failure reasons go to structlog, callers get a generic
401 — same no-oracle policy as services/auth.py.

Verification chain:
  - SUPABASE_JWT_SECRET set → HS256 (self-hosted / legacy projects; also tests)
  - else SUPABASE_URL set → JWKS RS256/ES256 (cloud projects, asymmetric keys)
  - else → unauthorized (fail closed)
"""

from typing import Annotated, Any, NoReturn
from uuid import UUID

import jwt
import structlog
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

from orchestrator.config import settings
from orchestrator.db import require_pool

logger = structlog.get_logger()

_WWW_AUTH_BEARER = 'Bearer realm="dashboard"'


class AuthContext(BaseModel):
    user_id: UUID
    email: str = ""
    org_id: UUID | None = None
    role: str | None = None


def _unauthorized(reason: str, **fields: Any) -> NoReturn:
    logger.warning("dashboard_auth_failed", reason=reason, **fields)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": _WWW_AUTH_BEARER},
    )


_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    # ponytail: sync JWKS fetch blocks the loop on first call, then cached 10 min
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=600,
        )
    return _jwks_client


def _decode(token: str) -> dict[str, Any]:
    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    if settings.supabase_url:
        key = _get_jwks_client().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token, key, algorithms=["RS256", "ES256"], audience="authenticated"
        )
    raise jwt.InvalidTokenError("supabase auth not configured")


async def verify_dashboard_auth(
    authorization: str | None = Header(default=None),
) -> AuthContext:
    if not authorization:
        _unauthorized("missing_header")

    parts = authorization.split(None, 1)
    if len(parts) < 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        _unauthorized("bad_scheme_or_empty_token")

    try:
        claims = _decode(parts[1].strip())
    except jwt.PyJWTError as exc:
        _unauthorized("invalid_token", error=str(exc))

    try:
        user_id = UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        _unauthorized("bad_sub")

    # Authorization comes from our tables only — never from user-editable
    # JWT metadata. One org per user in v1.
    pool = require_pool()
    row = await pool.fetchrow(
        "SELECT org_id, role FROM org_members WHERE user_id = $1 LIMIT 1", user_id
    )
    return AuthContext(
        user_id=user_id,
        email=str(claims.get("email") or ""),
        org_id=row["org_id"] if row else None,
        role=row["role"] if row else None,
    )


AuthCtx = Annotated[AuthContext, Depends(verify_dashboard_auth)]


class OrgContext(AuthContext):
    """AuthContext narrowed to members of an organization."""

    org_id: UUID
    role: str


async def require_org(ctx: AuthCtx) -> OrgContext:
    """403 for authenticated users who haven't completed org onboarding."""
    if ctx.org_id is None or ctx.role is None:
        raise HTTPException(status_code=403, detail="No organization")
    return OrgContext(**ctx.model_dump())


# Route param type for org-scoped endpoints: ctx.org_id is guaranteed non-None.
OrgCtx = Annotated[OrgContext, Depends(require_org)]
