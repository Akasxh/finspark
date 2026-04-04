"""Tests for diff engine accuracy: identity-based list matching and breaking change detection."""

import pytest

from finspark.services.config_engine.diff_engine import ConfigDiffEngine


@pytest.fixture
def engine() -> ConfigDiffEngine:
    return ConfigDiffEngine()


class TestIdentityBasedListMatching:
    def test_field_mappings_matched_by_source_field(self, engine: ConfigDiffEngine) -> None:
        """Adding a new mapping should not report the existing one as modified."""
        a = {
            "field_mappings": [
                {"source_field": "pan", "target_field": "bureau.pan"},
            ]
        }
        b = {
            "field_mappings": [
                {"source_field": "pan", "target_field": "bureau.pan"},
                {"source_field": "dob", "target_field": "bureau.dob"},
            ]
        }
        result = engine.compare(a, b)
        change_types = {d.change_type for d in result.diffs}
        # Only the new item should appear; no spurious modifications
        assert result.total_changes == 1
        assert change_types == {"added"}

    def test_field_mapping_modification_detected(self, engine: ConfigDiffEngine) -> None:
        """Changing target_field for an existing source_field is a modification."""
        a = {
            "field_mappings": [
                {"source_field": "pan", "target_field": "old.target"},
            ]
        }
        b = {
            "field_mappings": [
                {"source_field": "pan", "target_field": "new.target"},
            ]
        }
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert result.diffs[0].change_type == "modified"

    def test_field_mapping_removal_detected(self, engine: ConfigDiffEngine) -> None:
        a = {
            "field_mappings": [
                {"source_field": "pan", "target_field": "bureau.pan"},
                {"source_field": "dob", "target_field": "bureau.dob"},
            ]
        }
        b = {
            "field_mappings": [
                {"source_field": "pan", "target_field": "bureau.pan"},
            ]
        }
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert result.diffs[0].change_type == "removed"

    def test_endpoints_matched_by_path(self, engine: ConfigDiffEngine) -> None:
        """Endpoints use 'path' as identity key."""
        a = {
            "endpoints": [
                {"path": "/score", "method": "POST"},
            ]
        }
        b = {
            "endpoints": [
                {"path": "/score", "method": "POST"},
                {"path": "/report", "method": "GET"},
            ]
        }
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert result.diffs[0].change_type == "added"

    def test_reordering_lists_no_spurious_diff(self, engine: ConfigDiffEngine) -> None:
        """Reordering identity-keyed items produces no diff."""
        a = {
            "field_mappings": [
                {"source_field": "a", "target_field": "x"},
                {"source_field": "b", "target_field": "y"},
            ]
        }
        b = {
            "field_mappings": [
                {"source_field": "b", "target_field": "y"},
                {"source_field": "a", "target_field": "x"},
            ]
        }
        result = engine.compare(a, b)
        assert result.total_changes == 0

    def test_plain_value_list_uses_positional_matching(self, engine: ConfigDiffEngine) -> None:
        """Lists of scalars still use positional comparison."""
        a = {"tags": ["a", "b"]}
        b = {"tags": ["a", "c"]}
        result = engine.compare(a, b)
        assert result.total_changes == 1
        assert result.diffs[0].change_type == "modified"


class TestBreakingChangeDetection:
    def test_version_change_is_breaking(self, engine: ConfigDiffEngine) -> None:
        result = engine.compare({"version": "v1"}, {"version": "v2"})
        assert result.breaking_changes == 1

    def test_version_info_is_not_breaking(self, engine: ConfigDiffEngine) -> None:
        """'version_info' shares the 'version' prefix but is not a breaking path."""
        result = engine.compare({"version_info": "old"}, {"version_info": "new"})
        assert result.breaking_changes == 0

    def test_base_url_change_is_breaking(self, engine: ConfigDiffEngine) -> None:
        result = engine.compare(
            {"base_url": "https://v1.api.com"},
            {"base_url": "https://v2.api.com"},
        )
        assert result.breaking_changes == 1

    def test_auth_type_change_is_breaking(self, engine: ConfigDiffEngine) -> None:
        result = engine.compare(
            {"auth": {"type": "api_key"}},
            {"auth": {"type": "oauth2"}},
        )
        assert result.breaking_changes == 1

    def test_auth_key_change_is_not_breaking(self, engine: ConfigDiffEngine) -> None:
        """Changing auth.key (not auth.type) should not be flagged as breaking."""
        result = engine.compare(
            {"auth": {"type": "api_key", "key": "old"}},
            {"auth": {"type": "api_key", "key": "new"}},
        )
        assert result.breaking_changes == 0

    def test_endpoints_change_is_breaking(self, engine: ConfigDiffEngine) -> None:
        a = {"endpoints": [{"path": "/score", "method": "POST"}]}
        b = {"endpoints": [{"path": "/scores", "method": "POST"}]}
        result = engine.compare(a, b)
        assert result.breaking_changes > 0

    def test_non_breaking_field_change(self, engine: ConfigDiffEngine) -> None:
        result = engine.compare({"timeout_ms": 3000}, {"timeout_ms": 5000})
        assert result.breaking_changes == 0

    def test_exact_segment_boundary_not_prefix(self, engine: ConfigDiffEngine) -> None:
        """'versioning' should not be flagged as breaking (segment boundary check)."""
        result = engine.compare({"versioning": "semver"}, {"versioning": "calver"})
        assert result.breaking_changes == 0
