"""
Unit tests for the Requirement Parsing Engine (document parser).

Covers:
- Plain-text BRD extraction
- PDF byte extraction
- DOCX extraction
- Service / adapter detection from text
- Field mapping extraction
- SLA / timeout extraction
- Masked field detection (PAN, Aadhaar)
- Edge cases: empty doc, unknown format, very large text
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers shared across this module
# ---------------------------------------------------------------------------

KNOWN_ADAPTERS = {
    "cibil": "credit_bureau",
    "uidai": "kyc",
    "gstn": "gst",
    "razorpay": "payment",
    "setu": "account_aggregator",
}


def _make_parser(text: str):
    """
    Build a DocumentParser instance without needing the real module.
    Replaced with the actual import once app/ is implemented.
    """
    try:
        from app.services.parser import DocumentParser  # type: ignore[import]

        return DocumentParser(text)
    except ImportError:
        pytest.skip("app.services.parser not yet implemented")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


class TestTextExtraction:
    def test_extracts_adapter_names_from_brd(self, sample_brd_text: str) -> None:
        parser = _make_parser(sample_brd_text)
        detected = parser.detect_adapters()
        slugs = {a["id"] for a in detected}
        assert "cibil-bureau" in slugs
        assert "uidai-kyc" in slugs

    def test_extracts_field_mappings(self, sample_brd_text: str) -> None:
        parser = _make_parser(sample_brd_text)
        mappings = parser.extract_field_mappings()
        sources = {m["source"] for m in mappings}
        assert "customer.pan" in sources or any("pan" in s.lower() for s in sources)

    def test_extracts_sla_timeouts(self, sample_brd_text: str) -> None:
        parser = _make_parser(sample_brd_text)
        sla = parser.extract_sla()
        assert sla["bureau"]["timeout_s"] == 3
        assert sla["bureau"]["retry_count"] == 3
        assert sla["kyc"]["timeout_s"] == 5

    def test_detects_sensitive_fields(self, sample_brd_text: str) -> None:
        parser = _make_parser(sample_brd_text)
        sensitive = parser.detect_sensitive_fields()
        assert "pan" in {f.lower() for f in sensitive}

    def test_empty_document_returns_empty_results(self) -> None:
        parser = _make_parser("")
        assert parser.detect_adapters() == []
        assert parser.extract_field_mappings() == []

    def test_no_false_positives_on_irrelevant_text(self) -> None:
        boring = "The quarterly earnings report shows revenue of 1.2B INR."
        parser = _make_parser(boring)
        assert parser.detect_adapters() == []

    def test_version_extraction(self, sample_brd_text: str) -> None:
        parser = _make_parser(sample_brd_text)
        detected = parser.detect_adapters()
        cibil = next((a for a in detected if "cibil" in a["id"]), None)
        assert cibil is not None
        assert cibil.get("version") in ("2.0", "v2.0")


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------


class TestPdfParsing:
    def test_pdf_extraction_returns_string(self, sample_pdf_bytes: bytes) -> None:
        try:
            from app.services.parser import extract_text_from_pdf  # type: ignore[import]
        except ImportError:
            pytest.skip("extract_text_from_pdf not yet implemented")

        text = extract_text_from_pdf(io.BytesIO(sample_pdf_bytes))
        assert isinstance(text, str)
        assert len(text) > 0

    def test_pdf_extraction_handles_empty_file(self) -> None:
        try:
            from app.services.parser import extract_text_from_pdf  # type: ignore[import]
        except ImportError:
            pytest.skip()

        with pytest.raises((ValueError, RuntimeError)):
            extract_text_from_pdf(io.BytesIO(b""))

    def test_pdf_extraction_mock(self, sample_pdf_bytes: bytes) -> None:
        """
        Mock-based test: verify the function calls pypdf correctly without
        exercising actual PDF parsing.
        """
        try:
            from app.services import parser as parser_mod  # type: ignore[import]
        except ImportError:
            pytest.skip()

        with patch.object(parser_mod, "PdfReader") as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Integration BRD"
            mock_reader.return_value.pages = [mock_page]

            text = parser_mod.extract_text_from_pdf(io.BytesIO(sample_pdf_bytes))
            assert "Integration BRD" in text
            mock_reader.assert_called_once()


# ---------------------------------------------------------------------------
# DOCX parsing
# ---------------------------------------------------------------------------


class TestDocxParsing:
    def test_docx_extraction_returns_paragraphs(self, sample_docx_bytes: bytes) -> None:
        try:
            from app.services.parser import extract_text_from_docx  # type: ignore[import]
        except ImportError:
            pytest.skip()

        text = extract_text_from_docx(io.BytesIO(sample_docx_bytes))
        assert "CIBIL" in text or "bureau" in text.lower()

    def test_docx_extraction_handles_corrupt_file(self) -> None:
        try:
            from app.services.parser import extract_text_from_docx  # type: ignore[import]
        except ImportError:
            pytest.skip()

        with pytest.raises((ValueError, RuntimeError)):
            extract_text_from_docx(io.BytesIO(b"not a docx"))

    def test_docx_mock_extraction(self, sample_docx_bytes: bytes) -> None:
        try:
            from app.services import parser as parser_mod  # type: ignore[import]
        except ImportError:
            pytest.skip()

        with patch.object(parser_mod, "Document") as mock_doc_cls:
            p1 = MagicMock()
            p1.text = "Integrate with CIBIL bureau API v2.0"
            p2 = MagicMock()
            p2.text = "Customer PAN maps to bureau.pan_number"
            mock_doc_cls.return_value.paragraphs = [p1, p2]

            text = parser_mod.extract_text_from_docx(io.BytesIO(sample_docx_bytes))
            assert "CIBIL" in text


# ---------------------------------------------------------------------------
# Parametric adapter detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("keyword", "expected_category"),
    [
        ("CIBIL credit bureau", "credit_bureau"),
        ("UIDAI Aadhaar eKYC", "kyc"),
        ("GSTN GST verification", "gst"),
        ("Razorpay payment gateway", "payment"),
        ("Setu Account Aggregator", "account_aggregator"),
    ],
)
def test_adapter_detection_by_keyword(keyword: str, expected_category: str) -> None:
    parser = _make_parser(f"The system must integrate with {keyword} for processing.")
    detected = parser.detect_adapters()
    categories = {a.get("category") for a in detected}
    assert expected_category in categories, (
        f"Expected category {expected_category!r} not found in {categories}"
    )


# ---------------------------------------------------------------------------
# Large document performance
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_large_brd_parses_within_threshold(sample_brd_text: str) -> None:
    import time

    large_text = sample_brd_text * 200  # ~40 KB of repeated content
    start = time.perf_counter()
    parser = _make_parser(large_text)
    parser.detect_adapters()
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"Parsing took {elapsed:.2f}s, expected <2s"
