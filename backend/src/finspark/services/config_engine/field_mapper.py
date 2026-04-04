"""
Field mapper: maps source document fields to adapter request/response schemas.

Supports:
- Exact name matching
- Fuzzy name matching via token overlap scoring
- Separation of request vs response fields by source_section
- Type-based transformation suggestions
- Per-mapping confidence scores (0.0 – 1.0)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SourceField:
    name: str
    field_type: str = "string"
    source_section: str = ""  # e.g. "request_body", "response_200"
    required: bool = False
    description: str = ""


@dataclass
class TargetField:
    name: str
    field_type: str = "string"
    required: bool = False
    description: str = ""


@dataclass
class FieldMapping:
    source_name: str
    target_name: str | None  # None means unmapped
    confidence: float  # 0.0 – 1.0
    transformation: str | None = None
    is_request_field: bool = True  # False → response field


@dataclass
class GeneratedConfig:
    request_mappings: list[FieldMapping] = field(default_factory=list)
    response_mappings: list[FieldMapping] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TYPE_TRANSFORMS: dict[tuple[str, str], str] = {
    ("string", "number"): "parse_number",
    ("string", "integer"): "parse_integer",
    ("string", "boolean"): "parse_boolean",
    ("number", "string"): "to_string",
    ("integer", "string"): "to_string",
    ("boolean", "string"): "to_string",
}


def _is_request_field(source_section: str) -> bool:
    """Return True when source_section indicates this is a request-side field."""
    return "request" in source_section.lower()


def _fuzzy_score(source: str, target: str) -> float:
    """
    Token-overlap similarity between two snake_case or camelCase identifiers.

    Returns a float in [0, 1]. Exact match → 1.0.
    """
    if source == target:
        return 1.0

    def _tokens(name: str) -> set[str]:
        # Split on underscores then lower-case
        parts = name.replace("-", "_").split("_")
        return {p.lower() for p in parts if p}

    src_tokens = _tokens(source)
    tgt_tokens = _tokens(target)
    if not src_tokens or not tgt_tokens:
        return 0.0

    intersection = src_tokens & tgt_tokens
    union = src_tokens | tgt_tokens
    return len(intersection) / len(union)


def _best_match(
    source: str, candidates: list[TargetField], threshold: float = 0.3
) -> tuple[TargetField | None, float]:
    """Return the best-matching target field and its score, or (None, 0.0)."""
    best: TargetField | None = None
    best_score = 0.0
    for candidate in candidates:
        score = _fuzzy_score(source, candidate.name)
        if score > best_score:
            best_score = score
            best = candidate
    if best_score >= threshold:
        return best, best_score
    return None, 0.0


def _suggest_transform(source_type: str, target_type: str) -> str | None:
    return _TYPE_TRANSFORMS.get((source_type.lower(), target_type.lower()))


# ---------------------------------------------------------------------------
# ConfigGenerator
# ---------------------------------------------------------------------------


class ConfigGenerator:
    """
    Maps source fields from a parsed document to adapter request/response schemas.

    Usage::

        generator = ConfigGenerator(
            request_schema_fields=[TargetField("pan_number"), ...],
            response_schema_fields=[TargetField("score"), ...],
        )
        config = generator.generate(source_fields)
    """

    def __init__(
        self,
        request_schema_fields: list[TargetField] | None = None,
        response_schema_fields: list[TargetField] | None = None,
        fuzzy_threshold: float = 0.3,
    ) -> None:
        self._req_fields: list[TargetField] = request_schema_fields or []
        self._resp_fields: list[TargetField] = response_schema_fields or []
        self._threshold = fuzzy_threshold

    def generate(self, source_fields: list[SourceField]) -> GeneratedConfig:
        """
        Map each source field to the best-matching target field.

        - Source fields whose source_section contains "request" are mapped
          against request_schema_fields.
        - All other source fields are mapped against response_schema_fields.
        - Unmapped fields (no candidate above threshold) get confidence=0.
        - When source and target types differ, a transformation suggestion is added.

        Returns
        -------
        GeneratedConfig
            Separate lists for request and response mappings.
        """
        request_mappings: list[FieldMapping] = []
        response_mappings: list[FieldMapping] = []

        for sf in source_fields:
            is_req = _is_request_field(sf.source_section)
            pool = self._req_fields if is_req else self._resp_fields

            target, score = _best_match(sf.name, pool, self._threshold)
            transform: str | None = None
            if target is not None:
                transform = _suggest_transform(sf.field_type, target.field_type)

            mapping = FieldMapping(
                source_name=sf.name,
                target_name=target.name if target else None,
                confidence=round(score, 4),
                transformation=transform,
                is_request_field=is_req,
            )

            if is_req:
                request_mappings.append(mapping)
            else:
                response_mappings.append(mapping)

        return GeneratedConfig(
            request_mappings=request_mappings,
            response_mappings=response_mappings,
        )

    @staticmethod
    def from_openapi_endpoint(endpoint_data: dict[str, Any]) -> "ConfigGenerator":
        """
        Convenience factory that builds a ConfigGenerator directly from an
        ApiEndpoint-like dict with 'request_body_schema' and 'response_schemas'.
        """
        req_fields: list[TargetField] = []
        resp_fields: list[TargetField] = []

        req_schema = endpoint_data.get("request_body_schema") or {}
        for name, prop in (req_schema.get("properties") or {}).items():
            req_fields.append(
                TargetField(
                    name=name,
                    field_type=prop.get("type", "string"),
                    required=name in (req_schema.get("required") or []),
                )
            )

        response_schemas = endpoint_data.get("response_schemas") or {}
        for _status, schema in response_schemas.items():
            for name, prop in (schema.get("properties") or {}).items():
                resp_fields.append(
                    TargetField(
                        name=name,
                        field_type=prop.get("type", "string"),
                    )
                )

        return ConfigGenerator(
            request_schema_fields=req_fields,
            response_schema_fields=resp_fields,
        )
