"""
POST   /tenants/             — create tenant (superadmin only)
GET    /tenants/             — list all tenants (superadmin only)
GET    /tenants/{tenant_id}  — get tenant detail (own tenant or superadmin)
PATCH  /tenants/{tenant_id}  — update tenant (superadmin or tenant admin)
DELETE /tenants/{tenant_id}  — soft-delete tenant (superadmin only)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from finspark.api.deps import (
    CurrentUser,
    DbDep,
    PaginationDep,
    UserContext,
    require_roles,
)
from finspark.schemas.common import MessageResponse
from finspark.schemas.tenants import (
    TenantCreate,
    TenantListResponse,
    TenantRecord,
    TenantUpdate,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tenants", tags=["Tenants"])

_SuperAdmin = Annotated[UserContext, Depends(require_roles("superadmin"))]
_AdminOrSuper = Annotated[UserContext, Depends(require_roles("admin", "superadmin"))]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=TenantRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new tenant",
    description=(
        "Provisions a new isolated tenant.  Automatically creates the "
        "row-level-security scope, default settings, and vault key reference.  "
        "Superadmin role is required."
    ),
    responses={
        201: {"description": "Tenant created."},
        409: {"description": "Slug already exists."},
        403: {"description": "Superadmin required."},
    },
)
async def create_tenant(
    body: TenantCreate,
    db: DbDep,
    _user: _SuperAdmin,
) -> TenantRecord:
    # TODO: persist tenant, create vault key, emit audit event
    now = datetime.now(timezone.utc)
    return TenantRecord(
        id=uuid.uuid4(),
        name=body.name,
        slug=body.slug,
        plan=body.plan,
        settings=body.settings,
        vault_key_id=None,
        is_deleted=False,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=TenantListResponse,
    summary="List all tenants",
    description="Superadmin-only.  Returns all non-deleted tenants.",
    responses={
        200: {"description": "Paginated tenant list."},
        403: {"description": "Superadmin required."},
    },
)
async def list_tenants(
    db: DbDep,
    pagination: PaginationDep,
    _user: _SuperAdmin,
) -> TenantListResponse:
    return TenantListResponse(
        items=[],
        total=0,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=0,
    )


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


@router.get(
    "/{tenant_id}",
    response_model=TenantRecord,
    summary="Get tenant detail",
    description=(
        "Superadmins may retrieve any tenant.  "
        "Non-superadmins may only retrieve tenants they belong to."
    ),
    responses={
        200: {"description": "Tenant record."},
        404: {"description": "Tenant not found."},
        403: {"description": "Access denied."},
    },
)
async def get_tenant(
    tenant_id: UUID,
    db: DbDep,
    user: CurrentUser,
) -> TenantRecord:
    is_superadmin = "superadmin" in user.roles
    if not is_superadmin and tenant_id not in user.tenant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this tenant is not permitted.",
        )
    # TODO: load from DB
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Tenant {tenant_id} not found.",
    )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@router.patch(
    "/{tenant_id}",
    response_model=TenantRecord,
    summary="Update tenant settings or plan",
    responses={
        200: {"description": "Updated tenant."},
        404: {"description": "Tenant not found."},
        403: {"description": "Admin or superadmin required."},
    },
)
async def update_tenant(
    tenant_id: UUID,
    body: TenantUpdate,
    db: DbDep,
    user: _AdminOrSuper,
) -> TenantRecord:
    is_superadmin = "superadmin" in user.roles
    if not is_superadmin and tenant_id not in user.tenant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this tenant is not permitted.",
        )
    # TODO: apply update
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Tenant {tenant_id} not found.",
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{tenant_id}",
    response_model=MessageResponse,
    summary="Soft-delete a tenant",
    description=(
        "Marks the tenant as deleted.  All child resources are cascade-soft-deleted.  "
        "This operation is irreversible via the API — contact ops to restore."
    ),
    responses={
        200: {"description": "Tenant deleted."},
        404: {"description": "Tenant not found."},
        409: {"description": "Tenant has active deployments."},
        403: {"description": "Superadmin required."},
    },
)
async def delete_tenant(
    tenant_id: UUID,
    db: DbDep,
    _user: _SuperAdmin,
) -> MessageResponse:
    # TODO: cascade soft-delete, emit audit
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Tenant {tenant_id} not found.",
    )
