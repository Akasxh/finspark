"""
Pydantic schemas for the /adapters API surface.

Adapters are versioned connector definitions that map a tenant's external
integration (e.g. CIBIL, Razorpay) to the internal orchestration engine.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from finspark.integrations.types import AdapterKind, AuthType
from finspark.schemas.common import PaginatedResponse


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class EndpointSpec(BaseModel):
    path: str = Field(..., description="Relative URL path, e.g. /v1/reports")
    method: str = Field(default="POST", pattern="^(GET|POST|PUT|PATCH|DELETE)$")
    timeout_ms: int = Field(default=5000, ge=100, le=120_000)
    retry_count: int = Field(default=3, ge=0, le=10)
    description: str = ""


class CapabilitySpec(BaseModel):
    name: str
    description: str = ""
    required_fields: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------


class AdapterCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=120)
    kind: AdapterKind
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="SemVer")
    auth_type: AuthType
    base_url: str = Field(..., description="Adapter base URL (no trailing slash)")
    endpoints: list[EndpointSpec] = Field(default_factory=list)
    capabilities: list[CapabilitySpec] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict, description="Arbitrary adapter metadata")
    is_active: bool = True


class AdapterUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    base_url: str | None = None
    auth_type: AuthType | None = None
    endpoints: list[EndpointSpec] | None = None
    capabilities: list[CapabilitySpec] | None = None
    meta: dict[str, Any] | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class AdapterRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    name: str
    kind: AdapterKind
    version: str
    auth_type: AuthType
    base_url: str
    endpoints: list[EndpointSpec]
    capabilities: list[CapabilitySpec]
    meta: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdapterVersionSummary(BaseModel):
    version: str
    adapter_id: UUID
    is_active: bool
    created_at: datetime


AdapterListResponse = PaginatedResponse[AdapterRecord]
AdapterVersionListResponse = PaginatedResponse[AdapterVersionSummary]
