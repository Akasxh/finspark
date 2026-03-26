"""Integration tests for health and basic API endpoints."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.adapter import Adapter, AdapterVersion
from finspark.models.configuration import Configuration


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestAdaptersEndpoint:
    @pytest.mark.asyncio
    async def test_list_adapters(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/adapters/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestDocumentsEndpoint:
    @pytest.mark.asyncio
    async def test_list_documents_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/documents/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"] == []


class TestConfigurationsEndpoint:
    @pytest.mark.asyncio
    async def test_list_configurations_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/configurations/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAuditEndpoint:
    @pytest.mark.asyncio
    async def test_query_audit_logs_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/audit/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_header_propagated(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.headers.get("X-Tenant-ID") == "test-tenant"

    @pytest.mark.asyncio
    async def test_response_time_header(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert "X-Response-Time" in response.headers


class TestSimulationStream:
    @pytest.mark.asyncio
    async def test_stream_simulation_sse(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Set up required DB records
        adapter = Adapter(name="Test Adapter", category="bureau")
        db_session.add(adapter)
        await db_session.flush()

        adapter_version = AdapterVersion(adapter_id=adapter.id, version="v1", auth_type="api_key")
        db_session.add(adapter_version)
        await db_session.flush()

        full_config = {
            "adapter_name": "test",
            "version": "v1",
            "base_url": "https://api.test.com",
            "auth": {"type": "api_key"},
            "endpoints": [],
            "field_mappings": [],
        }
        config = Configuration(
            name="Test Config",
            adapter_version_id=adapter_version.id,
            tenant_id="test-tenant",
            full_config=json.dumps(full_config),
        )
        db_session.add(config)
        await db_session.flush()

        response = await client.get(f"/api/v1/simulations/{config.id}/stream")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        body = response.text
        # Should contain step events and a done event
        assert "event: step" in body
        assert "event: done" in body

        # Parse individual SSE events
        events = [line for line in body.strip().split("\n") if line.startswith("data: ")]
        assert len(events) >= 1

        # Verify the last event is the done summary
        done_data = json.loads(events[-1].removeprefix("data: "))
        assert "total_steps" in done_data
        assert done_data["total_steps"] >= 1

        # Verify a step event parses correctly
        step_data = json.loads(events[0].removeprefix("data: "))
        assert "step_name" in step_data
        assert "status" in step_data

    @pytest.mark.asyncio
    async def test_stream_simulation_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/simulations/nonexistent-id/stream")
        assert response.status_code == 404
