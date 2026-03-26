"""End-to-end integration tests for the full workflow:
Upload Document → Parse → Match Adapter → Generate Config → Simulate → Verify
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

from finspark.services.config_engine.diff_engine import ConfigDiffEngine
from finspark.services.config_engine.field_mapper import ConfigGenerator
from finspark.services.parsing.document_parser import DocumentParser
from finspark.services.simulation.simulator import IntegrationSimulator


class TestE2EDocumentToSimulation:
    """Full end-to-end flow test without API layer."""

    def test_parse_brd_generate_config_simulate(self, sample_brd_text: str) -> None:
        """Test the complete flow: parse → map → generate → simulate."""
        # Step 1: Parse document
        parser = DocumentParser()
        parsed = parser.parse_text(sample_brd_text, doc_type="brd")

        assert parsed.confidence_score > 0.0
        assert len(parsed.fields) > 0
        assert len(parsed.endpoints) > 0
        assert any("CIBIL" in s for s in parsed.services_identified)

        # Step 2: Generate configuration
        generator = ConfigGenerator()
        adapter_version = {
            "adapter_name": "CIBIL Credit Bureau",
            "version": "v1",
            "base_url": "https://api.cibil.com/v1",
            "auth_type": "api_key_certificate",
            "endpoints": [
                {"path": "/credit-score", "method": "POST", "description": "Fetch credit score"},
                {
                    "path": "/credit-report",
                    "method": "POST",
                    "description": "Fetch detailed credit report",
                },
            ],
            "request_schema": {
                "type": "object",
                "required": ["pan_number", "full_name", "date_of_birth"],
                "properties": {
                    "pan_number": {"type": "string"},
                    "full_name": {"type": "string"},
                    "date_of_birth": {"type": "string", "format": "date"},
                    "mobile_number": {"type": "string"},
                    "email_address": {"type": "string"},
                    "address": {"type": "string"},
                    "loan_type": {"type": "string"},
                    "loan_amount": {"type": "number"},
                },
            },
            "response_schema": {},
        }

        config = generator.generate(parsed.model_dump(), adapter_version)

        assert config["adapter_name"] == "CIBIL Credit Bureau"
        assert config["version"] == "v1"
        assert len(config["field_mappings"]) > 0
        assert len(config["hooks"]) > 0
        assert config["retry_policy"]["max_retries"] == 3

        # Check that some fields were mapped with reasonable confidence
        mapped_fields = [m for m in config["field_mappings"] if m.get("target_field")]
        assert len(mapped_fields) > 0

        # Step 3: Run simulation
        simulator = IntegrationSimulator()
        steps = simulator.run_simulation(config, test_type="full")

        assert len(steps) > 0
        passed = sum(1 for s in steps if s.status == "passed")
        assert passed > 0  # At least some tests should pass

        # Step 4: Verify config structure test passed
        structure_step = next(s for s in steps if s.step_name == "config_structure_validation")
        assert structure_step.status == "passed"

    def test_parse_openapi_generate_config_simulate(self, sample_openapi_path: Path) -> None:
        """Test flow with OpenAPI spec input."""
        # Step 1: Parse OpenAPI spec
        parser = DocumentParser()
        parsed = parser.parse(sample_openapi_path)

        assert parsed.doc_type == "api_spec"
        assert parsed.confidence_score >= 0.9
        assert len(parsed.endpoints) >= 3
        assert len(parsed.fields) > 0

        # Step 2: Generate config using parsed fields as source
        generator = ConfigGenerator()
        adapter_version = {
            "adapter_name": "CIBIL Credit Bureau",
            "version": "v2",
            "base_url": "https://api.cibil.com/v2",
            "auth_type": "oauth2",
            "endpoints": [
                {"path": "/scores", "method": "POST"},
                {"path": "/reports", "method": "POST"},
            ],
            "request_schema": {
                "type": "object",
                "required": ["pan_number", "applicant_name", "dob", "consent_id"],
                "properties": {
                    "pan_number": {"type": "string"},
                    "applicant_name": {"type": "string"},
                    "dob": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                    "consent_id": {"type": "string"},
                },
            },
        }

        config = generator.generate(parsed.model_dump(), adapter_version)
        assert config["version"] == "v2"
        assert config["auth"]["type"] == "oauth2"

        # Step 3: Simulate
        simulator = IntegrationSimulator()
        steps = simulator.run_simulation(config)
        passed = sum(1 for s in steps if s.status == "passed")
        total = len(steps)
        assert passed / total >= 0.5  # At least 50% pass rate

    def test_config_diff_between_versions(self) -> None:
        """Test config diff between v1 and v2 configurations."""
        config_v1 = {
            "adapter_name": "CIBIL",
            "version": "v1",
            "base_url": "https://api.cibil.com/v1",
            "auth": {"type": "api_key"},
            "endpoints": [{"path": "/credit-score", "method": "POST"}],
            "field_mappings": [{"source": "pan_number", "target": "pan"}],
        }
        config_v2 = {
            "adapter_name": "CIBIL",
            "version": "v2",
            "base_url": "https://api.cibil.com/v2",
            "auth": {"type": "oauth2"},
            "endpoints": [
                {"path": "/scores", "method": "POST"},
                {"path": "/reports", "method": "POST"},
            ],
            "field_mappings": [
                {"source": "pan_number", "target": "pan"},
                {"source": "consent_id", "target": "consent"},
            ],
        }

        diff_engine = ConfigDiffEngine()
        diff = diff_engine.compare(config_v1, config_v2, "v1-config", "v2-config")

        assert diff.total_changes > 0
        assert diff.breaking_changes > 0  # base_url and auth changed
        assert any(d.path.startswith("version") for d in diff.diffs)

    def test_parallel_version_simulation(self) -> None:
        """Test parallel version testing between v1 and v2."""
        config_v1 = {
            "adapter_name": "CIBIL",
            "version": "v1",
            "base_url": "https://api.cibil.com/v1",
            "auth": {"type": "api_key"},
            "endpoints": [{"path": "/credit-score", "method": "POST"}],
            "field_mappings": [
                {"source_field": "pan_number", "target_field": "pan", "confidence": 1.0},
            ],
        }
        config_v2 = {**config_v1, "version": "v2", "base_url": "https://api.cibil.com/v2"}

        simulator = IntegrationSimulator()
        steps = simulator.run_parallel_version_test(config_v1, config_v2)

        assert len(steps) == 3
        compat = next(s for s in steps if s.step_name == "version_compatibility_check")
        assert compat.status == "passed"


class TestAPIE2EFlow:
    """Test the E2E flow through the API layer."""

    @pytest.mark.asyncio
    async def test_health_and_adapters_available(self, client: AsyncClient) -> None:
        """Verify basic API is working."""
        health = await client.get("/health")
        assert health.status_code == 200

        adapters = await client.get("/api/v1/adapters/")
        assert adapters.status_code == 200

    @pytest.mark.asyncio
    async def test_document_not_found(self, client: AsyncClient) -> None:
        """Test 404 for non-existent document."""
        response = await client.get("/api/v1/documents/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_configuration_not_found(self, client: AsyncClient) -> None:
        """Test 404 for non-existent configuration."""
        response = await client.get("/api/v1/configurations/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_simulation_not_found(self, client: AsyncClient) -> None:
        """Test 404 for non-existent simulation."""
        response = await client.get("/api/v1/simulations/nonexistent-id")
        assert response.status_code == 404
