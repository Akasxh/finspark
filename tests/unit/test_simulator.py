"""Unit tests for the simulation framework."""

import pytest

from finspark.services.simulation.simulator import IntegrationSimulator, MockAPIServer


@pytest.fixture
def simulator() -> IntegrationSimulator:
    return IntegrationSimulator()


@pytest.fixture
def mock_server() -> MockAPIServer:
    return MockAPIServer()


@pytest.fixture
def sample_config() -> dict:
    return {
        "adapter_name": "CIBIL",
        "version": "v1",
        "base_url": "https://api.cibil.com/v1",
        "auth": {"type": "api_key", "credentials": {}},
        "endpoints": [
            {"path": "/credit-score", "method": "POST", "enabled": True},
            {"path": "/credit-report", "method": "POST", "enabled": True},
        ],
        "field_mappings": [
            {"source_field": "pan_number", "target_field": "pan", "confidence": 1.0},
            {"source_field": "customer_name", "target_field": "full_name", "confidence": 0.9},
            {"source_field": "date_of_birth", "target_field": "dob", "confidence": 0.95},
        ],
        "transformation_rules": [],
        "hooks": [
            {
                "name": "log_request",
                "type": "pre_request",
                "handler": "audit_logger",
                "is_active": True,
            },
            {
                "name": "validate_response",
                "type": "post_response",
                "handler": "schema_validator",
                "is_active": True,
            },
        ],
        "retry_policy": {
            "max_retries": 3,
            "backoff_factor": 2,
            "retry_on_status": [429, 500, 502, 503],
        },
        "timeout_ms": 30000,
    }


class TestMockAPIServer:
    def test_generate_response_default(self, mock_server: MockAPIServer) -> None:
        response = mock_server.generate_response(
            {"path": "/test"},
            {"pan_number": "ABCDE1234F"},
        )
        assert response["status"] == "success"
        assert response["code"] == 200

    def test_generate_response_from_schema(self, mock_server: MockAPIServer) -> None:
        schema = {
            "properties": {
                "credit_score": {"type": "integer"},
                "pan_number": {"type": "string"},
                "unknown_field": {"type": "string"},
            },
        }
        response = mock_server.generate_response(
            {"path": "/score"},
            {},
            response_schema=schema,
        )
        assert response["credit_score"] == 750  # From MOCK_DATA
        assert response["pan_number"] == "ABCDE1234F"
        assert "unknown_field" in response


class TestIntegrationSimulator:
    def test_run_full_simulation(
        self, simulator: IntegrationSimulator, sample_config: dict
    ) -> None:
        steps = simulator.run_simulation(sample_config, test_type="full")
        assert len(steps) > 0
        step_names = [s.step_name for s in steps]
        assert "config_structure_validation" in step_names
        assert "field_mapping_validation" in step_names
        assert "auth_config_validation" in step_names

    def test_config_structure_validation_passes(
        self, simulator: IntegrationSimulator, sample_config: dict
    ) -> None:
        steps = simulator.run_simulation(sample_config)
        structure_step = next(s for s in steps if s.step_name == "config_structure_validation")
        assert structure_step.status == "passed"

    def test_field_mapping_validation(
        self, simulator: IntegrationSimulator, sample_config: dict
    ) -> None:
        steps = simulator.run_simulation(sample_config)
        mapping_step = next(s for s in steps if s.step_name == "field_mapping_validation")
        assert mapping_step.status == "passed"
        assert mapping_step.actual_response["coverage"] > 0.5

    def test_auth_validation(self, simulator: IntegrationSimulator, sample_config: dict) -> None:
        steps = simulator.run_simulation(sample_config)
        auth_step = next(s for s in steps if s.step_name == "auth_config_validation")
        assert auth_step.status == "passed"

    def test_simulation_with_missing_fields(self, simulator: IntegrationSimulator) -> None:
        bad_config = {"adapter_name": "test"}
        steps = simulator.run_simulation(bad_config, test_type="smoke")
        structure_step = next(s for s in steps if s.step_name == "config_structure_validation")
        assert structure_step.status == "failed"

    def test_parallel_version_test(
        self, simulator: IntegrationSimulator, sample_config: dict
    ) -> None:
        config_v2 = {**sample_config, "version": "v2", "base_url": "https://api.cibil.com/v2"}
        steps = simulator.run_parallel_version_test(sample_config, config_v2)
        assert len(steps) == 3
        compat_step = next(s for s in steps if s.step_name == "version_compatibility_check")
        assert compat_step.status == "passed"

    def test_hooks_validation(self, simulator: IntegrationSimulator, sample_config: dict) -> None:
        steps = simulator.run_simulation(sample_config)
        hooks_step = next(s for s in steps if s.step_name == "hooks_validation")
        assert hooks_step.status == "passed"

    def test_retry_logic_validation(
        self, simulator: IntegrationSimulator, sample_config: dict
    ) -> None:
        steps = simulator.run_simulation(sample_config, test_type="full")
        retry_step = next(s for s in steps if s.step_name == "retry_logic_validation")
        assert retry_step.status == "passed"

    def test_all_steps_have_duration(
        self, simulator: IntegrationSimulator, sample_config: dict
    ) -> None:
        steps = simulator.run_simulation(sample_config)
        for step in steps:
            assert step.duration_ms >= 0
