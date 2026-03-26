"""
ConfigGenerator — takes parsed document output + a selected adapter descriptor
and produces a validated JSON integration config.

Flow:
  1. Flatten nested document payload (SchemaTransformer.flatten)
  2. Run FieldMapper to propose source→target mappings
  3. Auto-register SchemaTransformer rules for matched fields
  4. Apply transformations to raw values
  5. Validate result against adapter FieldSchema (required fields, patterns,
     max_length, enum_values)
  6. Emit GeneratedConfig with per-field metadata and an overall confidence score

The emitted config is a plain JSON-serialisable dict so it can be stored
in the configurations.config_data JSONB column directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.integrations.metadata import AdapterMetadata, FieldSchema
from app.integrations.config_engine.field_mapper import FieldMapper, FieldMatch
from app.integrations.config_engine.schema_transformer import SchemaTransformer


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FieldConfigEntry:
    """Per-field entry inside a GeneratedConfig."""

    source_field: str
    target_field: str
    raw_value: Any
    transformed_value: Any
    confidence: float
    match_method: str
    transform_ops: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    is_required: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_field": self.source_field,
            "target_field": self.target_field,
            "raw_value": self.raw_value,
            "transformed_value": self.transformed_value,
            "confidence": round(self.confidence, 4),
            "match_method": self.match_method,
            "transform_ops": self.transform_ops,
            "validation_errors": self.validation_errors,
            "is_required": self.is_required,
            "notes": self.notes,
        }


@dataclass
class GeneratedConfig:
    """
    Full output of ConfigGenerator.generate().

    config_data:       dict ready to insert into DB / return via API
    field_entries:     per-field mapping metadata with confidence
    overall_confidence: weighted mean confidence (required fields weighted 2x)
    missing_required:  target fields marked required but not mapped
    validation_errors: field-level validation failures
    adapter_kind:      e.g. "kyc", "credit_bureau"
    adapter_version:   e.g. "v1"
    """

    config_data: dict[str, Any]
    field_entries: list[FieldConfigEntry]
    overall_confidence: float
    missing_required: list[str]
    validation_errors: dict[str, list[str]]
    adapter_kind: str
    adapter_version: str

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self._serialise(), indent=indent, ensure_ascii=False)

    def _serialise(self) -> dict[str, Any]:
        return {
            "adapter_kind": self.adapter_kind,
            "adapter_version": self.adapter_version,
            "overall_confidence": round(self.overall_confidence, 4),
            "missing_required": self.missing_required,
            "validation_errors": self.validation_errors,
            "config_data": self.config_data,
            "field_entries": [e.as_dict() for e in self.field_entries],
        }


# ---------------------------------------------------------------------------
# ConfigGenerator
# ---------------------------------------------------------------------------

class ConfigGenerator:
    """
    Orchestrates field mapping + schema transformation to produce an
    integration config from a raw parsed document payload.

    Parameters
    ----------
    adapter_metadata:
        The target adapter's AdapterMetadata descriptor.
    min_confidence:
        Mappings below this threshold are excluded from config_data but
        still appear in field_entries for transparency.
    include_unmatched_in_config:
        When True, source fields with no confident match are passed through
        to config_data verbatim under their original names.
    """

    def __init__(
        self,
        adapter_metadata: AdapterMetadata,
        min_confidence: float = 0.50,
        include_unmatched_in_config: bool = False,
    ) -> None:
        self._meta = adapter_metadata
        self._min_confidence = min_confidence
        self._include_unmatched = include_unmatched_in_config
        self._mapper = FieldMapper(
            target_fields=adapter_metadata.supported_fields,
            min_confidence=min_confidence,
        )
        self._transformer = SchemaTransformer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, document_output: dict[str, Any]) -> GeneratedConfig:
        """
        Generate a config from a parsed document payload.

        Parameters
        ----------
        document_output:
            Arbitrary nested dict from the document parser.
            Nested dicts are flattened before processing.
        """
        # 1. Flatten nested payload
        flatten_result = SchemaTransformer.flatten(document_output)
        flat_data = flatten_result.flat

        # 2. Map source fields to adapter targets
        source_field_names = list(flat_data.keys())
        matches: list[FieldMatch] = self._mapper.map(source_field_names)

        # Build a lookup: target_field → match
        match_by_target: dict[str, FieldMatch] = {m.target_field: m for m in matches}

        # 3. Auto-register transformer rules for matched target fields
        self._transformer.auto_register([m.target_field for m in matches])

        # Build a remapped dict: target_field → raw_value
        remapped: dict[str, Any] = {}
        for m in matches:
            if m.confidence >= self._min_confidence:
                remapped[m.target_field] = flat_data[m.source_field]

        # 4. Apply transformations
        transformed, transform_log = self._transformer.transform(remapped)

        # 5. Validate against adapter schema
        schema_by_name: dict[str, FieldSchema] = {
            fs.name: fs for fs in self._meta.supported_fields
        }
        validation_errors: dict[str, list[str]] = {}
        for tgt_name, value in transformed.items():
            schema = schema_by_name.get(tgt_name)
            if schema is None:
                continue
            errs = _validate_field_value(tgt_name, value, schema)
            if errs:
                validation_errors[tgt_name] = errs

        # 6. Detect missing required fields
        missing_required = [
            fs.name
            for fs in self._meta.supported_fields
            if fs.required and fs.name not in transformed
        ]

        # 7. Build field entries
        entries: list[FieldConfigEntry] = []
        for m in matches:
            raw = flat_data[m.source_field]
            t_val = transformed.get(m.target_field, raw)
            entries.append(
                FieldConfigEntry(
                    source_field=m.source_field,
                    target_field=m.target_field,
                    raw_value=raw,
                    transformed_value=t_val,
                    confidence=m.confidence,
                    match_method=m.match_method,
                    transform_ops=transform_log.get(m.target_field, []),
                    validation_errors=validation_errors.get(m.target_field, []),
                    is_required=m.is_required,
                    notes=m.notes,
                )
            )

        # Pass-through unmatched fields if requested
        matched_sources = {m.source_field for m in matches}
        if self._include_unmatched:
            for src_name, val in flat_data.items():
                if src_name not in matched_sources:
                    entries.append(
                        FieldConfigEntry(
                            source_field=src_name,
                            target_field=src_name,
                            raw_value=val,
                            transformed_value=val,
                            confidence=0.0,
                            match_method="passthrough",
                        )
                    )
                    transformed[src_name] = val

        # 8. Overall confidence = weighted mean (required fields 2x weight)
        overall_confidence = _weighted_confidence(entries, schema_by_name)

        # config_data contains only fields that pass confidence threshold
        config_data = {
            tgt: val
            for tgt, val in transformed.items()
            if match_by_target.get(tgt) is None
            or match_by_target[tgt].confidence >= self._min_confidence
        }

        return GeneratedConfig(
            config_data=config_data,
            field_entries=entries,
            overall_confidence=overall_confidence,
            missing_required=missing_required,
            validation_errors=validation_errors,
            adapter_kind=self._meta.kind,
            adapter_version=self._meta.version,
        )

    def generate_template(self) -> dict[str, Any]:
        """
        Emit a JSON config template for the adapter with placeholder values.
        Useful for manual config scaffolding / API docs.
        """
        template: dict[str, Any] = {
            "_adapter": {
                "kind": self._meta.kind,
                "version": self._meta.version,
                "provider": self._meta.provider,
            },
            "fields": {},
        }
        for fs in self._meta.supported_fields:
            template["fields"][fs.name] = {
                "type": fs.dtype,
                "required": fs.required,
                "description": fs.description,
                "example": fs.example,
                "pattern": fs.pattern,
                "max_length": fs.max_length,
                "enum_values": list(fs.enum_values) if fs.enum_values else None,
            }
        return template


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_field_value(
    field_name: str,
    value: Any,
    schema: FieldSchema,
) -> list[str]:
    errors: list[str] = []
    str_val = str(value) if value is not None else ""

    if schema.max_length and len(str_val) > schema.max_length:
        errors.append(
            f"Value length {len(str_val)} exceeds max_length {schema.max_length}"
        )
    if schema.pattern:
        import re
        if not re.fullmatch(schema.pattern, str_val):
            errors.append(f"Value {str_val!r} does not match pattern {schema.pattern!r}")
    if schema.enum_values and str_val not in schema.enum_values:
        errors.append(
            f"Value {str_val!r} not in allowed enum_values: {schema.enum_values}"
        )
    if schema.dtype == "int":
        try:
            int(str_val.replace(",", ""))
        except ValueError:
            errors.append(f"Cannot cast {str_val!r} to int")
    if schema.dtype == "float":
        try:
            float(str_val.replace(",", ""))
        except ValueError:
            errors.append(f"Cannot cast {str_val!r} to float")
    return errors


def _weighted_confidence(
    entries: list[FieldConfigEntry],
    schema_by_name: dict[str, FieldSchema],
) -> float:
    if not entries:
        return 0.0
    total_weight = 0.0
    weighted_sum = 0.0
    for e in entries:
        w = 2.0 if e.is_required else 1.0
        weighted_sum += e.confidence * w
        total_weight += w
    return weighted_sum / total_weight if total_weight > 0 else 0.0
