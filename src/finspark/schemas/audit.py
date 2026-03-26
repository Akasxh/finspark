"""Schemas for audit logging."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str
    details: dict[str, Any] | None = None
    created_at: datetime


class AuditLogQuery(BaseModel):
    resource_type: str | None = None
    resource_id: str | None = None
    actor: str | None = None
    action: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    page: int = 1
    page_size: int = 50
