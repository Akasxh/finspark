"""
Schemas for document upload, parsing, and extraction results.
Covers BRD, SOW, and API specification documents.
"""
from __future__ import annotations

import mimetypes
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, HttpUrl, field_validator, model_validator

from .common import (
    NonEmptyStr,
    OrchestratorBase,
    ResourceId,
    SemVer,
    TenantId,
    TimestampedMixin,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentType(StrEnum):
    BRD = "brd"
    SOW = "sow"
    API_SPEC = "api_spec"
    UNKNOWN = "unknown"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class ApiSpecFormat(StrEnum):
    OPENAPI_3 = "openapi_3"
    OPENAPI_2 = "swagger_2"
    RAML = "raml"
    ASYNCAPI = "asyncapi"
    GRAPHQL_SDL = "graphql_sdl"
    POSTMAN = "postman"
    UNKNOWN = "unknown"


class ExtractionConfidence(StrEnum):
    HIGH = "high"       # >= 0.85
    MEDIUM = "medium"   # 0.60–0.84
    LOW = "low"         # < 0.60


# ---------------------------------------------------------------------------
# Upload request
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
        "text/markdown",
        "application/json",
        "application/x-yaml",
        "text/yaml",
        "text/x-yaml",
    }
)

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class DocumentUploadRequest(OrchestratorBase):
    tenant_id: TenantId
    document_type: DocumentType
    filename: NonEmptyStr
    content_type: NonEmptyStr
    file_size_bytes: int = Field(..., gt=0, le=MAX_FILE_SIZE_BYTES)
    description: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    # presigned S3 key returned by storage layer; populated after upload
    storage_key: str | None = None

    @field_validator("content_type")
    @classmethod
    def validate_mime(cls, v: str) -> str:
        if v not in ALLOWED_MIME_TYPES:
            raise ValueError(
                f"MIME type '{v}' not allowed. Accepted: {sorted(ALLOWED_MIME_TYPES)}"
            )
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def deduplicate_tags(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(t.lower().strip() for t in v if t.strip()))


class DocumentUploadResponse(OrchestratorBase):
    document_id: ResourceId
    upload_url: HttpUrl
    upload_expires_at: str  # ISO-8601
    storage_key: str


# ---------------------------------------------------------------------------
# Extracted entities from parsing
# ---------------------------------------------------------------------------

class ExtractedEndpoint(OrchestratorBase):
    method: str = Field(..., pattern=r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$")
    path: NonEmptyStr
    summary: str | None = None
    description: str | None = None
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    auth_required: bool = True
    tags: list[str] = Field(default_factory=list)


class ExtractedIntegrationHint(OrchestratorBase):
    """A service/provider identified in the document by the NLP engine."""
    service_name: NonEmptyStr
    service_category: str  # e.g. "credit_bureau", "kyc", "payment_gateway"
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_level: ExtractionConfidence
    source_sentences: list[str] = Field(default_factory=list, max_length=10)
    suggested_adapter_slug: str | None = None

    @model_validator(mode="after")
    def derive_confidence_level(self) -> "ExtractedIntegrationHint":
        if self.confidence >= 0.85:
            object.__setattr__(self, "confidence_level", ExtractionConfidence.HIGH)
        elif self.confidence >= 0.60:
            object.__setattr__(self, "confidence_level", ExtractionConfidence.MEDIUM)
        else:
            object.__setattr__(self, "confidence_level", ExtractionConfidence.LOW)
        return self


class ExtractedAuthRequirement(OrchestratorBase):
    auth_type: str  # "api_key", "oauth2", "mtls", "basic", "hmac"
    scopes: list[str] = Field(default_factory=list)
    credential_fields: list[str] = Field(default_factory=list)
    notes: str | None = None


class ExtractedFieldMapping(OrchestratorBase):
    source_field: NonEmptyStr
    target_field: NonEmptyStr
    data_type: str
    required: bool
    transformation_hint: str | None = None


# ---------------------------------------------------------------------------
# Discriminated union: per-document-type parse results
# ---------------------------------------------------------------------------

class BrdParseResult(OrchestratorBase):
    doc_kind: Literal["brd"] = "brd"
    project_name: str | None = None
    stakeholders: list[str] = Field(default_factory=list)
    integration_hints: list[ExtractedIntegrationHint] = Field(default_factory=list)
    functional_requirements: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    timeline_hints: list[str] = Field(default_factory=list)
    raw_text_preview: str | None = Field(default=None, max_length=5000)


class SowParseResult(OrchestratorBase):
    doc_kind: Literal["sow"] = "sow"
    project_scope: str | None = None
    deliverables: list[str] = Field(default_factory=list)
    integration_hints: list[ExtractedIntegrationHint] = Field(default_factory=list)
    sla_requirements: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list)
    raw_text_preview: str | None = Field(default=None, max_length=5000)


class ApiSpecParseResult(OrchestratorBase):
    doc_kind: Literal["api_spec"] = "api_spec"
    spec_format: ApiSpecFormat
    spec_version: str | None = None  # version declared in the spec itself
    title: str | None = None
    base_url: str | None = None
    endpoints: list[ExtractedEndpoint] = Field(default_factory=list)
    auth_requirements: list[ExtractedAuthRequirement] = Field(default_factory=list)
    schemas_extracted: dict[str, Any] = Field(default_factory=dict)
    integration_hints: list[ExtractedIntegrationHint] = Field(default_factory=list)


ParseResult = Annotated[
    BrdParseResult | SowParseResult | ApiSpecParseResult,
    Field(discriminator="doc_kind"),
]


# ---------------------------------------------------------------------------
# Full document read schema
# ---------------------------------------------------------------------------

class DocumentRead(TimestampedMixin):
    id: ResourceId
    tenant_id: TenantId
    document_type: DocumentType
    filename: NonEmptyStr
    content_type: NonEmptyStr
    file_size_bytes: int
    status: DocumentStatus
    description: str | None
    tags: list[str]
    storage_key: str
    parse_result: ParseResult | None = None
    parse_error: str | None = None
    parse_duration_ms: int | None = None


class DocumentListItem(OrchestratorBase):
    id: ResourceId
    tenant_id: TenantId
    document_type: DocumentType
    filename: NonEmptyStr
    status: DocumentStatus
    tags: list[str]
    created_at: str
