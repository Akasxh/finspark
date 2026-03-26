"""
POST   /hooks/                              — register a webhook
GET    /hooks/                              — list hooks (tenant-scoped)
GET    /hooks/{hook_id}                     — get hook detail
PATCH  /hooks/{hook_id}                    — update hook
DELETE /hooks/{hook_id}                    — delete hook
POST   /hooks/{hook_id}/ping               — send test delivery
GET    /hooks/{hook_id}/deliveries         — delivery history
POST   /hooks/{hook_id}/deliveries/{delivery_id}/retry  — retry a failed delivery
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from finspark.api.deps import (
    CurrentUser,
    DbDep,
    PaginationDep,
    TenantCtx,
    UserContext,
    require_roles,
)
from finspark.schemas.common import MessageResponse
from finspark.schemas.hooks import (
    HookCreate,
    HookDeliveryListResponse,
    HookDeliveryRecord,
    HookListResponse,
    HookRecord,
    HookSecret,
    HookStatus,
    HookUpdate,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/hooks", tags=["Hooks"])


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=HookSecret,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new webhook",
    description=(
        "Creates a webhook subscription for the given event types.  "
        "The response body includes the **full** HMAC-SHA256 signing secret "
        "exactly **once**.  Store it securely — it cannot be retrieved again.  "
        "Verify incoming deliveries with: "
        "`HMAC-SHA256(secret, request_body) == X-FinSpark-Signature`."
    ),
    responses={
        201: {"description": "Hook created; secret returned once."},
        403: {"description": "Tenant access denied."},
        409: {"description": "Duplicate target URL + event combination."},
    },
)
async def create_hook(
    body: HookCreate,
    db: DbDep,
    _user: CurrentUser,
) -> HookSecret:
    hook_id = uuid.uuid4()
    secret = secrets.token_hex(32)  # 256-bit HMAC secret

    # TODO: persist hook (store only secret hash, not plaintext)
    logger.info("hook_created", hook_id=str(hook_id), tenant=str(body.tenant_id))

    return HookSecret(hook_id=hook_id, secret=secret)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=HookListResponse,
    summary="List registered webhooks",
    responses={
        200: {"description": "Paginated hook records."},
        403: {"description": "Tenant access denied."},
    },
)
async def list_hooks(
    tenant_ctx: TenantCtx,
    db: DbDep,
    pagination: PaginationDep,
) -> HookListResponse:
    return HookListResponse(
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
    "/{hook_id}",
    response_model=HookRecord,
    summary="Get hook detail",
    description="The signing secret is never returned after creation.",
    responses={
        200: {"description": "Hook record (no secret)."},
        404: {"description": "Hook not found."},
        403: {"description": "Tenant access denied."},
    },
)
async def get_hook(
    hook_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> HookRecord:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Hook {hook_id} not found.",
    )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@router.patch(
    "/{hook_id}",
    response_model=HookRecord,
    summary="Update webhook configuration",
    responses={
        200: {"description": "Updated hook."},
        404: {"description": "Hook not found."},
        403: {"description": "Tenant access denied."},
    },
)
async def update_hook(
    hook_id: UUID,
    body: HookUpdate,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> HookRecord:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Hook {hook_id} not found.",
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{hook_id}",
    response_model=MessageResponse,
    summary="Delete a webhook",
    responses={
        200: {"description": "Hook deleted."},
        404: {"description": "Hook not found."},
        403: {"description": "Tenant access denied."},
    },
)
async def delete_hook(
    hook_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> MessageResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Hook {hook_id} not found.",
    )


# ---------------------------------------------------------------------------
# Ping (test delivery)
# ---------------------------------------------------------------------------


@router.post(
    "/{hook_id}/ping",
    response_model=MessageResponse,
    summary="Send a test delivery to the webhook target",
    description=(
        "Dispatches a synthetic `ping` event to the hook's target URL.  "
        "Useful for verifying connectivity and HMAC signature validation on the receiver."
    ),
    responses={
        200: {"description": "Ping dispatched."},
        404: {"description": "Hook not found."},
        503: {"description": "Target URL unreachable."},
        403: {"description": "Tenant access denied."},
    },
)
async def ping_hook(
    hook_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> MessageResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Hook {hook_id} not found.",
    )


# ---------------------------------------------------------------------------
# Delivery history
# ---------------------------------------------------------------------------


@router.get(
    "/{hook_id}/deliveries",
    response_model=HookDeliveryListResponse,
    summary="List delivery attempts for a hook",
    responses={
        200: {"description": "Paginated delivery records."},
        404: {"description": "Hook not found."},
        403: {"description": "Tenant access denied."},
    },
)
async def list_hook_deliveries(
    hook_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
    pagination: PaginationDep,
) -> HookDeliveryListResponse:
    return HookDeliveryListResponse(
        items=[],
        total=0,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=0,
    )


# ---------------------------------------------------------------------------
# Retry failed delivery
# ---------------------------------------------------------------------------


@router.post(
    "/{hook_id}/deliveries/{delivery_id}/retry",
    response_model=MessageResponse,
    summary="Retry a failed delivery",
    responses={
        200: {"description": "Retry queued."},
        404: {"description": "Hook or delivery not found."},
        409: {"description": "Delivery was already successful."},
        403: {"description": "Tenant access denied."},
    },
)
async def retry_hook_delivery(
    hook_id: UUID,
    delivery_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> MessageResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Delivery {delivery_id} not found.",
    )
