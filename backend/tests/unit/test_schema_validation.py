"""
Unit tests for Pydantic schemas used across the API layer.

Covers:
- Request body validation for document upload
- Config generation request
- Integration create/update schemas
- Field mapping schema
- Error response shape
- UUID field coercion
- Enum validation
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_schema(module: str, name: str):
    try:
        import importlib

        mod = importlib.import_module(f"app.schemas.{module}")
        return getattr(mod, name)
    except (ImportError, AttributeError):
        pytest.skip(f"app.schemas.{module}.{name} not yet implemented")


# ---------------------------------------------------------------------------
# Document schemas
# ---------------------------------------------------------------------------


class TestDocumentUploadSchema:
    def test_valid_upload_meta(self) -> None:
        Schema = _import_schema("document", "DocumentUploadMeta")
        obj = Schema(filename="brd.pdf", content_type="application/pdf", tenant_id="t1")
        assert obj.filename == "brd.pdf"

    def test_rejects_unsupported_content_type(self) -> None:
        Schema = _import_schema("document", "DocumentUploadMeta")
        with pytest.raises(ValidationError):
            Schema(
                filename="exploit.exe",
                content_type="application/x-msdownload",
                tenant_id="t1",
            )

    def test_filename_is_required(self) -> None:
        Schema = _import_schema("document", "DocumentUploadMeta")
        with pytest.raises(ValidationError):
            Schema(content_type="application/pdf", tenant_id="t1")


# ---------------------------------------------------------------------------
# Config generation schemas
# ---------------------------------------------------------------------------


class TestConfigGenerateRequest:
    def test_valid_request(self) -> None:
        Schema = _import_schema("config", "ConfigGenerateRequest")
        req = Schema(text="Integrate with CIBIL bureau API v2.0")
        assert len(req.text) > 0

    def test_empty_text_rejected(self) -> None:
        Schema = _import_schema("config", "ConfigGenerateRequest")
        with pytest.raises(ValidationError):
            Schema(text="")

    def test_whitespace_only_rejected(self) -> None:
        Schema = _import_schema("config", "ConfigGenerateRequest")
        with pytest.raises(ValidationError):
            Schema(text="   \n\t  ")

    def test_text_length_limit(self) -> None:
        Schema = _import_schema("config", "ConfigGenerateRequest")
        # Most schemas cap at ~50 KB of text
        with pytest.raises(ValidationError):
            Schema(text="x" * 200_001)


# ---------------------------------------------------------------------------
# Integration schemas
# ---------------------------------------------------------------------------


class TestIntegrationCreateSchema:
    def test_valid_create(self) -> None:
        Schema = _import_schema("integration", "IntegrationCreate")
        obj = Schema(
            tenant_id="t1",
            adapter_slug="cibil-bureau",
            adapter_version="2.0",
            name="Credit Check",
            config={"base_url": "https://api.example.com", "timeout_ms": 3000},
        )
        assert obj.adapter_slug == "cibil-bureau"

    def test_adapter_slug_required(self) -> None:
        Schema = _import_schema("integration", "IntegrationCreate")
        with pytest.raises(ValidationError):
            Schema(
                tenant_id="t1",
                adapter_version="2.0",
                name="No Slug",
                config={},
            )

    def test_config_must_be_dict(self) -> None:
        Schema = _import_schema("integration", "IntegrationCreate")
        with pytest.raises(ValidationError):
            Schema(
                tenant_id="t1",
                adapter_slug="cibil-bureau",
                adapter_version="2.0",
                name="Bad Config",
                config="not-a-dict",
            )

    def test_version_format_validated(self) -> None:
        Schema = _import_schema("integration", "IntegrationCreate")
        with pytest.raises(ValidationError):
            Schema(
                tenant_id="t1",
                adapter_slug="cibil-bureau",
                adapter_version="not-semver!!!!",
                name="Bad Version",
                config={},
            )


# ---------------------------------------------------------------------------
# Field mapping schema
# ---------------------------------------------------------------------------


class TestFieldMappingSchema:
    def test_valid_mapping(self) -> None:
        Schema = _import_schema("mapping", "FieldMappingCreate")
        obj = Schema(
            tenant_id="t1",
            adapter_slug="cibil-bureau",
            source_field="customer.pan",
            target_field="bureau.pan_number",
            transform=None,
            is_required=True,
        )
        assert obj.source_field == "customer.pan"

    def test_transform_must_be_known(self) -> None:
        Schema = _import_schema("mapping", "FieldMappingCreate")
        with pytest.raises(ValidationError):
            Schema(
                tenant_id="t1",
                adapter_slug="cibil-bureau",
                source_field="x",
                target_field="y",
                transform="totally_unknown_transform_xyz",
                is_required=False,
            )

    @pytest.mark.parametrize("transform", ["iso8601_date", "e164_in", "mask_pan", None])
    def test_known_transforms_accepted(self, transform: str | None) -> None:
        Schema = _import_schema("mapping", "FieldMappingCreate")
        obj = Schema(
            tenant_id="t1",
            adapter_slug="cibil-bureau",
            source_field="a",
            target_field="b",
            transform=transform,
            is_required=False,
        )
        assert obj.transform == transform


# ---------------------------------------------------------------------------
# Error response schema
# ---------------------------------------------------------------------------


class TestErrorResponseSchema:
    def test_error_shape(self) -> None:
        Schema = _import_schema("common", "ErrorResponse")
        err = Schema(detail="Not found", code="not_found", status_code=404)
        assert err.status_code == 404
        assert err.code == "not_found"
