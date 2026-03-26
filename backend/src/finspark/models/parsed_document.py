"""
Unified data models for the document parsing service.

All parsers (DOCX, PDF, OpenAPI) converge onto these Pydantic models.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DocumentType(str, Enum):
    DOCX = "docx"
    PDF = "pdf"
    OPENAPI_JSON = "openapi_json"
    OPENAPI_YAML = "openapi_yaml"
    UNKNOWN = "unknown"


class SectionCategory(str, Enum):
    REQUIREMENTS = "requirements"
    TECHNICAL_SPEC = "technical_spec"
    SECURITY = "security"
    DATA_FORMAT = "data_format"
    AUTHENTICATION = "authentication"
    ENDPOINTS = "endpoints"
    ERROR_HANDLING = "error_handling"
    OVERVIEW = "overview"
    GLOSSARY = "glossary"
    UNKNOWN = "unknown"


class AuthScheme(str, Enum):
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    NONE = "none"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


# ---------------------------------------------------------------------------
# Fine-grained extracted entities
# ---------------------------------------------------------------------------


class ApiEndpoint(BaseModel):
    path: str
    method: HttpMethod
    summary: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    request_body_schema: dict[str, Any] | None = None
    response_schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    auth_required: bool = False
    source_section: str = ""


class FieldDefinition(BaseModel):
    name: str
    field_type: str = "unknown"
    required: bool = False
    description: str = ""
    example: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)


class AuthRequirement(BaseModel):
    scheme: AuthScheme
    description: str = ""
    header_name: str = ""
    scopes: list[str] = Field(default_factory=list)
    token_url: str = ""


class TableData(BaseModel):
    caption: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    source_section: str = ""


class DocumentSection(BaseModel):
    heading: str
    level: int  # 1 = H1, 2 = H2, etc.
    category: SectionCategory
    content: str
    subsections: list["DocumentSection"] = Field(default_factory=list)
    tables: list[TableData] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    api_paths: list[str] = Field(default_factory=list)
    field_names: list[str] = Field(default_factory=list)


# Enable forward-ref resolution for the recursive model
DocumentSection.model_rebuild()


# ---------------------------------------------------------------------------
# Top-level unified model
# ---------------------------------------------------------------------------


class ParsedDocument(BaseModel):
    """
    Unified output from any document parser.

    Consumers should use `endpoints`, `auth_requirements`, and `field_definitions`
    for structured data; `sections` for context; `raw_text` only as fallback.
    """

    source_filename: str
    doc_type: DocumentType
    title: str = ""
    version: str = ""
    description: str = ""

    # Structural
    sections: list[DocumentSection] = Field(default_factory=list)
    tables: list[TableData] = Field(default_factory=list)

    # Extracted entities
    endpoints: list[ApiEndpoint] = Field(default_factory=list)
    auth_requirements: list[AuthRequirement] = Field(default_factory=list)
    field_definitions: list[FieldDefinition] = Field(default_factory=list)

    # Flat entity lists (union across all sections)
    all_urls: list[str] = Field(default_factory=list)
    all_api_paths: list[str] = Field(default_factory=list)
    all_field_names: list[str] = Field(default_factory=list)

    # OpenAPI-specific
    openapi_version: str = ""
    base_urls: list[str] = Field(default_factory=list)
    external_docs: list[str] = Field(default_factory=list)

    # Stats
    word_count: int = 0
    page_count: int = 0

    # Fallback
    raw_text: str = ""

    # Parse metadata
    parse_errors: list[str] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
