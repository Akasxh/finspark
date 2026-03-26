"""
Integration tests for the document upload / parsing API endpoints.

Endpoints under test:
  POST /api/v1/documents/upload
  GET  /api/v1/documents/{doc_id}
  POST /api/v1/documents/{doc_id}/analyse

These tests use the rolled-back DB session from conftest.py,
so no data persists between tests.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestDocumentUpload:
    async def test_upload_pdf_returns_201(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        upload_pdf: tuple[str, Any, str],
    ) -> None:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": upload_pdf},
            headers=tenant_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "id" in body
        assert body["status"] in ("pending", "processing", "ready")

    async def test_upload_docx_returns_201(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        upload_docx: tuple[str, Any, str],
    ) -> None:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": upload_docx},
            headers=tenant_headers,
        )
        assert resp.status_code == 201, resp.text

    async def test_upload_requires_auth(
        self,
        client: AsyncClient,
        upload_pdf: tuple[str, Any, str],
    ) -> None:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": upload_pdf},
            # No auth headers
        )
        assert resp.status_code in (401, 403)

    async def test_upload_rejects_unsupported_type(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        import io

        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
            headers=tenant_headers,
        )
        assert resp.status_code == 422

    async def test_upload_rejects_empty_file(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        import io

        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
            headers=tenant_headers,
        )
        assert resp.status_code == 422

    async def test_uploaded_doc_visible_by_same_tenant(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        upload_pdf: tuple[str, Any, str],
    ) -> None:
        upload_resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": upload_pdf},
            headers=tenant_headers,
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        get_resp = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers=tenant_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == doc_id


class TestDocumentAnalysis:
    async def test_analyse_returns_adapters(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        upload_pdf: tuple[str, Any, str],
        mock_openai: Any,
    ) -> None:
        # Upload first
        import io

        from tests.conftest import TEST_DATABASE_URL  # just to reference conftest

        upload_resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": upload_pdf},
            headers=tenant_headers,
        )
        if upload_resp.status_code != 201:
            pytest.skip("Upload endpoint not yet implemented")

        doc_id = upload_resp.json()["id"]
        analyse_resp = await client.post(
            f"/api/v1/documents/{doc_id}/analyse",
            headers=tenant_headers,
        )
        assert analyse_resp.status_code == 200
        body = analyse_resp.json()
        assert "adapters" in body
        assert isinstance(body["adapters"], list)

    async def test_analyse_nonexistent_doc_returns_404(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await client.post(
            "/api/v1/documents/00000000-0000-0000-0000-000000000000/analyse",
            headers=tenant_headers,
        )
        assert resp.status_code == 404


class TestMultiTenantDocumentIsolation:
    """Documents uploaded by tenant A must not be visible to tenant B."""

    async def test_cross_tenant_document_access_returns_404(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        other_tenant: dict[str, Any],
        upload_pdf: tuple[str, Any, str],
    ) -> None:
        import io

        # Tenant A uploads
        upload_resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": upload_pdf},
            headers=tenant_headers,
        )
        if upload_resp.status_code != 201:
            pytest.skip("Upload not implemented")

        doc_id = upload_resp.json()["id"]

        # Tenant B tries to access
        other_headers = {
            "X-Tenant-ID": other_tenant["id"],
            "X-Tenant-Slug": other_tenant["slug"],
            "Authorization": f"Bearer test-token-{other_tenant['id']}",
        }
        get_resp = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers=other_headers,
        )
        assert get_resp.status_code == 404
