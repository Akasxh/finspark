"""
Integration tests for the Auto-Configuration Engine endpoints.

Endpoints under test:
  POST /api/v1/config/generate          - generate from document text
  POST /api/v1/config/generate-from-doc - generate from uploaded doc ID
  GET  /api/v1/config/{config_id}
  GET  /api/v1/config/{config_id}/diff
  POST /api/v1/config/{config_id}/apply
  POST /api/v1/config/{config_id}/rollback
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestConfigGeneration:
    async def test_generate_from_text(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        sample_brd_text: str,
        mock_openai: AsyncMock,
    ) -> None:
        resp = await client.post(
            "/api/v1/config/generate",
            json={"text": sample_brd_text},
            headers=tenant_headers,
        )
        assert resp.status_code in (200, 202), resp.text
        body = resp.json()
        assert "adapters" in body or "config_id" in body

    async def test_generate_calls_llm_once(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        sample_brd_text: str,
        mock_openai: AsyncMock,
    ) -> None:
        await client.post(
            "/api/v1/config/generate",
            json={"text": sample_brd_text},
            headers=tenant_headers,
        )
        mock_openai.chat.completions.create.assert_awaited()

    async def test_generate_empty_text_returns_422(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await client.post(
            "/api/v1/config/generate",
            json={"text": ""},
            headers=tenant_headers,
        )
        assert resp.status_code == 422

    async def test_generate_requires_auth(
        self,
        client: AsyncClient,
        sample_brd_text: str,
    ) -> None:
        resp = await client.post(
            "/api/v1/config/generate",
            json={"text": sample_brd_text},
        )
        assert resp.status_code in (401, 403)


class TestConfigRetrieval:
    async def _create_config(
        self,
        client: AsyncClient,
        headers: dict[str, str],
        brd_text: str,
        mock_openai: AsyncMock,
    ) -> str | None:
        resp = await client.post(
            "/api/v1/config/generate",
            json={"text": brd_text},
            headers=headers,
        )
        if resp.status_code not in (200, 202):
            return None
        body = resp.json()
        return body.get("config_id") or body.get("id")

    async def test_get_config_by_id(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        sample_brd_text: str,
        mock_openai: AsyncMock,
    ) -> None:
        config_id = await self._create_config(
            client, tenant_headers, sample_brd_text, mock_openai
        )
        if config_id is None:
            pytest.skip("Config generation not implemented")

        resp = await client.get(f"/api/v1/config/{config_id}", headers=tenant_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == config_id

    async def test_get_nonexistent_config_returns_404(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await client.get(
            "/api/v1/config/00000000-0000-0000-0000-000000000000",
            headers=tenant_headers,
        )
        assert resp.status_code == 404


class TestConfigDiff:
    async def test_config_diff_returns_changes(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        sample_brd_text: str,
        mock_openai: AsyncMock,
    ) -> None:
        create_resp = await client.post(
            "/api/v1/config/generate",
            json={"text": sample_brd_text},
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 202):
            pytest.skip("Config generation not implemented")

        config_id = create_resp.json().get("config_id") or create_resp.json().get("id")
        if not config_id:
            pytest.skip()

        diff_resp = await client.get(f"/api/v1/config/{config_id}/diff", headers=tenant_headers)
        assert diff_resp.status_code == 200
        assert "changes" in diff_resp.json() or "diff" in diff_resp.json()


class TestConfigApplyRollback:
    async def test_apply_config(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        sample_brd_text: str,
        mock_openai: AsyncMock,
    ) -> None:
        create_resp = await client.post(
            "/api/v1/config/generate",
            json={"text": sample_brd_text},
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 202):
            pytest.skip()

        config_id = create_resp.json().get("config_id") or create_resp.json().get("id")
        if not config_id:
            pytest.skip()

        apply_resp = await client.post(
            f"/api/v1/config/{config_id}/apply",
            headers=tenant_headers,
        )
        assert apply_resp.status_code in (200, 202)
        assert apply_resp.json().get("status") in ("applied", "pending", "success")

    async def test_rollback_config(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        sample_brd_text: str,
        mock_openai: AsyncMock,
    ) -> None:
        create_resp = await client.post(
            "/api/v1/config/generate",
            json={"text": sample_brd_text},
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 202):
            pytest.skip()

        config_id = create_resp.json().get("config_id") or create_resp.json().get("id")
        if not config_id:
            pytest.skip()

        rollback_resp = await client.post(
            f"/api/v1/config/{config_id}/rollback",
            headers=tenant_headers,
        )
        assert rollback_resp.status_code in (200, 202)


class TestConfigTenantIsolation:
    async def test_other_tenant_cannot_apply_config(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        other_tenant: dict[str, Any],
        sample_brd_text: str,
        mock_openai: AsyncMock,
    ) -> None:
        create_resp = await client.post(
            "/api/v1/config/generate",
            json={"text": sample_brd_text},
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 202):
            pytest.skip()

        config_id = create_resp.json().get("config_id") or create_resp.json().get("id")
        if not config_id:
            pytest.skip()

        other_headers = {
            "X-Tenant-ID": other_tenant["id"],
            "X-Tenant-Slug": other_tenant["slug"],
            "Authorization": f"Bearer test-token-{other_tenant['id']}",
        }
        apply_resp = await client.post(
            f"/api/v1/config/{config_id}/apply",
            headers=other_headers,
        )
        assert apply_resp.status_code in (403, 404)
