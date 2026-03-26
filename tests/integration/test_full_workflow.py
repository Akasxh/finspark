"""Full workflow integration test: create adapter -> upload doc -> parse -> generate config -> validate -> simulate -> audit.

This test proves the complete demo flow works end-to-end through the API layer.
"""

import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.adapter import Adapter, AdapterVersion

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _upload_file_path() -> Path:
    """Return a fixture file with an allowed extension (.yaml)."""
    return FIXTURES_DIR / "sample_openapi.yaml"


async def _seed_cibil_adapter(db_session: AsyncSession) -> str:
    """Seed a CIBIL adapter with a version and return the version ID."""
    adapter = Adapter(
        name="CIBIL Credit Bureau",
        category="bureau",
        description="TransUnion CIBIL credit score and report integration",
        is_active=True,
        icon="credit-card",
    )
    db_session.add(adapter)
    await db_session.flush()

    version = AdapterVersion(
        adapter_id=adapter.id,
        version="v1",
        base_url="https://api.cibil.com/v1",
        auth_type="api_key_certificate",
        endpoints=json.dumps(
            [
                {"path": "/credit-score", "method": "POST", "description": "Fetch credit score"},
                {
                    "path": "/credit-report",
                    "method": "POST",
                    "description": "Fetch detailed report",
                },
            ]
        ),
        request_schema=json.dumps(
            {
                "type": "object",
                "required": ["pan_number", "full_name", "date_of_birth"],
                "properties": {
                    "pan_number": {"type": "string"},
                    "full_name": {"type": "string"},
                    "date_of_birth": {"type": "string", "format": "date"},
                    "mobile_number": {"type": "string"},
                    "email_address": {"type": "string"},
                },
            }
        ),
        response_schema=json.dumps(
            {
                "type": "object",
                "properties": {
                    "credit_score": {"type": "integer"},
                    "enquiry_id": {"type": "string"},
                },
            }
        ),
    )
    db_session.add(version)
    await db_session.flush()
    return version.id


async def _upload_doc(client: AsyncClient) -> str:
    """Upload the YAML fixture via API and return document ID."""
    filepath = _upload_file_path()
    with open(filepath, "rb") as f:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("sample_openapi.yaml", f, "application/x-yaml")},
            params={"doc_type": "api_spec"},
        )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["data"]["id"]


class TestFullWorkflow:
    """Complete workflow through the API: adapter -> document -> config -> simulate -> audit."""

    @pytest.mark.asyncio
    async def test_complete_demo_workflow(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Full happy-path: upload doc, generate config, validate, simulate, verify audit trail."""
        # Step 1: Seed adapter (lifespan seeding doesn't run in tests)
        av_id = await _seed_cibil_adapter(db_session)

        # Verify adapters are listed
        adapters_resp = await client.get("/api/v1/adapters/")
        assert adapters_resp.status_code == 200
        adapters = adapters_resp.json()["data"]["adapters"]
        assert len(adapters) > 0, "No adapters found after seeding"

        cibil = next((a for a in adapters if "CIBIL" in a["name"]), None)
        assert cibil is not None, "CIBIL adapter not found"

        # Step 2: Upload and parse a document
        document_id = await _upload_doc(client)

        # Step 3: Verify the document was persisted and parsed
        doc_resp = await client.get(f"/api/v1/documents/{document_id}")
        assert doc_resp.status_code == 200
        doc_detail = doc_resp.json()["data"]
        assert doc_detail["status"] == "parsed"
        assert doc_detail["parsed_result"] is not None
        assert len(doc_detail["parsed_result"]["fields"]) > 0
        assert len(doc_detail["parsed_result"]["endpoints"]) > 0

        # Step 4: Generate configuration from parsed doc + adapter version
        gen_resp = await client.post(
            "/api/v1/configurations/generate",
            json={
                "document_id": document_id,
                "adapter_version_id": av_id,
                "name": "CIBIL Integration Test Config",
            },
        )
        assert gen_resp.status_code == 200, f"Config generation failed: {gen_resp.text}"
        gen_data = gen_resp.json()
        assert gen_data["success"] is True
        config_id = gen_data["data"]["id"]
        assert gen_data["data"]["status"] == "configured"
        assert len(gen_data["data"]["field_mappings"]) > 0

        # Step 5: Validate the generated configuration
        validate_resp = await client.post(f"/api/v1/configurations/{config_id}/validate")
        assert validate_resp.status_code == 200
        validation = validate_resp.json()["data"]
        assert validation["is_valid"] is True
        assert validation["coverage_score"] > 0.0
        assert len(validation["errors"]) == 0

        # Step 6: Run simulation against the configuration
        sim_resp = await client.post(
            "/api/v1/simulations/run",
            json={
                "configuration_id": config_id,
                "test_type": "full",
            },
        )
        assert sim_resp.status_code == 200, f"Simulation failed: {sim_resp.text}"
        sim_data = sim_resp.json()["data"]
        assert sim_data["total_tests"] > 0
        assert sim_data["passed_tests"] > 0
        assert sim_data["duration_ms"] >= 0

        # Verify individual steps ran
        step_names = [s["step_name"] for s in sim_data["steps"]]
        assert "config_structure_validation" in step_names
        assert "field_mapping_validation" in step_names

        # Step 7: Verify simulation is retrievable
        sim_id = sim_data["id"]
        sim_get_resp = await client.get(f"/api/v1/simulations/{sim_id}")
        assert sim_get_resp.status_code == 200
        assert sim_get_resp.json()["data"]["id"] == sim_id

        # Step 8: Verify audit trail captured all actions
        audit_resp = await client.get("/api/v1/audit/")
        assert audit_resp.status_code == 200
        audit_data = audit_resp.json()["data"]
        audit_actions = [item["action"] for item in audit_data["items"]]
        assert "upload_document" in audit_actions
        assert "generate_config" in audit_actions
        assert "run_simulation" in audit_actions

    @pytest.mark.asyncio
    async def test_document_list_reflects_upload(self, client: AsyncClient) -> None:
        """Documents list endpoint returns the uploaded document."""
        list_resp = await client.get("/api/v1/documents/")
        assert list_resp.status_code == 200
        initial_count = len(list_resp.json()["data"])

        await _upload_doc(client)

        list_resp = await client.get("/api/v1/documents/")
        assert len(list_resp.json()["data"]) == initial_count + 1

    @pytest.mark.asyncio
    async def test_configuration_list_reflects_generation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Configurations list endpoint returns the generated config."""
        av_id = await _seed_cibil_adapter(db_session)
        doc_id = await _upload_doc(client)

        await client.post(
            "/api/v1/configurations/generate",
            json={
                "document_id": doc_id,
                "adapter_version_id": av_id,
                "name": "List Test Config",
            },
        )

        configs_resp = await client.get("/api/v1/configurations/")
        assert configs_resp.status_code == 200
        configs = configs_resp.json()["data"]
        assert any(c["name"] == "List Test Config" for c in configs)

    @pytest.mark.asyncio
    async def test_invalid_file_extension_rejected(self, client: AsyncClient) -> None:
        """Upload with disallowed extension returns 400."""
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("malicious.exe", b"not a real file", "application/octet-stream")},
            params={"doc_type": "brd"},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_generate_config_missing_document_404(self, client: AsyncClient) -> None:
        """Generate config with non-existent document_id returns 404."""
        resp = await client.post(
            "/api/v1/configurations/generate",
            json={
                "document_id": "nonexistent-doc-id",
                "adapter_version_id": "nonexistent-av-id",
                "name": "Should Fail",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_simulate_missing_config_404(self, client: AsyncClient) -> None:
        """Simulate with non-existent configuration_id returns 404."""
        resp = await client.post(
            "/api/v1/simulations/run",
            json={
                "configuration_id": "nonexistent-config-id",
                "test_type": "smoke",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_audit_filters_by_action(self, client: AsyncClient) -> None:
        """Audit endpoint filters by action query parameter."""
        await _upload_doc(client)

        resp = await client.get("/api/v1/audit/", params={"action": "upload_document"})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert all(item["action"] == "upload_document" for item in items)
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_config_export_json(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Export a generated configuration as JSON."""
        av_id = await _seed_cibil_adapter(db_session)
        doc_id = await _upload_doc(client)

        gen_resp = await client.post(
            "/api/v1/configurations/generate",
            json={
                "document_id": doc_id,
                "adapter_version_id": av_id,
                "name": "Export Test Config",
            },
        )
        config_id = gen_resp.json()["data"]["id"]

        export_resp = await client.get(
            f"/api/v1/configurations/{config_id}/export", params={"format": "json"}
        )
        assert export_resp.status_code == 200
        exported = json.loads(export_resp.content)
        assert exported["name"] == "Export Test Config"
        assert "config" in exported
