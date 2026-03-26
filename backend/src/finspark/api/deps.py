"""
FastAPI dependency injectors — auth, DB session, tenant context, pagination.

Dependency graph (outer to inner):
  get_db              → yields AsyncSession
  get_current_user    → decodes JWT → UserContext
  get_tenant_context  → validates tenant membership → TenantContext
  require_roles(...)  → factory for role-assertion guard
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.core.db import get_db
from finspark.core.security import decode_token

logger = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=True)

# ---------------------------------------------------------------------------
# OAuth2 scheme kept for Swagger UI token form compatibility
# ---------------------------------------------------------------------------
from fastapi.security import OAuth2PasswordBearer  # noqa: E402

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


# ---------------------------------------------------------------------------
# Context dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UserContext:
    user_id: UUID
    email: str
    roles: frozenset[str]
    tenant_ids: frozenset[UUID]


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: UUID
    user: UserContext
    plan: str = "standard"


@dataclass(frozen=True, slots=True)
class PaginationParams:
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth — primary dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
) -> UserContext:
    """
    Decode and validate Bearer JWT.

    Expected JWT claims:
        sub     — user UUID string
        type    — must be "access"
        email   — user email
        roles   — list[str]  (e.g. ["admin", "viewer"])
        tenants — list[str UUID]
    """
    _401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        logger.warning("jwt_decode_failure", error=str(exc))
        raise _401 from exc

    if payload.get("type") != "access":
        raise _401

    try:
        user_id = UUID(payload["sub"])
        email: str = payload.get("email", "")
        roles: frozenset[str] = frozenset(payload.get("roles", []))
        tenant_ids: frozenset[UUID] = frozenset(
            UUID(t) for t in payload.get("tenants", [])
        )
    except (KeyError, ValueError) as exc:
        raise _401 from exc

    return UserContext(user_id=user_id, email=email, roles=roles, tenant_ids=tenant_ids)


# ---------------------------------------------------------------------------
# Backwards-compat alias used in older routes
# ---------------------------------------------------------------------------


async def get_current_user_id(
    user: Annotated[UserContext, Depends(get_current_user)],
) -> str:
    return user.user_id.hex


CurrentUserDep = Annotated[str, Depends(get_current_user_id)]
CurrentUser = Annotated[UserContext, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Tenant context
# ---------------------------------------------------------------------------


async def get_tenant_context(
    tenant_id: UUID,
    user: Annotated[UserContext, Depends(get_current_user)],
    db: DbDep,
) -> TenantContext:
    """
    Validates that the authenticated user belongs to the requested tenant.

    Superadmin role bypasses the membership check.
    Raises 403 if forbidden, 404 if tenant missing/soft-deleted.
    """
    is_superadmin = "superadmin" in user.roles

    if not is_superadmin and tenant_id not in user.tenant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this tenant is not permitted.",
        )

    # Deferred import to break potential circular dependency chains.
    # Tenant ORM model lives in the app package (backend/app/db/models/tenant.py).
    # Once that package is consolidated under finspark, update this import.
    from sqlalchemy import select  # noqa: PLC0415

    try:
        from app.db.models.tenant import Tenant  # type: ignore[import]  # noqa: PLC0415
    except ModuleNotFoundError:
        # Fallback: allow startup without app package (tests, isolated dev)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant model not available.",
        )

    result = await db.execute(
        select(Tenant).where(
            Tenant.id == tenant_id.hex,
            Tenant.is_deleted.is_(False),
        )
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found.",
        )

    return TenantContext(tenant_id=tenant_id, user=user, plan=str(tenant.plan))


TenantCtx = Annotated[TenantContext, Depends(get_tenant_context)]


# ---------------------------------------------------------------------------
# Role guard factory
# ---------------------------------------------------------------------------


def require_roles(*required: str):  # type: ignore[no-untyped-def]
    """
    Returns a dependency that asserts the caller holds at least one of
    *required* roles.

    Usage:
        @router.get("/admin-only")
        async def handler(user: Annotated[UserContext, Depends(require_roles("admin"))]):
            ...
    """

    async def _guard(
        user: Annotated[UserContext, Depends(get_current_user)],
    ) -> UserContext:
        if not (user.roles & set(required)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of roles {list(required)} required.",
            )
        return user

    return _guard


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def pagination(
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, description="Items per page")] = 20,
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


PaginationDep = Annotated[PaginationParams, Depends(pagination)]
