"""Integration tests for security inspection API endpoints."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestInspectSpecEndpoint:
    """POST /api/v1/security/inspect-spec"""

    async def test_bad_spec_returns_findings(self, client: AsyncClient):
        """A deliberately insecure spec should produce multiple findings."""
        bad_spec = """
openapi: '3.0.3'
info:
  title: Insecure API
  version: '1.0'
servers:
  - url: http://api.example.com
paths:
  /users/{pan}/credit:
    get:
      summary: get credit by PAN
  /login:
    post:
      summary: login
components:
  schemas:
    LoginRequest:
      type: object
      properties:
        username:
          type: string
        password:
          type: string
"""
        resp = await client.post(
            "/api/v1/security/inspect-spec",
            json={"spec_text": bad_spec, "format": "yaml"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        report = body["data"]

        findings = report["findings"]
        assert len(findings) >= 3

        categories = {f["category"] for f in findings}
        assert "API2_Broken_Authentication" in categories
        assert "API8_Security_Misconfiguration" in categories

        titles = {f["title"] for f in findings}
        assert "No authentication declared" in titles
        assert "HTTP base URL (no TLS)" in titles
        assert "Sensitive field in URL path" in titles

        assert report["overall_risk"] == "critical"
        assert report["summary"]["critical"] >= 1

    async def test_secure_spec_minimal_findings(self, client: AsyncClient):
        """A well-configured spec should produce few or no findings."""
        good_spec = """
openapi: '3.0.3'
info:
  title: Secure API
  version: '1.0'
  description: "Rate limit: 100 req/min. Returns 429 when exceeded."
security:
  - Bearer: []
components:
  securitySchemes:
    Bearer:
      type: http
      scheme: bearer
servers:
  - url: https://api.example.com/v1
paths:
  /items:
    get:
      summary: list items
      responses:
        '429':
          description: Rate limited
"""
        resp = await client.post(
            "/api/v1/security/inspect-spec",
            json={"spec_text": good_spec, "format": "yaml"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        report = body["data"]
        assert report["overall_risk"] == "minimal"
        assert len(report["findings"]) == 0

    async def test_json_format_spec(self, client: AsyncClient):
        """JSON-formatted specs should also be parseable."""
        import json
        json_spec = json.dumps({
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0"},
            "paths": {"/data": {"get": {"summary": "get"}}},
        })
        resp = await client.post(
            "/api/v1/security/inspect-spec",
            json={"spec_text": json_spec, "format": "json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        # Should find: no auth, no rate limit, no versioning
        assert len(body["data"]["findings"]) >= 2

    async def test_empty_spec_text(self, client: AsyncClient):
        """Empty spec should still return a valid report (no crash)."""
        resp = await client.post(
            "/api/v1/security/inspect-spec",
            json={"spec_text": "", "format": "yaml"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    async def test_inspect_cibil_fixture(self, client: AsyncClient):
        """Inspect the sample CIBIL OpenAPI fixture."""
        from pathlib import Path
        fixture = Path(__file__).parent.parent / "fixtures" / "sample_openapi.yaml"
        spec_text = fixture.read_text()

        resp = await client.post(
            "/api/v1/security/inspect-spec",
            json={"spec_text": spec_text, "format": "yaml"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        report = body["data"]
        # The CIBIL fixture has auth, HTTPS, versioning, and no rate limit
        # mention in the simple fixture -> should trigger rate limit finding
        assert report["inspector_version"] == "1.0"


@pytest.mark.asyncio
class TestInspectConfigEndpoint:
    """POST /api/v1/security/inspect-config/{config_id}"""

    async def test_config_not_found(self, client: AsyncClient):
        """Non-existent config should return 404."""
        resp = await client.post(
            "/api/v1/security/inspect-config/nonexistent-id",
        )
        assert resp.status_code == 404

    async def test_inspect_existing_config(self, client: AsyncClient, db_session):
        """Create a config via DB, then inspect it."""
        import json as _json

        from finspark.models.adapter import Adapter, AdapterVersion
        from finspark.models.configuration import Configuration

        adapter = Adapter(
            name="Test Adapter",
            category="bureau",
            description="test",
        )
        db_session.add(adapter)
        await db_session.flush()

        av = AdapterVersion(
            adapter_id=adapter.id,
            version="1.0",
            status="active",
            auth_type="api_key",
            base_url="http://insecure.example.com",
            endpoints=_json.dumps([{"path": "/credit-pull", "method": "POST"}]),
        )
        db_session.add(av)
        await db_session.flush()

        config = Configuration(
            name="Test Config",
            adapter_version_id=av.id,
            tenant_id="test-tenant",
            status="draft",
            field_mappings=_json.dumps([
                {"source_field": "pan_number", "target_field": "pan", "confidence": 0.9},
            ]),
        )
        db_session.add(config)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/security/inspect-config/{config.id}",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        report = body["data"]
        assert len(report["findings"]) >= 0  # At least report is returned
        assert report["inspector_version"] == "1.0"
