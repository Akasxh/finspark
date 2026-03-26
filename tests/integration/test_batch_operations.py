"""Integration tests for batch operation endpoints on configurations."""

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.adapter import Adapter, AdapterVersion
from finspark.models.configuration import Configuration


@pytest_asyncio.fixture
async def seeded_configs(db_session: AsyncSession) -> list[str]:
    """Create an adapter + 3 configurations and return their IDs."""
    adapter = Adapter(
        name="TestAdapter",
        category="bureau",
        is_active=True,
    )
    db_session.add(adapter)
    await db_session.flush()

    av = AdapterVersion(
        adapter_id=adapter.id,
        version="v1",
        base_url="https://api.test.com/v1",
        auth_type="api_key",
        endpoints=json.dumps([{"path": "/check", "method": "POST"}]),
        request_schema=json.dumps({"type": "object", "properties": {"pan": {"type": "string"}}}),
    )
    db_session.add(av)
    await db_session.flush()

    full_valid = json.dumps(
        {
            "adapter_name": "TestAdapter",
            "version": "v1",
            "base_url": "https://api.test.com/v1",
            "auth": {"type": "api_key"},
            "endpoints": [{"path": "/check", "method": "POST"}],
            "field_mappings": [
                {"source_field": "pan_number", "target_field": "pan", "confidence": 0.95},
            ],
            "hooks": [],
            "retry_policy": {"max_retries": 3, "backoff_factor": 2, "retry_on_status": [500, 502]},
            "timeout_ms": 5000,
        }
    )

    full_invalid = json.dumps(
        {
            "adapter_name": "TestAdapter",
            "version": "v1",
            "field_mappings": [],
        }
    )

    ids: list[str] = []
    for i, (name, status, full_cfg, mappings) in enumerate(
        [
            (
                "Config A",
                "configured",
                full_valid,
                json.dumps(
                    [
                        {"source_field": "pan_number", "target_field": "pan", "confidence": 0.95},
                    ]
                ),
            ),
            (
                "Config B",
                "active",
                full_valid,
                json.dumps(
                    [
                        {"source_field": "pan_number", "target_field": "pan", "confidence": 0.8},
                        {"source_field": "name", "target_field": "full_name", "confidence": 0.6},
                    ]
                ),
            ),
            ("Config C", "configured", full_invalid, json.dumps([])),
        ]
    ):
        cfg = Configuration(
            tenant_id="test-tenant",
            name=name,
            adapter_version_id=av.id,
            status=status,
            version=1,
            field_mappings=mappings,
            full_config=full_cfg,
        )
        db_session.add(cfg)
        await db_session.flush()
        ids.append(cfg.id)

    return ids


class TestBatchValidate:
    @pytest.mark.asyncio
    async def test_batch_validate_all(self, client: AsyncClient, seeded_configs: list[str]) -> None:
        response = await client.post(
            "/api/v1/configurations/batch-validate",
            json={"config_ids": seeded_configs},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        items = data["data"]
        assert len(items) == 3

        # First two configs have valid full_config
        assert items[0]["result"]["is_valid"] is True
        assert items[1]["result"]["is_valid"] is True
        # Third config is missing base_url, auth, endpoints
        assert items[2]["result"]["is_valid"] is False
        assert len(items[2]["result"]["errors"]) > 0

    @pytest.mark.asyncio
    async def test_batch_validate_missing_id(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/configurations/batch-validate",
            json={"config_ids": ["nonexistent-id"]},
        )
        assert response.status_code == 200
        items = response.json()["data"]
        assert len(items) == 1
        assert items[0]["error"] == "Configuration not found"
        assert items[0]["result"] is None

    @pytest.mark.asyncio
    async def test_batch_validate_empty_list(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/configurations/batch-validate",
            json={"config_ids": []},
        )
        assert response.status_code == 200
        assert response.json()["data"] == []


class TestBatchSimulate:
    @pytest.mark.asyncio
    async def test_batch_simulate_all(self, client: AsyncClient, seeded_configs: list[str]) -> None:
        response = await client.post(
            "/api/v1/configurations/batch-simulate",
            json={"config_ids": seeded_configs},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        items = data["data"]
        assert len(items) == 3

        for item in items:
            assert item["total_tests"] > 0
            assert item["status"] in ("passed", "failed")
            assert item["error"] is None

    @pytest.mark.asyncio
    async def test_batch_simulate_missing_id(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/configurations/batch-simulate",
            json={"config_ids": ["nonexistent-id"]},
        )
        assert response.status_code == 200
        items = response.json()["data"]
        assert items[0]["error"] == "Configuration not found"
        assert items[0]["total_tests"] == 0


class TestConfigSummary:
    @pytest.mark.asyncio
    async def test_summary_with_configs(
        self, client: AsyncClient, seeded_configs: list[str]
    ) -> None:
        response = await client.get("/api/v1/configurations/summary")
        assert response.status_code == 200
        data = response.json()["data"]

        assert data["total"] == 3
        assert data["by_status"]["configured"] == 2
        assert data["by_status"]["active"] == 1
        # All 3 configs share the same adapter_version_id
        assert len(data["by_adapter"]) == 1
        assert list(data["by_adapter"].values())[0] == 3
        # avg_confidence computed from field_mappings
        assert data["avg_confidence"] > 0

    @pytest.mark.asyncio
    async def test_summary_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/configurations/summary")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0
        assert data["by_status"] == {}
        assert data["by_adapter"] == {}
        assert data["avg_confidence"] == 0.0
