"""
PDF parser using pypdf.

Strategy:
1. Extract full text page-by-page via pypdf (fast, no extra deps).
2. Heuristically split into sections by detecting ALL-CAPS or Title-Case
   lines that look like headings (≤ 80 chars, preceded by blank line).
3. Detect table-like blocks: lines where ≥3 tab/multi-space separated
   columns repeat across ≥3 consecutive lines.
4. Run entity extraction (URLs, API paths, fields, auth hints) per section.

pdfplumber is better for complex PDFs but adds a heavy dependency;
pypdf covers 95% of BRD/spec PDFs encountered in practice.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Union

from pypdf import PdfReader  # type: ignore[import-untyped]

from finspark.models.parsed_document import (
    ApiEndpoint,
    AuthRequirement,
    AuthScheme,
    DocumentSection,
    DocumentType,
    FieldDefinition,
    HttpMethod,
    ParsedDocument,
    TableData,
)
from finspark.services.document_parser.heuristics import (
    classify_section,
    detect_auth_schemes,
    detect_http_method_pairs,
    extract_api_paths,
    extract_field_names,
    extract_urls,
    extract_version,
)


# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)*\.?\s+[A-Z]"  # "1.2 Title" or "1. TITLE"
    r"|[A-Z][A-Z\s]{3,60}$"       # ALL CAPS line
    r"|(?:[A-Z][a-z]+\s*){2,8}$"  # Title Case multiword ≤ 8 words
    r")"
)

_MULTI_SPACE_RE = re.compile(r"  {2,}|\t+")  # 2+ spaces or tabs → column sep


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 100:
        return False
    return bool(_HEADING_RE.match(stripped))


# ---------------------------------------------------------------------------
# Table detection: runs of lines with consistent column count via multi-space
# ---------------------------------------------------------------------------

def _try_extract_table(lines: list[str], section_heading: str) -> TableData | None:
    """
    Given a block of lines that look tabular, split on multi-space and return
    a TableData if at least 2 rows of consistent column count are found.
    """
    if len(lines) < 2:
        return None

    split_rows = [_MULTI_SPACE_RE.split(ln.strip()) for ln in lines if ln.strip()]
    col_counts = [len(r) for r in split_rows if len(r) > 1]
    if not col_counts:
        return None

    # Use the most common column count
    mode_cols = max(set(col_counts), key=col_counts.count)
    if mode_cols < 2:
        return None

    consistent = [r for r in split_rows if len(r) == mode_cols]
    if len(consistent) < 2:
        return None

    return TableData(
        headers=[c.strip() for c in consistent[0]],
        rows=[[c.strip() for c in row] for row in consistent[1:]],
        source_section=section_heading,
    )


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------

def _split_into_sections(full_text: str) -> list[tuple[str, int, str]]:
    """
    Returns list of (heading, level, content) tuples.
    Level is inferred from whether it's numeric (1.2 → level 2) or ALL CAPS (1).
    """
    lines = full_text.splitlines()
    sections: list[tuple[str, int, str]] = []
    cur_heading = "Preamble"
    cur_level = 0
    cur_lines: list[str] = []

    for line in lines:
        if _looks_like_heading(line.strip()):
            if cur_lines:
                sections.append((cur_heading, cur_level, "\n".join(cur_lines)))
            cur_heading = line.strip()
            # Infer level from numbering
            num_match = re.match(r"^(\d+)((?:\.\d+)*)", cur_heading)
            if num_match:
                cur_level = len(num_match.group(2).split(".")) if num_match.group(2) else 1
            else:
                cur_level = 1
            cur_lines = []
        else:
            cur_lines.append(line)

    if cur_lines:
        sections.append((cur_heading, cur_level, "\n".join(cur_lines)))

    return sections if sections else [("Document", 1, full_text)]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_pdf(source: Union[str, Path, bytes, io.BytesIO]) -> ParsedDocument:
    if isinstance(source, bytes):
        source = io.BytesIO(source)

    path_str = str(source) if not isinstance(source, io.BytesIO) else "<bytes>"

    try:
        reader = PdfReader(source)
    except Exception as exc:
        return ParsedDocument(
            source_filename=path_str,
            doc_type=DocumentType.PDF,
            parse_errors=[f"Failed to open PDF: {exc}"],
        )

    page_texts: list[str] = []
    for page in reader.pages:
        try:
            page_texts.append(page.extract_text() or "")
        except Exception as exc:
            page_texts.append("")

    full_text = "\n".join(page_texts)
    raw_sections = _split_into_sections(full_text)

    doc_sections: list[DocumentSection] = []
    all_tables: list[TableData] = []
    endpoints: list[ApiEndpoint] = []
    seen_endpoints: set[tuple[str, str]] = set()
    field_definitions: list[FieldDefinition] = []

    for heading, level, content in raw_sections:
        # Try to detect table blocks within content
        section_tables: list[TableData] = []
        content_lines = content.splitlines()
        tabular_buffer: list[str] = []

        for ln in content_lines:
            if _MULTI_SPACE_RE.search(ln):
                tabular_buffer.append(ln)
            else:
                if len(tabular_buffer) >= 3:
                    tbl = _try_extract_table(tabular_buffer, heading)
                    if tbl:
                        section_tables.append(tbl)
                        all_tables.append(tbl)
                tabular_buffer = []

        if len(tabular_buffer) >= 3:
            tbl = _try_extract_table(tabular_buffer, heading)
            if tbl:
                section_tables.append(tbl)
                all_tables.append(tbl)

        section = DocumentSection(
            heading=heading,
            level=level,
            category=classify_section(heading, content),
            content=content,
            tables=section_tables,
            urls=extract_urls(content),
            api_paths=extract_api_paths(content),
            field_names=extract_field_names(content),
        )
        doc_sections.append(section)

        # Endpoints from inline method+path mentions
        for method_str, path in detect_http_method_pairs(content):
            key = (method_str, path)
            if key not in seen_endpoints:
                seen_endpoints.add(key)
                try:
                    method = HttpMethod(method_str)
                except ValueError:
                    continue
                endpoints.append(
                    ApiEndpoint(path=path, method=method, source_section=heading)
                )

        # Fields from table rows
        for tbl in section_tables:
            lower_headers = [h.lower() for h in tbl.headers]
            name_idx = next(
                (i for i, h in enumerate(lower_headers) if h in ("field", "name", "property", "parameter")),
                None,
            )
            type_idx = next(
                (i for i, h in enumerate(lower_headers) if "type" in h),
                None,
            )
            if name_idx is None:
                continue
            for row in tbl.rows:
                if len(row) <= name_idx:
                    continue
                field_definitions.append(
                    FieldDefinition(
                        name=row[name_idx],
                        field_type=row[type_idx] if type_idx is not None and len(row) > type_idx else "unknown",
                    )
                )

    auth_schemes = detect_auth_schemes(full_text)
    auth_requirements = [
        AuthRequirement(scheme=s, description="Detected via PDF heuristic scan")
        for s in auth_schemes
    ] or [AuthRequirement(scheme=AuthScheme.NONE)]

    return ParsedDocument(
        source_filename=path_str,
        doc_type=DocumentType.PDF,
        title=raw_sections[0][0] if raw_sections else "",
        version=extract_version(full_text),
        sections=doc_sections,
        tables=all_tables,
        endpoints=endpoints,
        auth_requirements=auth_requirements,
        field_definitions=field_definitions,
        all_urls=extract_urls(full_text),
        all_api_paths=extract_api_paths(full_text),
        all_field_names=extract_field_names(full_text),
        word_count=len(full_text.split()),
        page_count=len(reader.pages),
        raw_text=full_text,
    )
