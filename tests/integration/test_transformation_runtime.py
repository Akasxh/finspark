"""Integration tests for transformation_expr inside the simulator runtime.

Verifies that a configuration with ``transformation_expr`` produces correctly
transformed values when run through :meth:`IntegrationSimulator._build_sample_request`
and that the legacy ``transformation`` enum keeps working as the fallback.
"""

from __future__ import annotations

from finspark.services.simulation.simulator import IntegrationSimulator, MockAPIServer
from finspark.services.transformation import apply_transformation


def _config_with_mapping(
    source: str,
    target: str,
    *,
    transformation_expr: str | None = None,
    transformation: str | None = None,
) -> dict:
    return {
        "adapter_name": "test_adapter",
        "version": "1.0.0",
        "base_url": "https://api.example.com",
        "auth": {"type": "api_key"},
        "endpoints": [],
        "field_mappings": [
            {
                "source_field": source,
                "target_field": target,
                "transformation": transformation,
                "transformation_expr": transformation_expr,
                "confidence": 1.0,
                "is_confirmed": True,
            }
        ],
    }


class TestSimulatorAppliesExpr:
    def test_clamp_high_bound_passes_through(self) -> None:
        """transformation_expr='int(x) | clamp(0, 1000000)' on credit_score=750 returns 750."""
        config = _config_with_mapping(
            source="credit_score",
            target="score",
            transformation_expr="int | clamp(0, 1000000)",
        )
        req = IntegrationSimulator._build_sample_request(config)
        # credit_score mock is 750; clamping to [0, 1_000_000] should pass through.
        assert req["credit_score"] == 750

    def test_clamp_low_bound_clips(self) -> None:
        """A tighter clamp should clip the mock value to the upper bound."""
        config = _config_with_mapping(
            source="credit_score",
            target="score",
            transformation_expr="int | clamp(0, 100)",
        )
        req = IntegrationSimulator._build_sample_request(config)
        assert req["credit_score"] == 100

    def test_expr_takes_precedence_over_enum(self) -> None:
        """When both transformation and transformation_expr are set, expr wins."""
        # 'pan_number' mock is "ABCDE1234F" — legacy "upper" enum would no-op,
        # but the expr 'lower' makes it lowercase. Demonstrates precedence.
        config = _config_with_mapping(
            source="pan_number",
            target="pan",
            transformation="upper",
            transformation_expr="lower",
        )
        req = IntegrationSimulator._build_sample_request(config)
        assert req["pan_number"] == "abcde1234f"

    def test_legacy_enum_still_works_when_expr_blank(self) -> None:
        """transformation_expr=None falls back to legacy enum behaviour."""
        config = _config_with_mapping(
            source="customer_name",
            target="name",
            transformation="upper",
            transformation_expr=None,
        )
        req = IntegrationSimulator._build_sample_request(config)
        # "Rajesh Kumar" -> "RAJESH KUMAR"
        assert req["customer_name"] == "RAJESH KUMAR"

    def test_legacy_enum_still_works_when_expr_empty_string(self) -> None:
        """Empty string transformation_expr is treated the same as None."""
        config = _config_with_mapping(
            source="customer_name",
            target="name",
            transformation="upper",
            transformation_expr="",
        )
        req = IntegrationSimulator._build_sample_request(config)
        assert req["customer_name"] == "RAJESH KUMAR"

    def test_invalid_expr_leaves_value_unchanged(self) -> None:
        """Invalid expressions are logged-and-ignored; the sample value is preserved."""
        config = _config_with_mapping(
            source="customer_name",
            target="name",
            transformation_expr="__import__('os')",
        )
        req = IntegrationSimulator._build_sample_request(config)
        # Should be the raw mock value (unchanged).
        assert req["customer_name"] == MockAPIServer.MOCK_DATA["customer_name"]


class TestApplyTransformationStandalone:
    """End-to-end smoke tests on the public DSL surface."""

    def test_int_clamp_high(self) -> None:
        assert apply_transformation("5000", "int | clamp(0, 1000000)") == 5000

    def test_int_clamp_low(self) -> None:
        assert apply_transformation("5000", "int | clamp(0, 1000)") == 1000

    def test_strip_pipe_int(self) -> None:
        assert apply_transformation("   42   ", "strip | int") == 42

    def test_str_pipe_upper(self) -> None:
        assert apply_transformation(123, "str | upper") == "123"


class TestSimulatorRunsEndToEnd:
    """The full run_simulation() path should not blow up when a mapping has expr."""

    def test_run_simulation_with_expr(self) -> None:
        config = {
            "adapter_name": "test_adapter",
            "version": "1.0.0",
            "base_url": "https://api.example.com",
            "auth": {"type": "api_key", "header": "X-API-Key"},
            "endpoints": [
                {"path": "/v1/verify", "method": "POST", "enabled": True},
            ],
            "field_mappings": [
                {
                    "source_field": "loan_amount",
                    "target_field": "amount",
                    "transformation_expr": "int | clamp(0, 1000000)",
                    "confidence": 0.95,
                    "is_confirmed": True,
                },
            ],
            "hooks": [],
            "retry_policy": {"max_retries": 3, "backoff_factor": 2, "retry_on_status": [500, 502, 503]},
            "timeout_ms": 5000,
        }
        sim = IntegrationSimulator()
        steps = sim.run_simulation(config, test_type="basic")
        # The simulator emits step results. We don't care about pass/fail here —
        # only that the new wire doesn't crash.
        assert len(steps) > 0
        # The endpoint step's request_payload should include the transformed value.
        endpoint_steps = [s for s in steps if s.step_name.startswith("endpoint_test_")]
        assert endpoint_steps, "no endpoint test steps produced"
        payload = endpoint_steps[0].request_payload
        # loan_amount mock is 500000.00 (float). int | clamp(0, 1000000) -> 500000.
        assert payload["loan_amount"] == 500000
