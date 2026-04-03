"""
POST   /adapters/                          — register a new adapter version
GET    /adapters/                          — list all adapters (filtered by kind/tenant)
GET    /adapters/{adapter_id}              — get adapter detail
PUT    /adapters/{adapter_id}              — full update
PATCH  /adapters/{adapter_id}             — partial update
DELETE /adapters/{adapter_id}             — soft-delete
GET    /adapters/{adapter_id}/versions    — list all semver versions
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from finspark.api.deps import (
    CurrentUser,
    DbDep,
    PaginationDep,
    UserContext,
    require_roles,
)
from finspark.integrations.types import AdapterKind
from finspark.schemas.adapters import (
    AdapterCreate,
    AdapterListResponse,
    AdapterRecord,
    AdapterUpdate,
    AdapterVersionListResponse,
)
from finspark.schemas.common import MessageResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/adapters", tags=["Adapters"])


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=AdapterRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new adapter or adapter version",
    description=(
        "Registers an adapter definition in the registry.  If an adapter "
        "with the same `name` + `kind` already exists, a new version entry "
        "is created.  SemVer ordering is enforced — you cannot register a "
        "version lower than the current latest."
    ),
    responses={
        201: {"description": "Adapter registered."},
        409: {"description": "Version already exists."},
        403: {"description": "Only admins may register adapters."},
    },
)
async def create_adapter(
    body: AdapterCreate,
    db: DbDep,
    _user: Annotated[UserContext, Depends(require_roles("admin", "superadmin"))],
) -> AdapterRecord:
    # TODO: persist adapter record, enforce version uniqueness
    now = datetime.utcnow()
    return AdapterRecord(
        id=uuid.uuid4(),
        name=body.name,
        kind=body.kind,
        version=body.version,
        auth_type=body.auth_type,
        base_url=body.base_url,
        endpoints=body.endpoints,
        capabilities=body.capabilities,
        meta=body.meta,
        is_active=body.is_active,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=AdapterListResponse,
    summary="List adapter registry",
    description="Returns all active adapters.  Filter by `kind` for type-specific queries.",
    responses={200: {"description": "Paginated adapter list."}},
)
async def list_adapters(
    db: DbDep,
    _user: CurrentUser,
    pagination: PaginationDep,
    kind: Annotated[AdapterKind | None, Query(description="Filter by adapter kind")] = None,
    active_only: Annotated[bool, Query(description="Exclude inactive adapters")] = True,
) -> AdapterListResponse:
    # TODO: query adapter registry
    return AdapterListResponse(
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
    "/{adapter_id}",
    response_model=AdapterRecord,
    summary="Get adapter detail",
    responses={
        200: {"description": "Adapter record."},
        404: {"description": "Adapter not found."},
    },
)
async def get_adapter(
    adapter_id: UUID,
    db: DbDep,
    _user: CurrentUser,
) -> AdapterRecord:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Adapter {adapter_id} not found.",
    )


# ---------------------------------------------------------------------------
# Full update
# ---------------------------------------------------------------------------


@router.put(
    "/{adapter_id}",
    response_model=AdapterRecord,
    summary="Replace adapter configuration",
    responses={
        200: {"description": "Updated adapter."},
        404: {"description": "Adapter not found."},
        403: {"description": "Admin required."},
    },
)
async def replace_adapter(
    adapter_id: UUID,
    body: AdapterCreate,
    db: DbDep,
    _user: Annotated[UserContext, Depends(require_roles("admin", "superadmin"))],
) -> AdapterRecord:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Adapter {adapter_id} not found.",
    )


# ---------------------------------------------------------------------------
# Partial update
# ---------------------------------------------------------------------------


@router.patch(
    "/{adapter_id}",
    response_model=AdapterRecord,
    summary="Partially update an adapter",
    responses={
        200: {"description": "Updated adapter."},
        404: {"description": "Adapter not found."},
        403: {"description": "Admin required."},
    },
)
async def patch_adapter(
    adapter_id: UUID,
    body: AdapterUpdate,
    db: DbDep,
    _user: Annotated[UserContext, Depends(require_roles("admin", "superadmin"))],
) -> AdapterRecord:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Adapter {adapter_id} not found.",
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{adapter_id}",
    response_model=MessageResponse,
    summary="Soft-delete an adapter",
    responses={
        200: {"description": "Adapter deactivated."},
        404: {"description": "Adapter not found."},
        409: {"description": "Adapter has active deployments."},
        403: {"description": "Superadmin required."},
    },
)
async def delete_adapter(
    adapter_id: UUID,
    db: DbDep,
    _user: Annotated[UserContext, Depends(require_roles("superadmin"))],
) -> MessageResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Adapter {adapter_id} not found.",
    )


# ---------------------------------------------------------------------------
# List versions
# ---------------------------------------------------------------------------


@router.get(
    "/{adapter_id}/versions",
    response_model=AdapterVersionListResponse,
    summary="List all semver versions of an adapter",
    responses={
        200: {"description": "Version history."},
        404: {"description": "Adapter not found."},
    },
)
async def list_adapter_versions(
    adapter_id: UUID,
    db: DbDep,
    _user: CurrentUser,
    pagination: PaginationDep,
) -> AdapterVersionListResponse:
    return AdapterVersionListResponse(
        items=[],
        total=0,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=0,
    )
