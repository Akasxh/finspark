"""Tests that mutation endpoints reject cross-tenant operations with 404."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.core.database import get_db
from finspark.main import app
from finspark.models.adapter import Adapter, AdapterVersion

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


async def _build_tenant_client(
    db_session: AsyncSession, tenant_id: str, tenant_name: str
) -> AsyncClient:
    async def override_get_db():  # noqa: ANN202
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-Tenant-ID"] = tenant_id
    client.headers["X-Tenant-Name"] = tenant_name
    client.headers["X-Tenant-Role"] = "admin"
    return client


async def _upload_doc(client: AsyncClient, filename: str = "spec.yaml") -> str:
    filepath = FIXTURES_DIR / "sample_openapi.yaml"
    with open(filepath, "rb") as f:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": (filename, f, "application/x-yaml")},
            params={"doc_type": "api_spec"},
        )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["data"]["id"]


async def _seed_adapter(db_session: AsyncSession) -> str:
    adapter = Adapter(
        name="Test Bureau",
        category="bureau",
        description="Adapter for mutation isolation tests",
        is_active=True,
    )
    db_session.add(adapter)
    await db_session.flush()

    version = AdapterVersion(
        adapter_id=adapter.id,
        version="v1",
        base_url="https://api.test.com/v1",
        auth_type="api_key",
        endpoints=json.dumps([{"path": "/score", "method": "POST"}]),
        request_schema=json.dumps(
            {
                "type": "object",
                "required": ["pan_number"],
                "properties": {"pan_number": {"type": "string"}},
            }
        ),
    )
    db_session.add(version)
    await db_session.flush()
    return version.id


class TestCrossTenantDocumentDelete:
    """Tenant B must not be able to delete tenant A's documents."""

    @pytest.mark.asyncio
    async def test_delete_other_tenants_document_returns_404(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            doc_id = await _upload_doc(client_a, "alpha_secret.yaml")

            # Tenant B tries to delete tenant A's document
            resp = await client_b.delete(f"/api/v1/documents/{doc_id}")
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code} — "
                "tenant B can delete tenant A's document"
            )

            # Verify document still exists for tenant A
            resp_a = await client_a.get(f"/api/v1/documents/{doc_id}")
            assert resp_a.status_code == 200
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()


class TestCrossTenantConfigurationPatch:
    """Tenant B must not be able to update tenant A's configurations."""

    @pytest.mark.asyncio
    async def test_patch_other_tenants_config_returns_404(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            av_id = await _seed_adapter(db_session)
            doc_id = await _upload_doc(client_a, "alpha_patch.yaml")

            gen = await client_a.post(
                "/api/v1/configurations/generate",
                json={
                    "document_id": doc_id,
                    "adapter_version_id": av_id,
                    "name": "Alpha Config",
                },
            )
            assert gen.status_code == 200
            config_id = gen.json()["data"]["id"]

            # Tenant B tries to patch tenant A's config
            resp = await client_b.patch(
                f"/api/v1/configurations/{config_id}",
                json={"name": "Hijacked Config"},
            )
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code} — "
                "tenant B can patch tenant A's configuration"
            )

            # Verify config unchanged for tenant A
            resp_a = await client_a.get(f"/api/v1/configurations/{config_id}")
            assert resp_a.status_code == 200
            assert resp_a.json()["data"]["name"] == "Alpha Config"
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()


class TestCrossTenantConfigurationTransition:
    """Tenant B must not be able to transition tenant A's configuration state."""

    @pytest.mark.asyncio
    async def test_transition_other_tenants_config_returns_404(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            av_id = await _seed_adapter(db_session)
            doc_id = await _upload_doc(client_a, "alpha_transition.yaml")

            gen = await client_a.post(
                "/api/v1/configurations/generate",
                json={
                    "document_id": doc_id,
                    "adapter_version_id": av_id,
                    "name": "Alpha Transition Config",
                },
            )
            assert gen.status_code == 200
            config_id = gen.json()["data"]["id"]

            # Tenant B tries to transition tenant A's config
            resp = await client_b.post(
                f"/api/v1/configurations/{config_id}/transition",
                json={"target_state": "validating"},
            )
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code} — "
                "tenant B can transition tenant A's configuration"
            )
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()


class TestCrossTenantConfigurationRollback:
    """Tenant B must not be able to rollback tenant A's configuration."""

    @pytest.mark.asyncio
    async def test_rollback_other_tenants_config_returns_404(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            av_id = await _seed_adapter(db_session)
            doc_id = await _upload_doc(client_a, "alpha_rollback.yaml")

            gen = await client_a.post(
                "/api/v1/configurations/generate",
                json={
                    "document_id": doc_id,
                    "adapter_version_id": av_id,
                    "name": "Alpha Rollback Config",
                },
            )
            assert gen.status_code == 200
            config_id = gen.json()["data"]["id"]

            # Tenant B tries to rollback tenant A's config
            resp = await client_b.post(
                f"/api/v1/configurations/{config_id}/rollback",
                json={"target_version": 1},
            )
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code} — "
                "tenant B can rollback tenant A's configuration"
            )
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()
