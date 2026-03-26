"""
Single entry point for document parsing.

Usage:
    doc = parse_document("/path/to/file.docx")
    doc = parse_document_bytes(content_bytes, filename="spec.yaml")
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Union

from finspark.models.parsed_document import DocumentType, ParsedDocument
from finspark.services.document_parser.docx_parser import parse_docx
from finspark.services.document_parser.openapi_parser import parse_openapi
from finspark.services.document_parser.pdf_parser import parse_pdf


def _detect_type(filename: str, content: bytes | None = None) -> DocumentType:
    lower = filename.lower()
    if lower.endswith(".docx"):
        return DocumentType.DOCX
    if lower.endswith(".pdf"):
        return DocumentType.PDF
    if lower.endswith((".yaml", ".yml")):
        return DocumentType.OPENAPI_YAML
    if lower.endswith(".json"):
        # Could be OpenAPI JSON
        return DocumentType.OPENAPI_JSON
    # Sniff bytes
    if content:
        head = content[:512].lstrip()
        if head.startswith(b"PK\x03\x04"):
            return DocumentType.DOCX  # ZIP-based → DOCX
        if head.startswith(b"%PDF"):
            return DocumentType.PDF
        if head.startswith(b"{") or head.startswith(b"---") or b"openapi" in head or b"swagger" in head:
            return DocumentType.OPENAPI_JSON if head.startswith(b"{") else DocumentType.OPENAPI_YAML
    return DocumentType.UNKNOWN


def parse_document(path: Union[str, Path]) -> ParsedDocument:
    """Parse a document from a file path. Type is inferred from extension + magic bytes."""
    p = Path(path)
    content = p.read_bytes()
    doc_type = _detect_type(p.name, content)
    return _dispatch(doc_type, content, p.name)


def parse_document_bytes(content: bytes, filename: str) -> ParsedDocument:
    """Parse a document from raw bytes with an associated filename."""
    doc_type = _detect_type(filename, content)
    return _dispatch(doc_type, content, filename)


def _dispatch(doc_type: DocumentType, content: bytes, filename: str) -> ParsedDocument:
    buf = io.BytesIO(content)
    if doc_type == DocumentType.DOCX:
        result = parse_docx(buf)
    elif doc_type == DocumentType.PDF:
        result = parse_pdf(buf)
    elif doc_type in (DocumentType.OPENAPI_JSON, DocumentType.OPENAPI_YAML):
        result = parse_openapi(buf, filename=filename)
    else:
        # Last-resort: try each parser and return first success
        for parser in (parse_openapi, parse_pdf, parse_docx):
            try:
                result = parser(io.BytesIO(content), filename) if parser is parse_openapi else parser(io.BytesIO(content))  # type: ignore[call-arg]
                if not result.parse_errors:
                    return result
            except Exception:
                pass
        return ParsedDocument(
            source_filename=filename,
            doc_type=DocumentType.UNKNOWN,
            parse_errors=[f"Could not determine document type for '{filename}'"],
        )

    # Patch filename if parser used placeholder
    if result.source_filename == "<bytes>":
        result = result.model_copy(update={"source_filename": filename})
    return result
