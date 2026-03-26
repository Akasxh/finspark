"""Unit tests for tenant isolation: tenant A's data must not leak to tenant B."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.core.database import get_db
from finspark.main import app
from finspark.models.adapter import Adapter, AdapterVersion

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _upload_file_path() -> Path:
    return FIXTURES_DIR / "sample_openapi.yaml"


async def _build_tenant_client(
    db_session: AsyncSession, tenant_id: str, tenant_name: str
) -> AsyncClient:
    """Build an AsyncClient with specific tenant headers, sharing the test DB session."""

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
    """Upload the YAML fixture and return the document ID."""
    filepath = _upload_file_path()
    with open(filepath, "rb") as f:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": (filename, f, "application/x-yaml")},
            params={"doc_type": "api_spec"},
        )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["data"]["id"]


class TestTenantDocumentIsolation:
    """Tenant A's uploaded documents must not be visible to tenant B."""

    @pytest.mark.asyncio
    async def test_documents_isolated_between_tenants(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            # Tenant A uploads a document
            doc_id = await _upload_doc(client_a, "alpha_spec.yaml")

            # Tenant A can see the document
            a_list = await client_a.get("/api/v1/documents/")
            assert a_list.status_code == 200
            a_docs = a_list.json()["data"]
            assert any(d["id"] == doc_id for d in a_docs)

            # Tenant B cannot see tenant A's document
            b_list = await client_b.get("/api/v1/documents/")
            assert b_list.status_code == 200
            b_docs = b_list.json()["data"]
            assert not any(d["id"] == doc_id for d in b_docs), (
                "Tenant B can see tenant A's document — isolation broken"
            )

            # Tenant B gets 404 when directly accessing tenant A's document
            b_direct = await client_b.get(f"/api/v1/documents/{doc_id}")
            assert b_direct.status_code == 404
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_each_tenant_sees_only_own_documents(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            # Both tenants upload documents
            doc_id_a = await _upload_doc(client_a, "alpha.yaml")
            doc_id_b = await _upload_doc(client_b, "beta.yaml")

            # Tenant A sees only its own
            a_list = await client_a.get("/api/v1/documents/")
            a_ids = {d["id"] for d in a_list.json()["data"]}
            assert doc_id_a in a_ids
            assert doc_id_b not in a_ids

            # Tenant B sees only its own
            b_list = await client_b.get("/api/v1/documents/")
            b_ids = {d["id"] for d in b_list.json()["data"]}
            assert doc_id_b in b_ids
            assert doc_id_a not in b_ids
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()


async def _seed_adapter(db_session: AsyncSession) -> str:
    """Seed a minimal adapter+version and return the version ID."""
    adapter = Adapter(
        name="Test Bureau",
        category="bureau",
        description="Test adapter for isolation tests",
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


class TestTenantConfigurationIsolation:
    """Tenant A's configurations must not be visible to tenant B."""

    @pytest.mark.asyncio
    async def test_configurations_isolated_between_tenants(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            # Seed adapter directly (lifespan seeding doesn't run in tests)
            av_id = await _seed_adapter(db_session)

            # Tenant A: upload doc + generate config
            doc_id_a = await _upload_doc(client_a, "alpha_config.yaml")

            gen_a = await client_a.post(
                "/api/v1/configurations/generate",
                json={
                    "document_id": doc_id_a,
                    "adapter_version_id": av_id,
                    "name": "Alpha Config",
                },
            )
            assert gen_a.status_code == 200, f"Config gen failed: {gen_a.text}"
            config_id_a = gen_a.json()["data"]["id"]

            # Tenant A can see its config
            a_configs = await client_a.get("/api/v1/configurations/")
            a_config_ids = {c["id"] for c in a_configs.json()["data"]}
            assert config_id_a in a_config_ids

            # Tenant B cannot see tenant A's config
            b_configs = await client_b.get("/api/v1/configurations/")
            b_config_ids = {c["id"] for c in b_configs.json()["data"]}
            assert config_id_a not in b_config_ids, (
                "Tenant B can see tenant A's configuration — isolation broken"
            )

            # Tenant B gets 404 for direct access
            b_direct = await client_b.get(f"/api/v1/configurations/{config_id_a}")
            assert b_direct.status_code == 404
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()


class TestTenantAuditIsolation:
    """Tenant A's audit logs must not be visible to tenant B."""

    @pytest.mark.asyncio
    async def test_audit_logs_isolated_between_tenants(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            # Tenant A performs an action that generates audit
            await _upload_doc(client_a, "alpha_audit.yaml")

            # Tenant A sees audit entries
            a_audit = await client_a.get("/api/v1/audit/")
            a_items = a_audit.json()["data"]["items"]
            assert len(a_items) >= 1
            assert all(item["tenant_id"] == "tenant-alpha" for item in a_items)

            # Tenant B sees no audit entries from tenant A
            b_audit = await client_b.get("/api/v1/audit/")
            b_items = b_audit.json()["data"]["items"]
            assert not any(item["tenant_id"] == "tenant-alpha" for item in b_items), (
                "Tenant B can see tenant A's audit logs — isolation broken"
            )
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()


class TestTenantHeaderPropagation:
    """Verify tenant context is correctly set from request headers."""

    @pytest.mark.asyncio
    async def test_response_reflects_tenant_header(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        try:
            resp = await client_a.get("/health")
            assert resp.status_code == 200
            assert resp.headers.get("X-Tenant-ID") == "tenant-alpha"
        finally:
            await client_a.aclose()
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_different_tenants_get_different_headers(
        self,
        db_session: AsyncSession,
    ) -> None:
        client_a = await _build_tenant_client(db_session, "tenant-alpha", "Alpha Corp")
        client_b = await _build_tenant_client(db_session, "tenant-beta", "Beta Inc")
        try:
            resp_a = await client_a.get("/health")
            resp_b = await client_b.get("/health")
            assert resp_a.headers.get("X-Tenant-ID") == "tenant-alpha"
            assert resp_b.headers.get("X-Tenant-ID") == "tenant-beta"
        finally:
            await client_a.aclose()
            await client_b.aclose()
            app.dependency_overrides.clear()
