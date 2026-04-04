"""
Unit tests for ConfigGenerator.generate in field_mapper.py.

Covers:
- Only request fields (source_section contains "request") go to adapter request schema
- Response fields are mapped separately to adapter response schema
- Unmapped request fields have confidence=0
- Fuzzy matching: source="full_name", target="applicant_name" → matched
- Transformation suggestion: source_type="string", target_type="number" → "parse_number"
"""
from __future__ import annotations

import pytest

from finspark.services.config_engine.field_mapper import (
    ConfigGenerator,
    FieldMapping,
    GeneratedConfig,
    SourceField,
    TargetField,
    _fuzzy_score,
    _suggest_transform,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _fuzzy_score unit tests
# ---------------------------------------------------------------------------


def test_fuzzy_score_exact_match_returns_one() -> None:
    assert _fuzzy_score("pan_number", "pan_number") == 1.0


def test_fuzzy_score_completely_different_returns_zero() -> None:
    score = _fuzzy_score("pan_number", "account_balance")
    assert score == 0.0


def test_fuzzy_score_partial_overlap() -> None:
    # "full_name" vs "applicant_name" — shares "name"
    score = _fuzzy_score("full_name", "applicant_name")
    assert 0.0 < score < 1.0


def test_fuzzy_score_same_word_different_prefix() -> None:
    # "customer_id" vs "applicant_id" — shares "id"
    score = _fuzzy_score("customer_id", "applicant_id")
    assert score > 0.0


def test_fuzzy_score_empty_string_returns_zero() -> None:
    assert _fuzzy_score("", "pan_number") == 0.0
    assert _fuzzy_score("pan_number", "") == 0.0


# ---------------------------------------------------------------------------
# _suggest_transform unit tests
# ---------------------------------------------------------------------------


def test_suggest_transform_string_to_number() -> None:
    assert _suggest_transform("string", "number") == "parse_number"


def test_suggest_transform_string_to_integer() -> None:
    assert _suggest_transform("string", "integer") == "parse_integer"


def test_suggest_transform_string_to_boolean() -> None:
    assert _suggest_transform("string", "boolean") == "parse_boolean"


def test_suggest_transform_number_to_string() -> None:
    assert _suggest_transform("number", "string") == "to_string"


def test_suggest_transform_same_type_returns_none() -> None:
    assert _suggest_transform("string", "string") is None
    assert _suggest_transform("integer", "integer") is None


def test_suggest_transform_unknown_combo_returns_none() -> None:
    assert _suggest_transform("object", "array") is None


def test_suggest_transform_case_insensitive() -> None:
    assert _suggest_transform("STRING", "NUMBER") == "parse_number"


# ---------------------------------------------------------------------------
# Request / response field separation
# ---------------------------------------------------------------------------


class TestRequestResponseSeparation:
    def _make_generator(self) -> ConfigGenerator:
        return ConfigGenerator(
            request_schema_fields=[
                TargetField("pan_number", "string"),
                TargetField("amount", "number"),
                TargetField("customer_id", "string"),
            ],
            response_schema_fields=[
                TargetField("score", "integer"),
                TargetField("report_id", "string"),
            ],
        )

    def test_request_source_fields_go_to_request_mappings(self) -> None:
        gen = self._make_generator()
        source_fields = [
            SourceField("pan_number", "string", source_section="request_body"),
            SourceField("amount", "number", source_section="request_body"),
        ]
        config = gen.generate(source_fields)

        assert len(config.request_mappings) == 2
        assert len(config.response_mappings) == 0
        for m in config.request_mappings:
            assert m.is_request_field is True

    def test_response_source_fields_go_to_response_mappings(self) -> None:
        gen = self._make_generator()
        source_fields = [
            SourceField("score", "integer", source_section="response_200"),
            SourceField("report_id", "string", source_section="response_body"),
        ]
        config = gen.generate(source_fields)

        assert len(config.request_mappings) == 0
        assert len(config.response_mappings) == 2
        for m in config.response_mappings:
            assert m.is_request_field is False

    def test_mixed_source_fields_split_correctly(self) -> None:
        gen = self._make_generator()
        source_fields = [
            SourceField("pan_number", "string", source_section="request_body"),
            SourceField("score", "integer", source_section="response_200"),
        ]
        config = gen.generate(source_fields)

        assert len(config.request_mappings) == 1
        assert len(config.response_mappings) == 1
        assert config.request_mappings[0].source_name == "pan_number"
        assert config.response_mappings[0].source_name == "score"

    def test_source_section_containing_request_is_a_request_field(self) -> None:
        """Various source_section strings that contain 'request' are treated as request."""
        gen = self._make_generator()
        for section in ["request", "request_body", "put_request", "REQUEST_BODY", "my_request"]:
            source_fields = [SourceField("pan_number", "string", source_section=section)]
            config = gen.generate(source_fields)
            assert len(config.request_mappings) == 1, f"section={section!r} should be request"

    def test_source_section_without_request_is_response_field(self) -> None:
        gen = self._make_generator()
        for section in ["response_200", "response", "body", ""]:
            source_fields = [SourceField("score", "integer", source_section=section)]
            config = gen.generate(source_fields)
            assert len(config.response_mappings) == 1, f"section={section!r} should be response"


# ---------------------------------------------------------------------------
# Unmapped fields confidence=0
# ---------------------------------------------------------------------------


class TestUnmappedFields:
    def test_unmapped_request_field_has_confidence_zero(self) -> None:
        gen = ConfigGenerator(
            request_schema_fields=[TargetField("unrelated_xyz", "string")],
        )
        source_fields = [
            SourceField("completely_different_field_name", "string", source_section="request_body")
        ]
        config = gen.generate(source_fields)

        assert len(config.request_mappings) == 1
        mapping = config.request_mappings[0]
        assert mapping.confidence == 0.0
        assert mapping.target_name is None

    def test_unmapped_response_field_has_confidence_zero(self) -> None:
        gen = ConfigGenerator(
            response_schema_fields=[TargetField("report_id", "string")],
        )
        source_fields = [
            SourceField("totally_different_xyz", "string", source_section="response_200")
        ]
        config = gen.generate(source_fields)

        mapping = config.response_mappings[0]
        assert mapping.confidence == 0.0
        assert mapping.target_name is None

    def test_no_target_fields_all_mappings_have_confidence_zero(self) -> None:
        gen = ConfigGenerator()  # empty pools
        source_fields = [
            SourceField("pan_number", "string", source_section="request_body"),
            SourceField("score", "integer", source_section="response"),
        ]
        config = gen.generate(source_fields)

        for m in config.request_mappings + config.response_mappings:
            assert m.confidence == 0.0
            assert m.target_name is None

    def test_empty_source_fields_returns_empty_config(self) -> None:
        gen = ConfigGenerator(
            request_schema_fields=[TargetField("pan_number", "string")],
        )
        config = gen.generate([])
        assert config.request_mappings == []
        assert config.response_mappings == []


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


class TestFuzzyMatching:
    def test_fuzzy_match_full_name_to_applicant_name(self) -> None:
        """source='full_name' should fuzzy-match to target='applicant_name' (shares 'name')."""
        gen = ConfigGenerator(
            request_schema_fields=[
                TargetField("applicant_name", "string"),
                TargetField("pan_number", "string"),
            ],
        )
        source_fields = [SourceField("full_name", "string", source_section="request_body")]
        config = gen.generate(source_fields)

        assert len(config.request_mappings) == 1
        mapping = config.request_mappings[0]
        assert mapping.target_name == "applicant_name"
        assert mapping.confidence > 0.0

    def test_exact_match_gives_higher_confidence_than_fuzzy(self) -> None:
        gen = ConfigGenerator(
            request_schema_fields=[
                TargetField("pan_number", "string"),
                TargetField("pan_id", "string"),
            ],
        )
        source_exact = [SourceField("pan_number", "string", source_section="request_body")]
        source_fuzzy = [SourceField("pan_num", "string", source_section="request_body")]

        exact_config = gen.generate(source_exact)
        fuzzy_config = gen.generate(source_fuzzy)

        exact_confidence = exact_config.request_mappings[0].confidence
        fuzzy_confidence = fuzzy_config.request_mappings[0].confidence

        assert exact_confidence >= fuzzy_confidence
        assert exact_confidence == 1.0

    def test_fuzzy_below_threshold_gives_no_match(self) -> None:
        """With a high threshold, a weak fuzzy match returns confidence=0."""
        gen = ConfigGenerator(
            request_schema_fields=[TargetField("xyz_foo_bar", "string")],
            fuzzy_threshold=0.9,  # very strict
        )
        source_fields = [SourceField("pan_number", "string", source_section="request_body")]
        config = gen.generate(source_fields)

        mapping = config.request_mappings[0]
        assert mapping.confidence == 0.0
        assert mapping.target_name is None

    def test_multiple_source_fields_each_independently_matched(self) -> None:
        gen = ConfigGenerator(
            request_schema_fields=[
                TargetField("pan_number", "string"),
                TargetField("dob", "string"),
                TargetField("phone", "string"),
            ],
        )
        source_fields = [
            SourceField("pan_number", "string", source_section="request"),
            SourceField("date_of_birth", "string", source_section="request"),
            SourceField("mobile_phone", "string", source_section="request"),
        ]
        config = gen.generate(source_fields)
        assert len(config.request_mappings) == 3

        pan_mapping = next(m for m in config.request_mappings if m.source_name == "pan_number")
        assert pan_mapping.confidence == 1.0
        assert pan_mapping.target_name == "pan_number"


# ---------------------------------------------------------------------------
# Transformation suggestions
# ---------------------------------------------------------------------------


class TestTransformationSuggestions:
    def test_string_to_number_suggests_parse_number(self) -> None:
        gen = ConfigGenerator(
            request_schema_fields=[TargetField("amount", "number")],
        )
        source_fields = [
            SourceField("amount", "string", source_section="request_body")
        ]
        config = gen.generate(source_fields)

        mapping = config.request_mappings[0]
        assert mapping.target_name == "amount"
        assert mapping.transformation == "parse_number"

    def test_string_to_integer_suggests_parse_integer(self) -> None:
        gen = ConfigGenerator(
            request_schema_fields=[TargetField("count", "integer")],
        )
        source_fields = [SourceField("count", "string", source_section="request_body")]
        config = gen.generate(source_fields)

        mapping = config.request_mappings[0]
        assert mapping.transformation == "parse_integer"

    def test_same_type_no_transformation(self) -> None:
        gen = ConfigGenerator(
            request_schema_fields=[TargetField("name", "string")],
        )
        source_fields = [SourceField("name", "string", source_section="request_body")]
        config = gen.generate(source_fields)

        mapping = config.request_mappings[0]
        assert mapping.transformation is None

    def test_number_to_string_suggests_to_string(self) -> None:
        gen = ConfigGenerator(
            response_schema_fields=[TargetField("score_display", "string")],
        )
        source_fields = [SourceField("score_display", "number", source_section="response")]
        config = gen.generate(source_fields)

        mapping = config.response_mappings[0]
        assert mapping.transformation == "to_string"

    def test_transformation_only_set_when_target_matched(self) -> None:
        """No transformation is suggested for unmapped fields."""
        gen = ConfigGenerator(
            request_schema_fields=[TargetField("completely_different", "number")],
        )
        source_fields = [
            SourceField("unmatched_field_xyz", "string", source_section="request_body")
        ]
        config = gen.generate(source_fields)

        mapping = config.request_mappings[0]
        if mapping.target_name is None:
            assert mapping.transformation is None


# ---------------------------------------------------------------------------
# ConfigGenerator.from_openapi_endpoint factory
# ---------------------------------------------------------------------------


class TestFromOpenAPIEndpoint:
    def test_builds_from_endpoint_dict_request_fields(self) -> None:
        endpoint_data = {
            "request_body_schema": {
                "type": "object",
                "required": ["pan_number"],
                "properties": {
                    "pan_number": {"type": "string"},
                    "amount": {"type": "number"},
                },
            },
            "response_schemas": {},
        }
        gen = ConfigGenerator.from_openapi_endpoint(endpoint_data)
        req_names = {f.name for f in gen._req_fields}
        assert "pan_number" in req_names
        assert "amount" in req_names

    def test_builds_from_endpoint_dict_response_fields(self) -> None:
        endpoint_data = {
            "request_body_schema": None,
            "response_schemas": {
                "200": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "integer"},
                        "report_id": {"type": "string"},
                    },
                }
            },
        }
        gen = ConfigGenerator.from_openapi_endpoint(endpoint_data)
        resp_names = {f.name for f in gen._resp_fields}
        assert "score" in resp_names
        assert "report_id" in resp_names

    def test_from_openapi_endpoint_empty_schemas(self) -> None:
        gen = ConfigGenerator.from_openapi_endpoint({})
        assert gen._req_fields == []
        assert gen._resp_fields == []

    def test_required_flag_propagated_from_request_schema(self) -> None:
        endpoint_data = {
            "request_body_schema": {
                "type": "object",
                "required": ["pan_number"],
                "properties": {
                    "pan_number": {"type": "string"},
                    "optional_field": {"type": "string"},
                },
            },
            "response_schemas": {},
        }
        gen = ConfigGenerator.from_openapi_endpoint(endpoint_data)
        pan = next(f for f in gen._req_fields if f.name == "pan_number")
        optional = next(f for f in gen._req_fields if f.name == "optional_field")
        assert pan.required is True
        assert optional.required is False

    def test_generate_after_from_openapi_endpoint(self) -> None:
        """End-to-end: build from endpoint data then map source fields."""
        endpoint_data = {
            "request_body_schema": {
                "type": "object",
                "properties": {
                    "pan_number": {"type": "string"},
                    "amount": {"type": "number"},
                },
            },
            "response_schemas": {
                "200": {
                    "type": "object",
                    "properties": {"score": {"type": "integer"}},
                }
            },
        }
        gen = ConfigGenerator.from_openapi_endpoint(endpoint_data)
        source_fields = [
            SourceField("pan_number", "string", source_section="request_body"),
            SourceField("score", "integer", source_section="response_200"),
        ]
        config = gen.generate(source_fields)
        assert len(config.request_mappings) == 1
        assert config.request_mappings[0].target_name == "pan_number"
        assert len(config.response_mappings) == 1
        assert config.response_mappings[0].target_name == "score"
