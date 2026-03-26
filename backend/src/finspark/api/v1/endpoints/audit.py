"""
GET  /audit/               — query audit log (tenant-scoped + time range)
GET  /audit/{audit_id}     — get single audit entry

Audit logs are immutable — no write operations exposed through the API.
Internal services write audit records via the AuditService, never via HTTP.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from finspark.api.deps import CurrentUser, DbDep, PaginationDep, TenantCtx
from finspark.schemas.audit import (
    AuditAction,
    AuditListResponse,
    AuditOutcome,
    AuditRecord,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit"])


# ---------------------------------------------------------------------------
# List / query
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=AuditListResponse,
    summary="Query the tenant audit log",
    description=(
        "Returns immutable audit records scoped to the tenant.  "
        "Superadmins may omit `tenant_id` to query across all tenants.  "
        "All filter parameters are ANDed together."
    ),
    responses={
        200: {"description": "Paginated audit records."},
        403: {"description": "Tenant access denied."},
    },
)
async def list_audit_logs(
    tenant_ctx: TenantCtx,
    db: DbDep,
    pagination: PaginationDep,
    actor_id: Annotated[UUID | None, Query(description="Filter by actor user ID")] = None,
    resource_type: Annotated[str | None, Query(description="E.g. document, adapter")] = None,
    resource_id: Annotated[UUID | None, Query(description="Filter by resource UUID")] = None,
    action: Annotated[AuditAction | None, Query(description="Event action type")] = None,
    outcome: Annotated[AuditOutcome | None, Query(description="success | failure | partial")] = None,
    from_ts: Annotated[
        datetime | None,
        Query(alias="from", description="ISO 8601 lower bound (inclusive)"),
    ] = None,
    to_ts: Annotated[
        datetime | None,
        Query(alias="to", description="ISO 8601 upper bound (exclusive)"),
    ] = None,
) -> AuditListResponse:
    # TODO: query audit log with filters
    return AuditListResponse(
        items=[],
        total=0,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=0,
    )


# ---------------------------------------------------------------------------
# Single record
# ---------------------------------------------------------------------------


@router.get(
    "/{audit_id}",
    response_model=AuditRecord,
    summary="Get a single audit log entry",
    responses={
        200: {"description": "Audit record."},
        404: {"description": "Audit entry not found."},
        403: {"description": "Tenant access denied."},
    },
)
async def get_audit_entry(
    audit_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> AuditRecord:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Audit entry {audit_id} not found.",
    )
