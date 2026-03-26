"""Unit tests for the document parser."""

from pathlib import Path

import pytest

from finspark.services.parsing.document_parser import DocumentParser


@pytest.fixture
def parser() -> DocumentParser:
    return DocumentParser()


class TestDocumentParserTextParsing:
    """Test text-based document parsing."""

    def test_parse_text_extracts_endpoints(
        self, parser: DocumentParser, sample_brd_text: str
    ) -> None:
        result = parser.parse_text(sample_brd_text, doc_type="brd")
        assert len(result.endpoints) > 0
        paths = [ep.path for ep in result.endpoints]
        assert any("/credit-score" in p or "/v1/credit-score" in p for p in paths)

    def test_parse_text_extracts_fields(self, parser: DocumentParser, sample_brd_text: str) -> None:
        result = parser.parse_text(sample_brd_text, doc_type="brd")
        assert len(result.fields) > 0
        field_names = [f.name for f in result.fields]
        assert any("pan" in fn for fn in field_names)
        assert any("name" in fn for fn in field_names)

    def test_parse_text_extracts_auth(self, parser: DocumentParser, sample_brd_text: str) -> None:
        result = parser.parse_text(sample_brd_text, doc_type="brd")
        assert len(result.auth_requirements) > 0
        auth_types = [a.auth_type for a in result.auth_requirements]
        assert any(
            "api" in at.lower() or "key" in at.lower() or "oauth" in at.lower() for at in auth_types
        )

    def test_parse_text_extracts_services(
        self, parser: DocumentParser, sample_brd_text: str
    ) -> None:
        result = parser.parse_text(sample_brd_text, doc_type="brd")
        assert len(result.services_identified) > 0
        assert any("CIBIL" in s for s in result.services_identified)

    def test_parse_text_extracts_security_requirements(
        self, parser: DocumentParser, sample_brd_text: str
    ) -> None:
        result = parser.parse_text(sample_brd_text, doc_type="brd")
        assert len(result.security_requirements) > 0

    def test_parse_text_extracts_sla(self, parser: DocumentParser, sample_brd_text: str) -> None:
        result = parser.parse_text(sample_brd_text, doc_type="brd")
        assert len(result.sla_requirements) > 0

    def test_parse_text_confidence_score(
        self, parser: DocumentParser, sample_brd_text: str
    ) -> None:
        result = parser.parse_text(sample_brd_text, doc_type="brd")
        assert 0.0 <= result.confidence_score <= 1.0
        assert result.confidence_score > 0.3  # BRD should have decent confidence

    def test_parse_text_empty_input(self, parser: DocumentParser) -> None:
        result = parser.parse_text("", doc_type="brd")
        assert result.confidence_score == 0.0
        assert len(result.endpoints) == 0

    def test_parse_text_extracts_title(self, parser: DocumentParser, sample_brd_text: str) -> None:
        result = parser.parse_text(sample_brd_text, doc_type="brd")
        assert len(result.title) > 0


class TestDocumentParserOpenAPI:
    """Test OpenAPI spec parsing."""

    def test_parse_openapi_yaml(self, parser: DocumentParser, sample_openapi_path: Path) -> None:
        result = parser.parse(sample_openapi_path)
        assert result.doc_type == "api_spec"
        assert result.confidence_score >= 0.9

    def test_parse_openapi_extracts_endpoints(
        self, parser: DocumentParser, sample_openapi_path: Path
    ) -> None:
        result = parser.parse(sample_openapi_path)
        assert len(result.endpoints) >= 3
        paths = [ep.path for ep in result.endpoints]
        assert "/scores" in paths
        assert "/reports" in paths

    def test_parse_openapi_extracts_fields(
        self, parser: DocumentParser, sample_openapi_path: Path
    ) -> None:
        result = parser.parse(sample_openapi_path)
        assert len(result.fields) > 0
        field_names = [f.name for f in result.fields]
        assert any("pan_number" in fn for fn in field_names)

    def test_parse_openapi_extracts_auth(
        self, parser: DocumentParser, sample_openapi_path: Path
    ) -> None:
        result = parser.parse(sample_openapi_path)
        assert len(result.auth_requirements) > 0

    def test_parse_openapi_extracts_title(
        self, parser: DocumentParser, sample_openapi_path: Path
    ) -> None:
        result = parser.parse(sample_openapi_path)
        assert "CIBIL" in result.title


class TestDocumentParserFieldTypes:
    """Test field type inference."""

    def test_infer_date_type(self, parser: DocumentParser) -> None:
        assert DocumentParser._infer_field_type("date_of_birth") == "date"
        assert DocumentParser._infer_field_type("created_at") == "date"

    def test_infer_number_type(self, parser: DocumentParser) -> None:
        assert DocumentParser._infer_field_type("loan_amount") == "number"
        assert DocumentParser._infer_field_type("credit_score") == "number"

    def test_infer_email_type(self, parser: DocumentParser) -> None:
        assert DocumentParser._infer_field_type("email_address") == "email"

    def test_infer_phone_type(self, parser: DocumentParser) -> None:
        assert DocumentParser._infer_field_type("mobile_number") == "phone"

    def test_infer_boolean_type(self, parser: DocumentParser) -> None:
        assert DocumentParser._infer_field_type("is_active") == "boolean"

    def test_infer_string_default(self, parser: DocumentParser) -> None:
        assert DocumentParser._infer_field_type("reference_id") == "string"


class TestDocumentParserUnsupported:
    """Test error handling for unsupported formats."""

    def test_unsupported_format(self, parser: DocumentParser) -> None:
        with pytest.raises(ValueError, match="Unsupported file format"):
            parser.parse(Path("test.xyz"))
