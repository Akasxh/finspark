"""Integration tests for the /api/v1/lint endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


class TestLintEndpoint:
    @pytest.mark.asyncio
    async def test_lint_non_api_spec_returns_empty(self, client: AsyncClient) -> None:
        """Non-API YAML returns an empty report."""
        response = await client.post(
            "/api/v1/lint/",
            json={"spec_text": "name: test\nversion: 1", "format": "yaml"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        report = data["data"]
        assert report["spectral_available"] is True
        assert len(report["findings"]) == 0

    @pytest.mark.asyncio
    async def test_lint_spectral_unavailable(self, client: AsyncClient) -> None:
        """When Spectral is not installed, report says so."""
        with patch(
            "finspark.services.lint.spectral_linter._check_spectral_available",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = await client.post(
                "/api/v1/lint/",
                json={"spec_text": 'openapi: "3.0.3"\ninfo:\n  title: T', "format": "yaml"},
            )
        assert response.status_code == 200
        data = response.json()
        report = data["data"]
        assert report["spectral_available"] is False
        assert len(report["findings"]) == 1
        assert report["findings"][0]["code"] == "spectral-unavailable"

    @pytest.mark.asyncio
    async def test_lint_returns_findings(self, client: AsyncClient) -> None:
        """POST a known-bad OpenAPI snippet and assert findings are returned."""
        import json

        spectral_output = json.dumps([
            {
                "code": "info-contact",
                "message": "Info object must have \"contact\" object.",
                "severity": 1,
                "path": ["info"],
                "range": {"start": {"line": 1, "character": 0}, "end": {"line": 2, "character": 0}},
            },
        ])

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(spectral_output.encode(), b""))
        mock_proc.returncode = 1

        with (
            patch(
                "finspark.services.lint.spectral_linter._check_spectral_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc),
        ):
            response = await client.post(
                "/api/v1/lint/",
                json={
                    "spec_text": 'openapi: "3.0.3"\ninfo:\n  title: Bad Spec',
                    "format": "yaml",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        report = data["data"]
        assert report["spectral_available"] is True
        assert len(report["findings"]) >= 1
        assert report["warning_count"] >= 1
        finding = report["findings"][0]
        assert finding["code"] == "info-contact"
        assert finding["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_lint_json_format(self, client: AsyncClient) -> None:
        """JSON format spec is accepted."""
        with patch(
            "finspark.services.lint.spectral_linter._check_spectral_available",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = await client.post(
                "/api/v1/lint/",
                json={
                    "spec_text": '{"openapi": "3.0.0", "info": {"title": "T", "version": "1"}}',
                    "format": "json",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["spectral_available"] is False
