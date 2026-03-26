"""Unit tests for the configuration diff engine."""

import pytest

from finspark.services.config_engine.diff_engine import ConfigDiffEngine


@pytest.fixture
def engine() -> ConfigDiffEngine:
    return ConfigDiffEngine()


class TestConfigDiffEngine:
    def test_identical_configs_no_diff(self, engine: ConfigDiffEngine) -> None:
        config = {"base_url": "https://api.example.com", "version": "v1"}
        result = engine.compare(config, config)
        assert result.total_changes == 0

    def test_added_field(self, engine: ConfigDiffEngine) -> None:
        a = {"name": "test"}
        b = {"name": "test", "description": "added"}
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert result.diffs[0].change_type == "added"
        assert result.diffs[0].path == "description"

    def test_removed_field(self, engine: ConfigDiffEngine) -> None:
        a = {"name": "test", "description": "will be removed"}
        b = {"name": "test"}
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert result.diffs[0].change_type == "removed"

    def test_modified_field(self, engine: ConfigDiffEngine) -> None:
        a = {"name": "old_name"}
        b = {"name": "new_name"}
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert result.diffs[0].change_type == "modified"
        assert result.diffs[0].old_value == "old_name"
        assert result.diffs[0].new_value == "new_name"

    def test_breaking_change_detection(self, engine: ConfigDiffEngine) -> None:
        a = {"base_url": "https://api.v1.com", "auth": {"type": "api_key"}}
        b = {"base_url": "https://api.v2.com", "auth": {"type": "oauth2"}}
        result = engine.compare(a, b)
        assert result.breaking_changes > 0

    def test_nested_diff(self, engine: ConfigDiffEngine) -> None:
        a = {"auth": {"type": "api_key", "key": "old"}}
        b = {"auth": {"type": "api_key", "key": "new"}}
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert "auth.key" in result.diffs[0].path

    def test_list_diff(self, engine: ConfigDiffEngine) -> None:
        a = {"endpoints": ["/a", "/b"]}
        b = {"endpoints": ["/a", "/c"]}
        result = engine.compare(a, b)
        assert result.total_changes == 1

    def test_list_length_diff(self, engine: ConfigDiffEngine) -> None:
        a = {"items": [1, 2]}
        b = {"items": [1, 2, 3]}
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert result.diffs[0].change_type == "added"

    def test_complex_config_diff(self, engine: ConfigDiffEngine) -> None:
        a = {
            "adapter_name": "CIBIL",
            "version": "v1",
            "base_url": "https://api.cibil.com/v1",
            "auth": {"type": "api_key"},
            "endpoints": [{"path": "/score", "method": "POST"}],
            "field_mappings": [
                {"source": "pan_number", "target": "pan"},
            ],
        }
        b = {
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
        result = engine.compare(a, b, "config-v1", "config-v2")
        assert result.total_changes > 0
        assert result.breaking_changes > 0  # version and base_url changed
        assert result.config_a_id == "config-v1"
        assert result.config_b_id == "config-v2"
