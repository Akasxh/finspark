"""
POST   /documents/                   — upload + async-parse document
GET    /documents/                   — list parsed documents (tenant-scoped)
GET    /documents/{document_id}      — full record with parsed payload
DELETE /documents/{document_id}      — soft-delete document
GET    /documents/{document_id}/raw  — stream original file bytes
"""
from __future__ import annotations

import asyncio
import datetime
import uuid
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.api.deps import (
    CurrentUser,
    DbDep,
    PaginationDep,
    TenantCtx,
    UserContext,
    require_roles,
)
from finspark.core.config import settings
from finspark.schemas.common import MessageResponse, PaginatedResponse
from finspark.schemas.documents import (
    DocumentDetail,
    DocumentListResponse,
    DocumentRecord,
    ParseStatus,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

_ALLOWED_EXTENSIONS = {".docx", ".pdf", ".json", ".yaml", ".yml"}
_SUPPORTED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "application/json",
    "application/x-yaml",
    "text/yaml",
    "text/x-yaml",
}
_CHUNK_SIZE = 64 * 1024  # 64 KB read chunks


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=DocumentRecord,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload and parse a document",
    description=(
        "Accepts multipart/form-data with a single `file` field "
        "(DOCX, PDF, OpenAPI JSON/YAML) plus optional JSON `meta`.\n\n"
        "Parsing is asynchronous; the returned record has `status=pending`. "
        "Poll GET /documents/{id} or subscribe to the `document.parsed` hook."
    ),
    responses={
        202: {"description": "Upload accepted, parsing queued."},
        400: {"description": "Unsupported file type or corrupt file."},
        403: {"description": "Tenant access denied."},
        413: {"description": "File exceeds the configured size limit."},  # 413 Content Too Large
    },
)
async def upload_document(
    tenant_ctx: TenantCtx,
    db: DbDep,
    file: Annotated[UploadFile, File(description="DOCX, PDF, or OpenAPI spec file")],
    description: Annotated[str, Form()] = "",
    tags: Annotated[str, Form(description="Comma-separated tag list")] = "",
) -> DocumentRecord:
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # Validate extension BEFORE reading file content
    raw_name = file.filename or ""
    safe_name = PurePosixPath(raw_name).name  # strip any directory components
    if not safe_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )
    suffix = Path(safe_name).suffix.lower()
    ct = file.content_type or ""
    if suffix not in _ALLOWED_EXTENSIONS and ct not in _SUPPORTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: extension='{suffix}' content_type='{ct}'.",
        )

    # Read in chunks to enforce size limit without loading the entire file first
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    # Build a safe on-disk filename: uuid4 prefix prevents collisions and path guessing
    doc_id = uuid.uuid4()
    stored_name = f"{doc_id}{suffix}"

    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    dest_path = (upload_dir / stored_name).resolve()

    # Guard: ensure resolved destination is strictly inside upload_dir
    if not dest_path.is_relative_to(upload_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename.",
        )

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    logger.info(
        "document_upload_accepted",
        doc_id=str(doc_id),
        tenant=str(tenant_ctx.tenant_id),
        original_filename=raw_name,
        stored_name=stored_name,
        size=total,
    )

    # TODO: persist to object storage + enqueue background parse task
    # When parse is invoked, use run_in_executor so it doesn't block the event loop:
    #   loop = asyncio.get_event_loop()
    #   parsed = await loop.run_in_executor(None, parse_document_bytes, content, safe_name)
    # (service layer not yet implemented — returns stub record)
    return DocumentRecord(
        id=doc_id,
        tenant_id=tenant_ctx.tenant_id,
        filename=safe_name,
        content_type=ct,
        size_bytes=total,
        status=ParseStatus.PENDING,
        tags=tag_list,
        description=description,
        uploaded_at=datetime.datetime.now(datetime.UTC),
        parsed_at=None,
        parse_errors=[],
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List parsed documents for a tenant",
    responses={
        200: {"description": "Paginated document records."},
        403: {"description": "Tenant access denied."},
    },
)
async def list_documents(
    tenant_ctx: TenantCtx,
    db: DbDep,
    pagination: PaginationDep,
) -> DocumentListResponse:
    # TODO: query document store
    return DocumentListResponse(
        items=[],
        total=0,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=0,
    )


# ---------------------------------------------------------------------------
# Get detail
# ---------------------------------------------------------------------------


@router.get(
    "/{document_id}",
    response_model=DocumentDetail,
    summary="Retrieve a single document with its parsed payload",
    responses={
        200: {"description": "Full document record."},
        404: {"description": "Document not found."},
        403: {"description": "Tenant access denied."},
    },
)
async def get_document(
    document_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> DocumentDetail:
    # TODO: load from DB, enforce tenant_id isolation
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Document {document_id} not found.",
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{document_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft-delete a document",
    responses={
        200: {"description": "Document marked deleted."},
        404: {"description": "Document not found."},
        403: {"description": "Only admins may delete documents."},
    },
)
async def delete_document(
    document_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
    _user: Annotated[UserContext, Depends(require_roles("admin", "superadmin"))],
) -> MessageResponse:
    # TODO: soft-delete in DB + cancel pending parse if any
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Document {document_id} not found.",
    )


# ---------------------------------------------------------------------------
# Raw file download
# ---------------------------------------------------------------------------


@router.get(
    "/{document_id}/raw",
    summary="Stream the original uploaded file",
    response_class=StreamingResponse,
    responses={
        200: {"description": "Binary file stream."},
        404: {"description": "Document not found."},
        403: {"description": "Tenant access denied."},
    },
)
async def download_document_raw(
    document_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> StreamingResponse:
    # TODO: fetch from object storage and stream
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Document {document_id} not found.",
    )
