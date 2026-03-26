"""
Pydantic schemas for the /hooks API surface.

Hooks (webhooks) let tenants subscribe to platform events and receive
HTTP callbacks.  Each hook has an HMAC secret for payload signing.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from finspark.schemas.common import PaginatedResponse


class HookEventType(str, Enum):
    DOCUMENT_PARSED = "document.parsed"
    CONFIG_GENERATED = "config.generated"
    CONFIG_DEPLOYED = "config.deployed"
    SIMULATION_COMPLETED = "simulation.completed"
    SIMULATION_FAILED = "simulation.failed"
    ADAPTER_UPDATED = "adapter.updated"
    TENANT_UPDATED = "tenant.updated"


class HookStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"  # too many consecutive delivery failures


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------


class HookCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: UUID
    target_url: AnyHttpUrl
    events: list[HookEventType] = Field(..., min_length=1)
    description: str = ""
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Extra headers sent with every delivery (e.g. auth tokens).",
    )
    retry_count: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=10, ge=1, le=60)


class HookUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_url: AnyHttpUrl | None = None
    events: list[HookEventType] | None = None
    description: str | None = None
    headers: dict[str, str] | None = None
    retry_count: int | None = None
    timeout_seconds: int | None = None
    status: HookStatus | None = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class HookRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    tenant_id: UUID
    target_url: str
    events: list[HookEventType]
    description: str
    headers: dict[str, str]
    retry_count: int
    timeout_seconds: int
    status: HookStatus
    secret_hint: str = Field(
        description="Last 4 chars of the HMAC secret for identification.",
    )
    failure_count: int = 0
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class HookSecret(BaseModel):
    """Returned once on creation; the full secret is never surfaced again."""

    hook_id: UUID
    secret: str = Field(description="Full HMAC-SHA256 signing secret. Store securely.")


class HookDeliveryRecord(BaseModel):
    id: UUID
    hook_id: UUID
    event_type: HookEventType
    payload: dict[str, Any]
    attempt: int
    status_code: int | None
    success: bool
    error: str | None
    delivered_at: datetime


HookListResponse = PaginatedResponse[HookRecord]
HookDeliveryListResponse = PaginatedResponse[HookDeliveryRecord]
