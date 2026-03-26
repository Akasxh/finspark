"""
Pydantic schemas for the /tenants API surface.

Tenants are the top-level isolation unit.  Superadmins manage tenants;
tenant-scoped users can only read their own tenant.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from finspark.schemas.common import PaginatedResponse


class TenantPlan(str, Enum):
    TRIAL = "trial"
    STANDARD = "standard"
    ENTERPRISE = "enterprise"


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------


class TenantCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(
        ...,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$",
        description="Unique URL-safe identifier",
    )
    plan: TenantPlan = TenantPlan.STANDARD
    settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Feature flags, rate-limit overrides, branding config.",
    )


class TenantUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    plan: TenantPlan | None = None
    settings: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class TenantRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    name: str
    slug: str
    plan: TenantPlan
    settings: dict[str, Any]
    vault_key_id: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


TenantListResponse = PaginatedResponse[TenantRecord]
