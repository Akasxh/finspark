"""Tests for configuration export and template endpoints."""

import json

import pytest
import yaml
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.configuration import Configuration


async def _create_config(db: AsyncSession) -> Configuration:
    """Insert a test configuration into the database."""
    full_config = {
        "base_url": "https://api.test.in/v1",
        "auth": {"type": "api_key"},
        "endpoints": [{"path": "/verify", "method": "POST"}],
        "field_mappings": [
            {"source_field": "pan", "target_field": "pan_number", "confidence": 1.0},
        ],
    }
    config = Configuration(
        tenant_id="test-tenant",
        name="Test Config",
        adapter_version_id="av-001",
        document_id=None,
        status="configured",
        version=1,
        field_mappings=json.dumps(full_config["field_mappings"]),
        full_config=json.dumps(full_config),
    )
    db.add(config)
    await db.flush()
    return config


class TestExportConfiguration:
    @pytest.mark.asyncio
    async def test_export_json(self, client: AsyncClient, db_session: AsyncSession) -> None:
        config = await _create_config(db_session)
        response = await client.get(f"/api/v1/configurations/{config.id}/export?format=json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "attachment" in response.headers["content-disposition"]
        assert ".json" in response.headers["content-disposition"]

        data = response.json()
        assert data["id"] == config.id
        assert data["name"] == "Test Config"
        assert data["version"] == 1
        assert "config" in data
        assert data["config"]["base_url"] == "https://api.test.in/v1"

    @pytest.mark.asyncio
    async def test_export_yaml(self, client: AsyncClient, db_session: AsyncSession) -> None:
        config = await _create_config(db_session)
        response = await client.get(f"/api/v1/configurations/{config.id}/export?format=yaml")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-yaml"
        assert "attachment" in response.headers["content-disposition"]
        assert ".yaml" in response.headers["content-disposition"]

        data = yaml.safe_load(response.text)
        assert data["id"] == config.id
        assert data["name"] == "Test Config"
        assert data["config"]["base_url"] == "https://api.test.in/v1"

    @pytest.mark.asyncio
    async def test_export_default_format_is_json(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        config = await _create_config(db_session)
        response = await client.get(f"/api/v1/configurations/{config.id}/export")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    @pytest.mark.asyncio
    async def test_export_invalid_format(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        config = await _create_config(db_session)
        response = await client.get(f"/api/v1/configurations/{config.id}/export?format=xml")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_export_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/configurations/nonexistent-id/export?format=json")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_empty_config(self, client: AsyncClient, db_session: AsyncSession) -> None:
        config = Configuration(
            tenant_id="test-tenant",
            name="Empty Config",
            adapter_version_id="av-001",
            status="draft",
            version=1,
            full_config=None,
        )
        db_session.add(config)
        await db_session.flush()

        response = await client.get(f"/api/v1/configurations/{config.id}/export?format=json")
        assert response.status_code == 200
        data = response.json()
        assert data["config"] == {}


class TestTemplates:
    @pytest.mark.asyncio
    async def test_list_templates(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/configurations/templates")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        templates = data["data"]
        assert len(templates) == 4
        names = {t["name"] for t in templates}
        assert names == {
            "Credit Bureau Basic",
            "KYC Standard",
            "Payment Gateway",
            "GST Verification",
        }

    @pytest.mark.asyncio
    async def test_template_structure(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/configurations/templates")
        templates = response.json()["data"]
        for t in templates:
            assert "name" in t
            assert "description" in t
            assert "adapter_category" in t
            assert "default_config" in t
            assert isinstance(t["default_config"], dict)
            assert "base_url" in t["default_config"]
            assert "field_mappings" in t["default_config"]

    @pytest.mark.asyncio
    async def test_template_categories(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/configurations/templates")
        templates = response.json()["data"]
        categories = {t["adapter_category"] for t in templates}
        assert categories == {"bureau", "kyc", "payment", "gst"}
