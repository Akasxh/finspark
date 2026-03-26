"""
Shared primitives reused across all schema modules.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Config baseline
# ---------------------------------------------------------------------------

class OrchestratorBase(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=True,
    )


# ---------------------------------------------------------------------------
# Reusable annotated types
# ---------------------------------------------------------------------------

TenantId = Annotated[UUID, Field(description="Tenant UUID (row-level isolation key)")]
ResourceId = Annotated[UUID, Field(description="Primary key of any resource")]
SemVer = Annotated[
    str,
    Field(
        pattern=r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$",
        description="Semantic version string (e.g. 1.2.3 or 2.0.0-beta.1)",
    ),
]
NonEmptyStr = Annotated[str, Field(min_length=1)]
SlugStr = Annotated[
    str,
    Field(
        pattern=r"^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$",
        description="URL-safe lowercase slug",
    ),
]

# ---------------------------------------------------------------------------
# Pagination / envelope
# ---------------------------------------------------------------------------

T = TypeVar("T")


class PageMeta(OrchestratorBase):
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=500)
    pages: int = Field(..., ge=0)


class Page(OrchestratorBase, Generic[T]):
    items: list[T]
    meta: PageMeta


class ErrorDetail(OrchestratorBase):
    code: str
    message: str
    field: str | None = None
    meta: dict[str, Any] | None = None


class ErrorResponse(OrchestratorBase):
    errors: list[ErrorDetail]
    request_id: str | None = None


class SuccessResponse(OrchestratorBase, Generic[T]):
    data: T
    request_id: str | None = None


# ---------------------------------------------------------------------------
# Timestamps mixin for read schemas
# ---------------------------------------------------------------------------

class TimestampedMixin(OrchestratorBase):
    created_at: datetime
    updated_at: datetime


class SoftDeleteMixin(TimestampedMixin):
    deleted_at: datetime | None = None
    is_deleted: bool = False
