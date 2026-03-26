"""
Pydantic schemas for the /documents API surface.

Upload → async parse → stored ParsedDocumentRecord.
Consumers retrieve the record to get the structured ParsedDocument payload.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from finspark.schemas.common import PaginatedResponse


class ParseStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class DocumentUploadMeta(BaseModel):
    """Optional metadata supplied alongside the multipart file upload."""

    model_config = ConfigDict(populate_by_name=True)

    tenant_id: UUID
    tags: list[str] = Field(default_factory=list, description="Free-form labels")
    description: str = ""


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class DocumentRecord(BaseModel):
    """Lightweight record returned immediately after upload (before parse completes)."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    tenant_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: ParseStatus
    tags: list[str]
    description: str
    uploaded_at: datetime
    parsed_at: datetime | None = None
    parse_errors: list[str] = Field(default_factory=list)


class DocumentDetail(DocumentRecord):
    """Full record including the parsed payload."""

    parsed_payload: dict[str, Any] | None = Field(
        default=None,
        description="Serialised finspark.models.parsed_document.ParsedDocument",
    )


DocumentListResponse = PaginatedResponse[DocumentRecord]
