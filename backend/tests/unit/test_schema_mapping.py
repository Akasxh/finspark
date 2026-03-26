"""
Unit tests for schema mapping / field transformation logic.

Covers:
- Direct (identity) mapping
- ISO-8601 date coercion
- E.164 phone normalisation
- PAN masking transform
- Nested field path resolution (dot notation)
- Missing required field raises MappingError
- Unknown transform raises MappingError
- Round-trip: apply_mappings on a full customer payload
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.unit


def _get_mapper():
    try:
        from app.services.mapping import FieldMapper  # type: ignore[import]

        return FieldMapper
    except ImportError:
        pytest.skip("app.services.mapping not yet implemented")


class TestDirectMapping:
    def test_identity_mapping(self) -> None:
        FieldMapper = _get_mapper()
        mapper = FieldMapper(
            mappings=[{"source": "customer.pan", "target": "bureau.pan_number", "transform": None}]
        )
        result = mapper.apply({"customer": {"pan": "ABCDE1234F"}})
        assert result["bureau"]["pan_number"] == "ABCDE1234F"

    def test_nested_source_path(self) -> None:
        FieldMapper = _get_mapper()
        mapper = FieldMapper(
            mappings=[
                {"source": "applicant.personal.dob", "target": "kyc.date_of_birth", "transform": None}
            ]
        )
        result = mapper.apply({"applicant": {"personal": {"dob": "1990-01-15"}}})
        assert result["kyc"]["date_of_birth"] == "1990-01-15"

    def test_missing_required_field_raises(self) -> None:
        FieldMapper = _get_mapper()
        try:
            from app.services.mapping import MappingError  # type: ignore[import]
        except ImportError:
            pytest.skip()

        mapper = FieldMapper(
            mappings=[
                {
                    "source": "customer.pan",
                    "target": "bureau.pan_number",
                    "transform": None,
                    "required": True,
                }
            ]
        )
        with pytest.raises(MappingError, match="required"):
            mapper.apply({"customer": {}})


class TestTransforms:
    def test_iso8601_date_coercion(self) -> None:
        FieldMapper = _get_mapper()
        mapper = FieldMapper(
            mappings=[
                {
                    "source": "customer.dob",
                    "target": "kyc.date_of_birth",
                    "transform": "iso8601_date",
                }
            ]
        )
        # Input may arrive as DD-MM-YYYY from some upstream
        result = mapper.apply({"customer": {"dob": "15-01-1990"}})
        assert result["kyc"]["date_of_birth"] == "1990-01-15"

    def test_e164_phone_normalisation(self) -> None:
        FieldMapper = _get_mapper()
        mapper = FieldMapper(
            mappings=[
                {
                    "source": "customer.mobile",
                    "target": "kyc.mobile",
                    "transform": "e164_in",
                }
            ]
        )
        result = mapper.apply({"customer": {"mobile": "9876543210"}})
        assert result["kyc"]["mobile"] == "+919876543210"

    def test_pan_mask_transform(self) -> None:
        FieldMapper = _get_mapper()
        mapper = FieldMapper(
            mappings=[
                {
                    "source": "customer.pan",
                    "target": "log.pan_masked",
                    "transform": "mask_pan",
                }
            ]
        )
        result = mapper.apply({"customer": {"pan": "ABCDE1234F"}})
        masked = result["log"]["pan_masked"]
        assert masked.startswith("ABCDE")
        assert "1234" not in masked  # digits must be masked

    def test_unknown_transform_raises(self) -> None:
        FieldMapper = _get_mapper()
        try:
            from app.services.mapping import MappingError  # type: ignore[import]
        except ImportError:
            pytest.skip()

        mapper = FieldMapper(
            mappings=[
                {
                    "source": "x",
                    "target": "y",
                    "transform": "nonexistent_transform_xyz",
                }
            ]
        )
        with pytest.raises(MappingError, match="Unknown transform"):
            mapper.apply({"x": "value"})


class TestFullPayloadRoundTrip:
    def test_complete_onboarding_payload(self) -> None:
        FieldMapper = _get_mapper()
        mappings = [
            {"source": "customer.pan", "target": "bureau.pan_number", "transform": None},
            {"source": "customer.dob", "target": "bureau.date_of_birth", "transform": "iso8601_date"},
            {"source": "customer.mobile", "target": "kyc.mobile", "transform": "e164_in"},
            {"source": "customer.income", "target": "bureau.annual_income", "transform": None},
        ]
        mapper = FieldMapper(mappings=mappings)
        customer = {
            "customer": {
                "pan": "ABCDE1234F",
                "dob": "15-01-1990",
                "mobile": "9876543210",
                "income": 750000.0,
            }
        }
        result = mapper.apply(customer)
        assert result["bureau"]["pan_number"] == "ABCDE1234F"
        assert result["bureau"]["date_of_birth"] == "1990-01-15"
        assert result["kyc"]["mobile"] == "+919876543210"
        assert result["bureau"]["annual_income"] == 750000.0


@pytest.mark.parametrize(
    ("raw_dob", "expected"),
    [
        ("15-01-1990", "1990-01-15"),
        ("1990-01-15", "1990-01-15"),
        ("15/01/1990", "1990-01-15"),
    ],
)
def test_iso8601_parametric(raw_dob: str, expected: str) -> None:
    FieldMapper = _get_mapper()
    mapper = FieldMapper(
        mappings=[{"source": "dob", "target": "date_of_birth", "transform": "iso8601_date"}]
    )
    result = mapper.apply({"dob": raw_dob})
    assert result["date_of_birth"] == expected
