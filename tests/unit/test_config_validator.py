"""Unit tests for the configuration validator."""

from __future__ import annotations

from typing import Any

import pytest

from finspark.services.config_engine.validator import ConfigValidator, ValidationReport


def _valid_config() -> dict[str, Any]:
    """Minimal valid configuration for testing."""
    return {
        "adapter_name": "KYC Provider",
        "version": "v1",
        "base_url": "https://api.kyc.in/v1",
        "auth": {"type": "api_key", "credentials": {}},
        "endpoints": [{"path": "/verify", "method": "POST"}],
        "field_mappings": [
            {"source_field": "pan", "target_field": "pan_number", "confidence": 1.0},
        ],
        "hooks": [
            {"name": "log", "type": "pre_request", "handler": "audit_logger"},
        ],
        "retry_policy": {"max_retries": 3, "backoff_factor": 2},
        "timeout_ms": 30000,
    }


@pytest.fixture
def validator() -> ConfigValidator:
    return ConfigValidator()


class TestRequiredFieldsMapped:
    def test_all_present(self, validator: ConfigValidator) -> None:
        result = validator.required_fields_mapped(_valid_config())
        assert result.passed
        assert result.rule_name == "required_fields_mapped"

    def test_missing_fields(self, validator: ConfigValidator) -> None:
        config = {"adapter_name": "test"}
        result = validator.required_fields_mapped(config)
        assert not result.passed
        assert result.severity == "error"
        assert "Missing required fields" in result.message

    def test_all_mappings_unmapped(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["field_mappings"] = [{"source_field": "x", "target_field": ""}]
        result = validator.required_fields_mapped(config)
        assert not result.passed
        assert "No source fields are mapped" in result.message


class TestAuthConfigured:
    def test_valid_auth(self, validator: ConfigValidator) -> None:
        result = validator.auth_configured(_valid_config())
        assert result.passed

    def test_missing_auth(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        del config["auth"]
        result = validator.auth_configured(config)
        assert not result.passed
        assert result.severity == "error"

    def test_invalid_auth_type(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["auth"] = {"type": "magic_token"}
        result = validator.auth_configured(config)
        assert not result.passed
        assert "Unknown auth type" in result.message

    @pytest.mark.parametrize("auth_type", ["api_key", "oauth2", "bearer", "basic", "jwt", "hmac"])
    def test_all_valid_auth_types(self, validator: ConfigValidator, auth_type: str) -> None:
        config = _valid_config()
        config["auth"] = {"type": auth_type}
        result = validator.auth_configured(config)
        assert result.passed


class TestEndpointsReachable:
    def test_valid_endpoints(self, validator: ConfigValidator) -> None:
        result = validator.endpoints_reachable(_valid_config())
        assert result.passed

    def test_no_endpoints(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["endpoints"] = []
        result = validator.endpoints_reachable(config)
        assert not result.passed
        assert result.severity == "error"

    def test_empty_path(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["endpoints"] = [{"path": "", "method": "POST"}]
        result = validator.endpoints_reachable(config)
        assert not result.passed

    def test_invalid_method(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["endpoints"] = [{"path": "/verify", "method": "YEET"}]
        result = validator.endpoints_reachable(config)
        assert not result.passed
        assert "invalid method" in result.message


class TestHooksValid:
    def test_valid_hooks(self, validator: ConfigValidator) -> None:
        result = validator.hooks_valid(_valid_config())
        assert result.passed

    def test_no_hooks_is_ok(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["hooks"] = []
        result = validator.hooks_valid(config)
        assert result.passed

    def test_invalid_hook_type(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["hooks"] = [{"name": "x", "type": "invalid_phase", "handler": "h"}]
        result = validator.hooks_valid(config)
        assert not result.passed

    def test_missing_handler(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["hooks"] = [{"name": "x", "type": "pre_request"}]
        result = validator.hooks_valid(config)
        assert not result.passed
        assert result.severity == "error"

    def test_hook_type_from_hook_type_key(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["hooks"] = [{"name": "x", "hook_type": "post_response", "handler": "h"}]
        result = validator.hooks_valid(config)
        assert result.passed


class TestRetryPolicyValid:
    def test_valid_policy(self, validator: ConfigValidator) -> None:
        result = validator.retry_policy_valid(_valid_config())
        assert result.passed

    def test_no_policy_is_ok(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        del config["retry_policy"]
        result = validator.retry_policy_valid(config)
        assert result.passed

    def test_excessive_retries(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["retry_policy"] = {"max_retries": 99}
        result = validator.retry_policy_valid(config)
        assert not result.passed
        assert result.severity == "error"

    def test_negative_retries(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["retry_policy"] = {"max_retries": -1}
        result = validator.retry_policy_valid(config)
        assert not result.passed

    def test_negative_backoff(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["retry_policy"] = {"max_retries": 3, "backoff_factor": -1}
        result = validator.retry_policy_valid(config)
        assert not result.passed


class TestTimeoutReasonable:
    def test_valid_timeout(self, validator: ConfigValidator) -> None:
        result = validator.timeout_reasonable(_valid_config())
        assert result.passed

    def test_missing_timeout(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        del config["timeout_ms"]
        result = validator.timeout_reasonable(config)
        assert not result.passed
        assert result.severity == "warning"

    def test_too_low(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["timeout_ms"] = 10
        result = validator.timeout_reasonable(config)
        assert not result.passed

    def test_too_high(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["timeout_ms"] = 999_999
        result = validator.timeout_reasonable(config)
        assert not result.passed

    def test_non_numeric(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        config["timeout_ms"] = "fast"
        result = validator.timeout_reasonable(config)
        assert not result.passed
        assert result.severity == "error"


class TestValidateAll:
    def test_full_valid_config(self, validator: ConfigValidator) -> None:
        report = validator.validate_all(_valid_config())
        assert isinstance(report, ValidationReport)
        assert report.passed
        assert len(report.errors) == 0
        assert len(report.results) == 6

    def test_report_collects_all_failures(self, validator: ConfigValidator) -> None:
        config: dict[str, Any] = {}  # empty config triggers multiple failures
        report = validator.validate_all(config)
        assert not report.passed
        assert len(report.errors) >= 1

    def test_warnings_dont_fail_report(self, validator: ConfigValidator) -> None:
        config = _valid_config()
        del config["timeout_ms"]  # triggers warning, not error
        report = validator.validate_all(config)
        assert report.passed
        assert len(report.warnings) == 1
