"""
Pydantic schemas for the /audit API surface.

Audit logs are append-only.  The API only supports reads (no create/update/delete
from the API surface — writes go through the internal audit service).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from finspark.schemas.common import PaginatedResponse


class AuditAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    DEPLOY = "deploy"
    LOGIN = "login"
    LOGOUT = "logout"
    SIMULATE = "simulate"
    VALIDATE = "validate"
    UPLOAD = "upload"


class AuditOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Query params
# ---------------------------------------------------------------------------


class AuditQueryParams(BaseModel):
    """Mirror of the query parameters accepted by GET /audit."""

    model_config = ConfigDict(populate_by_name=True)

    tenant_id: UUID | None = None
    actor_id: UUID | None = None
    resource_type: str | None = None
    resource_id: UUID | None = None
    action: AuditAction | None = None
    outcome: AuditOutcome | None = None
    from_ts: datetime | None = Field(default=None, alias="from")
    to_ts: datetime | None = Field(default=None, alias="to")


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class AuditRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    tenant_id: UUID
    actor_id: UUID | None
    actor_email: str | None
    action: AuditAction
    resource_type: str
    resource_id: UUID | None
    outcome: AuditOutcome
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    diff: dict[str, Any] | None = Field(
        default=None,
        description="JSON diff of before/after state for mutating actions.",
    )
    created_at: datetime


AuditListResponse = PaginatedResponse[AuditRecord]
