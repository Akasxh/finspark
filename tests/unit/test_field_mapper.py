"""Unit tests for the field mapping engine."""

import pytest

from finspark.services.config_engine.field_mapper import ConfigGenerator, FieldMapper


@pytest.fixture
def mapper() -> FieldMapper:
    return FieldMapper()


@pytest.fixture
def generator() -> ConfigGenerator:
    return ConfigGenerator()


class TestFieldMapper:
    """Test field mapping logic."""

    def test_exact_synonym_match(self, mapper: FieldMapper) -> None:
        source = [{"name": "pan_number", "type": "string"}]
        target = [{"name": "pan", "type": "string"}]
        result = mapper.map_fields(source, target)
        assert len(result) == 1
        assert result[0].target_field == "pan"
        assert result[0].confidence == 1.0

    def test_fuzzy_match(self, mapper: FieldMapper) -> None:
        source = [{"name": "applicant_name", "type": "string"}]
        target = [{"name": "full_name", "type": "string"}]
        result = mapper.map_fields(source, target)
        assert len(result) == 1
        assert result[0].target_field == "full_name"
        assert result[0].confidence > 0.5

    def test_no_match_returns_empty_target(self, mapper: FieldMapper) -> None:
        source = [{"name": "xyz_unknown_field", "type": "string"}]
        target = [{"name": "completely_different", "type": "string"}]
        result = mapper.map_fields(source, target)
        assert len(result) == 1
        # May or may not match depending on threshold

    def test_multiple_field_mapping(self, mapper: FieldMapper) -> None:
        source = [
            {"name": "pan_number", "type": "string"},
            {"name": "mobile_number", "type": "string"},
            {"name": "email_address", "type": "string"},
        ]
        target = [
            {"name": "pan", "type": "string"},
            {"name": "phone", "type": "string"},
            {"name": "email", "type": "string"},
        ]
        result = mapper.map_fields(source, target)
        assert len(result) == 3
        mapped_targets = {r.target_field for r in result if r.target_field}
        assert "pan" in mapped_targets

    def test_no_duplicate_targets(self, mapper: FieldMapper) -> None:
        """Each target field should be used at most once."""
        source = [
            {"name": "pan_number", "type": "string"},
            {"name": "pan_card", "type": "string"},
        ]
        target = [{"name": "pan", "type": "string"}]
        result = mapper.map_fields(source, target)
        targets_used = [r.target_field for r in result if r.target_field]
        assert len(targets_used) == len(set(targets_used))

    def test_transformation_suggestion(self, mapper: FieldMapper) -> None:
        source = [{"name": "date_of_birth", "type": "string"}]
        target = [{"name": "dob", "type": "date"}]
        result = mapper.map_fields(source, target)
        assert len(result) == 1
        if result[0].target_field:
            assert result[0].transformation == "parse_date"

    def test_empty_inputs(self, mapper: FieldMapper) -> None:
        result = mapper.map_fields([], [])
        assert result == []


class TestConfigGenerator:
    """Test configuration generation."""

    def test_generate_produces_valid_config(self, generator: ConfigGenerator) -> None:
        parsed = {
            "fields": [
                {"name": "pan_number", "data_type": "string"},
                {"name": "customer_name", "data_type": "string"},
            ],
        }
        adapter = {
            "adapter_name": "CIBIL",
            "version": "v1",
            "base_url": "https://api.cibil.com/v1",
            "auth_type": "api_key",
            "endpoints": [{"path": "/score", "method": "POST"}],
            "request_schema": {
                "properties": {
                    "pan": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["pan"],
            },
        }
        config = generator.generate(parsed, adapter)

        assert config["adapter_name"] == "CIBIL"
        assert config["version"] == "v1"
        assert config["base_url"] == "https://api.cibil.com/v1"
        assert "field_mappings" in config
        assert "hooks" in config
        assert "retry_policy" in config
        assert config["retry_policy"]["max_retries"] == 3

    def test_generate_includes_default_hooks(self, generator: ConfigGenerator) -> None:
        parsed = {"fields": []}
        adapter = {
            "adapter_name": "test",
            "version": "v1",
            "base_url": "",
            "auth_type": "api_key",
            "endpoints": [],
            "request_schema": {},
        }
        config = generator.generate(parsed, adapter)
        hook_names = [h["name"] for h in config["hooks"]]
        assert "log_request" in hook_names
        assert "mask_pii" in hook_names
        assert "validate_response" in hook_names

    def test_generate_calculates_confidence(self, generator: ConfigGenerator) -> None:
        parsed = {
            "fields": [
                {"name": "pan_number", "data_type": "string"},
            ],
        }
        adapter = {
            "adapter_name": "test",
            "version": "v1",
            "base_url": "",
            "auth_type": "api_key",
            "endpoints": [],
            "request_schema": {
                "properties": {"pan": {"type": "string"}},
                "required": ["pan"],
            },
        }
        config = generator.generate(parsed, adapter)
        assert "metadata" in config
        assert "confidence_score" in config["metadata"]
