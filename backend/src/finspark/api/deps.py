"""
FastAPI dependency injectors — auth, DB session, tenant context, pagination.

Dependency graph (outer to inner):
  get_db              → yields AsyncSession
  get_current_user    → decodes JWT → UserContext (dev bypass when no token)
  get_tenant_context  → validates tenant membership → TenantContext
  require_roles(...)  → factory for role-assertion guard
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, Header, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.core.config import settings
from finspark.core.db import get_db
from finspark.core.security import decode_token

logger = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Dev-mode defaults
# ---------------------------------------------------------------------------

_DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_DEV_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


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
# Auth — primary dependency (dev bypass when APP_ENV=development)
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)] = None,
) -> UserContext:
    """
    Decode and validate Bearer JWT.

    In development mode, if no token is provided, returns a default dev user
    with admin privileges to allow frontend development without auth setup.
    """
    if credentials is None or credentials.credentials == "":
        if settings.APP_ENV == "development":
            return UserContext(
                user_id=_DEV_USER_ID,
                email="dev@finspark.local",
                roles=frozenset({"admin", "superadmin"}),
                tenant_ids=frozenset({_DEV_TENANT_ID}),
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


CurrentUser = Annotated[UserContext, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Tenant context
# ---------------------------------------------------------------------------


async def get_tenant_context(
    user: Annotated[UserContext, Depends(get_current_user)],
    db: DbDep,
    x_tenant_id: Annotated[str, Header(alias="X-Tenant-ID")] = "default",
) -> TenantContext:
    """
    Resolves tenant context from the X-Tenant-ID header.

    In development mode with the default tenant ID, skips database validation
    and returns a dev tenant context directly.
    """
    if x_tenant_id == "default":
        tenant_id = _DEV_TENANT_ID
    else:
        try:
            tenant_id = UUID(x_tenant_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid X-Tenant-ID header: {x_tenant_id}",
            ) from exc

    is_superadmin = "superadmin" in user.roles

    if not is_superadmin and tenant_id not in user.tenant_ids:
        if settings.APP_ENV != "development":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this tenant is not permitted.",
            )

    if settings.APP_ENV == "development":
        return TenantContext(tenant_id=tenant_id, user=user, plan="standard")

    from sqlalchemy import select  # noqa: PLC0415

    try:
        from finspark.models.tenant import Tenant  # noqa: PLC0415
    except ImportError:
        return TenantContext(tenant_id=tenant_id, user=user, plan="standard")

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
