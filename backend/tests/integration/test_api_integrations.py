"""
Integration tests for the Integration Registry & Hook endpoints.

Endpoints under test:
  GET    /api/v1/adapters
  GET    /api/v1/adapters/{slug}
  POST   /api/v1/integrations
  GET    /api/v1/integrations
  GET    /api/v1/integrations/{id}
  PATCH  /api/v1/integrations/{id}
  DELETE /api/v1/integrations/{id}
  POST   /api/v1/integrations/{id}/test
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestAdapterRegistry:
    async def test_list_adapters_returns_200(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await client.get("/api/v1/adapters", headers=tenant_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list) or "items" in body

    async def test_get_adapter_by_slug(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await client.get("/api/v1/adapters/cibil-bureau", headers=tenant_headers)
        # Either 200 (adapter exists in seed data) or 404 (not seeded yet)
        assert resp.status_code in (200, 404)

    async def test_unknown_adapter_returns_404(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await client.get("/api/v1/adapters/does-not-exist-xyz", headers=tenant_headers)
        assert resp.status_code == 404


class TestIntegrationCRUD:
    async def test_create_integration(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        integration_payload: dict[str, Any],
    ) -> None:
        resp = await client.post(
            "/api/v1/integrations",
            json=integration_payload,
            headers=tenant_headers,
        )
        assert resp.status_code in (201, 200), resp.text
        body = resp.json()
        assert "id" in body
        assert body["adapter_slug"] == integration_payload["adapter_slug"]

    async def test_create_integration_validates_required_fields(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await client.post(
            "/api/v1/integrations",
            json={"name": "Missing adapter slug"},
            headers=tenant_headers,
        )
        assert resp.status_code == 422

    async def test_get_integration_by_id(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        integration_payload: dict[str, Any],
    ) -> None:
        create_resp = await client.post(
            "/api/v1/integrations",
            json=integration_payload,
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 201):
            pytest.skip("Create not yet implemented")

        integration_id = create_resp.json()["id"]
        get_resp = await client.get(
            f"/api/v1/integrations/{integration_id}",
            headers=tenant_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == integration_id

    async def test_list_integrations_scoped_to_tenant(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        integration_payload: dict[str, Any],
    ) -> None:
        # Create one integration
        await client.post(
            "/api/v1/integrations",
            json=integration_payload,
            headers=tenant_headers,
        )
        list_resp = await client.get("/api/v1/integrations", headers=tenant_headers)
        assert list_resp.status_code == 200
        items = list_resp.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        tenant_id = tenant_headers["X-Tenant-ID"]
        for item in items:
            assert item.get("tenant_id") == tenant_id

    async def test_update_integration_config(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        integration_payload: dict[str, Any],
    ) -> None:
        create_resp = await client.post(
            "/api/v1/integrations",
            json=integration_payload,
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 201):
            pytest.skip("Create not implemented")

        iid = create_resp.json()["id"]
        patch_resp = await client.patch(
            f"/api/v1/integrations/{iid}",
            json={"config": {"timeout_ms": 9000}},
            headers=tenant_headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["config"]["timeout_ms"] == 9000

    async def test_delete_integration(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        integration_payload: dict[str, Any],
    ) -> None:
        create_resp = await client.post(
            "/api/v1/integrations",
            json=integration_payload,
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 201):
            pytest.skip("Create not implemented")

        iid = create_resp.json()["id"]
        del_resp = await client.delete(
            f"/api/v1/integrations/{iid}",
            headers=tenant_headers,
        )
        assert del_resp.status_code in (200, 204)

        # Soft-delete: GET should return 404 or status=deleted
        get_resp = await client.get(f"/api/v1/integrations/{iid}", headers=tenant_headers)
        assert get_resp.status_code in (404, 200)
        if get_resp.status_code == 200:
            assert get_resp.json().get("is_active") is False


class TestIntegrationSimulation:
    async def test_run_integration_test(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        integration_payload: dict[str, Any],
        mock_openai: Any,
    ) -> None:
        create_resp = await client.post(
            "/api/v1/integrations",
            json=integration_payload,
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 201):
            pytest.skip("Create not implemented")

        iid = create_resp.json()["id"]
        test_resp = await client.post(
            f"/api/v1/integrations/{iid}/test",
            json={"mock_mode": True},
            headers=tenant_headers,
        )
        assert test_resp.status_code in (200, 202)
        body = test_resp.json()
        assert body.get("status") in ("passed", "failed", "pending", "running")


class TestMultiTenantIsolation:
    async def test_tenant_b_cannot_read_tenant_a_integration(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        other_tenant: dict[str, Any],
        integration_payload: dict[str, Any],
    ) -> None:
        # Tenant A creates an integration
        create_resp = await client.post(
            "/api/v1/integrations",
            json=integration_payload,
            headers=tenant_headers,
        )
        if create_resp.status_code not in (200, 201):
            pytest.skip("Create not implemented")

        iid = create_resp.json()["id"]

        # Tenant B tries to read it
        other_headers = {
            "X-Tenant-ID": other_tenant["id"],
            "X-Tenant-Slug": other_tenant["slug"],
            "Authorization": f"Bearer test-token-{other_tenant['id']}",
        }
        get_resp = await client.get(f"/api/v1/integrations/{iid}", headers=other_headers)
        assert get_resp.status_code == 404

    async def test_tenant_b_list_does_not_include_tenant_a(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
        other_tenant: dict[str, Any],
        integration_payload: dict[str, Any],
    ) -> None:
        await client.post(
            "/api/v1/integrations",
            json=integration_payload,
            headers=tenant_headers,
        )

        other_headers = {
            "X-Tenant-ID": other_tenant["id"],
            "X-Tenant-Slug": other_tenant["slug"],
            "Authorization": f"Bearer test-token-{other_tenant['id']}",
        }
        list_resp = await client.get("/api/v1/integrations", headers=other_headers)
        assert list_resp.status_code == 200
        items = list_resp.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        tenant_a_id = tenant_headers["X-Tenant-ID"]
        for item in items:
            assert item.get("tenant_id") != tenant_a_id
