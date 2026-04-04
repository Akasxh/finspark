"""Security tests for document upload endpoint."""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


def _make_settings_mock(upload_dir: Path, max_mb: int = 50) -> MagicMock:
    """Return a settings mock with a real upload_dir so SQLAlchemy gets actual ints."""
    mock = MagicMock()
    mock.upload_dir = upload_dir
    mock.max_upload_size_mb = max_mb
    return mock


class TestPathTraversalPrevention:
    @pytest.mark.asyncio
    async def test_path_traversal_filename_stripped(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """../../etc/passwd.pdf must be stored as passwd.pdf, not escape upload_dir."""
        malicious_name = "../../etc/passwd.pdf"
        file_content = b"%PDF-1.4 fake pdf content"

        with patch(
            "finspark.api.routes.documents.settings",
            _make_settings_mock(tmp_path),
        ):
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": (malicious_name, BytesIO(file_content), "application/pdf")},
                params={"doc_type": "brd"},
            )

        # Request must not 500; the stripped filename must not contain traversal chars
        assert response.status_code != 500
        if response.status_code in (200, 201):
            data = response.json()
            filename = data.get("data", {}).get("filename", "")
            assert ".." not in filename
            assert "/" not in filename
        # File must only exist inside tmp_path, never outside
        escaped = tmp_path.parent / "etc" / "passwd.pdf"
        assert not escaped.exists()

    @pytest.mark.asyncio
    async def test_empty_name_after_traversal_strip_rejected(self, client: AsyncClient) -> None:
        """A filename that is purely directory separators yields empty .name → 400."""
        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("/", BytesIO(b"%PDF-1.4"), "application/pdf")},
            params={"doc_type": "brd"},
        )
        assert response.status_code == 400


class TestFileSizeValidation:
    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self, client: AsyncClient, tmp_path: Path) -> None:
        """Files exceeding max_upload_size_mb must return 413."""
        # Patch the limit to 0 MB so a 1-byte file triggers the guard
        oversized = b"x" * 1024

        with patch(
            "finspark.api.routes.documents.settings",
            _make_settings_mock(tmp_path, max_mb=0),
        ):
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("spec.json", BytesIO(oversized), "application/json")},
                params={"doc_type": "api_spec"},
            )

        assert response.status_code == 413
        assert "maximum upload size" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_file_within_limit_not_rejected_for_size(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """A file within the size limit must not be rejected with 413."""
        small = b"name: api\nversion: '1.0'"

        with patch(
            "finspark.api.routes.documents.settings",
            _make_settings_mock(tmp_path, max_mb=50),
        ):
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("spec.yaml", BytesIO(small), "application/yaml")},
                params={"doc_type": "api_spec"},
            )

        assert response.status_code != 413


class TestDocTypeValidation:
    @pytest.mark.asyncio
    async def test_invalid_doc_type_rejected(self, client: AsyncClient) -> None:
        """An unrecognised doc_type must return 400 before any file I/O."""
        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("report.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
            params={"doc_type": "malicious_type"},
        )
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "doc_type" in detail or "invalid" in detail

    @pytest.mark.asyncio
    async def test_valid_doc_types_pass_validation(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Every DocType enum value must pass doc_type validation (no 400 for type)."""
        from finspark.schemas.common import DocType

        content = b"name: api\nversion: '1.0'"

        for dt in [e.value for e in DocType]:
            with patch(
                "finspark.api.routes.documents.settings",
                _make_settings_mock(tmp_path, max_mb=50),
            ):
                response = await client.post(
                    "/api/v1/documents/upload",
                    files={"file": ("spec.yaml", BytesIO(content), "application/yaml")},
                    params={"doc_type": dt},
                )

            detail = response.json().get("detail", "")
            assert not (
                response.status_code == 400 and "doc_type" in str(detail).lower()
            ), f"Valid doc_type '{dt}' was incorrectly rejected: {detail}"
