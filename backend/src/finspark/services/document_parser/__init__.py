"""
Document parsing service.

Entry point: `parse_document(path_or_bytes, filename)`
"""
from finspark.services.document_parser.facade import parse_document, parse_document_bytes

__all__ = ["parse_document", "parse_document_bytes"]
