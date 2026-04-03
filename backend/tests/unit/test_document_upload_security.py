"""
Security tests for the document upload endpoint.

Covers:
- Path traversal attempt in filename is rejected
- Oversized file is rejected with HTTP 413
- Valid upload with a safe filename succeeds (202)
- File extension validated before content is read
"""
from __future__ import annotations

import io
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.unit

_TENANT_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# App fixture with all heavy deps mocked out
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_tenant_ctx():
    from finspark.api.deps import TenantContext, UserContext

    user = UserContext(
        user_id=_USER_ID,
        email="test@example.com",
        roles=frozenset({"admin"}),
        tenant_ids=frozenset({_TENANT_ID}),
    )
    return TenantContext(tenant_id=_TENANT_ID, user=user, plan="enterprise")


@pytest.fixture()
def app_with_overrides(mock_tenant_ctx):
    """Return the FastAPI app with auth + DB deps overridden."""
    from finspark.api.deps import get_db, get_tenant_context
    from finspark.main import create_app

    _app = create_app()

    async def _mock_tenant_ctx():  # type: ignore[return]
        return mock_tenant_ctx

    async def _mock_db():
        yield AsyncMock()

    _app.dependency_overrides[get_tenant_context] = _mock_tenant_ctx
    _app.dependency_overrides[get_db] = _mock_db
    return _app


@pytest.fixture()
async def upload_client(app_with_overrides):
    transport = ASGITransport(app=app_with_overrides)
    # tenant_id query param is required by get_tenant_context; pass it in base URL params
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        params={"tenant_id": str(_TENANT_ID)},
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _multipart(filename: str, content: bytes, content_type: str = "application/pdf"):
    return {"file": (filename, io.BytesIO(content), content_type)}


_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
    b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>\nstream\nBT /F1 12 Tf 72 720 Td (Test) Tj ET\n"
    b"endstream\nendobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
    b"0000000115 00000 n \n0000000266 00000 n \n0000000362 00000 n \n"
    b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n433\n%%EOF"
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_traversal_rejected(upload_client: AsyncClient) -> None:
    """../../etc/passwd style filenames must be sanitised — directory components stripped."""
    response = await upload_client.post(
        "/api/v1/documents/",
        files=_multipart("../../etc/passwd", _MINIMAL_PDF, "application/pdf"),
    )
    # The sanitised name would be "passwd" with no extension, which is not in
    # the allowed extension list and content-type is application/pdf but extension
    # doesn't match — endpoint should reject the unsupported extension.
    # Accept either 400 (bad extension after strip) or 202 with "passwd" as filename
    # (proving the traversal path was stripped).  Either way, no path traversal.
    if response.status_code == status.HTTP_202_ACCEPTED:
        data = response.json()
        assert "/" not in data["filename"], "Directory separator must not appear in stored filename"
        assert ".." not in data["filename"], "Parent directory component must not appear in filename"
    else:
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_path_traversal_pdf_extension_rejected(upload_client: AsyncClient) -> None:
    """Path traversal with a valid extension: directory components must be stripped."""
    response = await upload_client.post(
        "/api/v1/documents/",
        files=_multipart("../../tmp/evil.pdf", _MINIMAL_PDF, "application/pdf"),
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    data = response.json()
    # Stored filename must be just "evil.pdf" — no path components
    assert "/" not in data["filename"]
    assert ".." not in data["filename"]
    assert data["filename"] == "evil.pdf"


@pytest.mark.asyncio
async def test_oversized_file_rejected(upload_client: AsyncClient) -> None:
    """Files exceeding MAX_UPLOAD_SIZE_MB must return 413."""
    from finspark.core.config import settings

    oversized = b"x" * (settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1)
    response = await upload_client.post(
        "/api/v1/documents/",
        files=_multipart("big.pdf", oversized, "application/pdf"),
    )
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert "limit" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_valid_upload_accepted(upload_client: AsyncClient) -> None:
    """A valid PDF upload with a clean filename must return 202."""
    response = await upload_client.post(
        "/api/v1/documents/",
        files=_multipart("integration-spec.pdf", _MINIMAL_PDF, "application/pdf"),
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    data = response.json()
    assert data["filename"] == "integration-spec.pdf"
    assert data["status"] == "pending"
    assert data["size_bytes"] == len(_MINIMAL_PDF)


@pytest.mark.asyncio
async def test_unsupported_extension_rejected(upload_client: AsyncClient) -> None:
    """Files with unsupported extensions and no matching content-type must return 400."""
    response = await upload_client.post(
        "/api/v1/documents/",
        files=_multipart("malware.exe", b"MZ\x90\x00", "application/octet-stream"),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_empty_filename_rejected(upload_client: AsyncClient) -> None:
    """Uploads with no usable filename after sanitisation must return 400."""
    response = await upload_client.post(
        "/api/v1/documents/",
        # Sending just path separators — PurePosixPath("///").name == ""
        files=_multipart("///", _MINIMAL_PDF, "application/pdf"),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
