"""
Contract validation: checks that an API response conforms to the
EndpointSchema.response_schema (JSON Schema Draft-7 subset).

Uses jsonschema when available; falls back to a lightweight built-in
validator so the framework has no hard dependency on jsonschema.
"""
from __future__ import annotations

import re
from typing import Any

from finspark.simulation.types import EndpointSchema


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_contract(
    endpoint: EndpointSchema,
    response_body: dict[str, Any],
    status_code: int,
) -> list[str]:
    """
    Returns a (possibly empty) list of human-readable violation strings.

    Checks:
    1. Status code is in endpoint.success_codes.
    2. response_body conforms to endpoint.response_schema (JSON Schema subset).
    """
    violations: list[str] = []

    # ---- status code gate ------------------------------------------------
    if status_code not in endpoint.success_codes:
        violations.append(
            f"Status {status_code} not in success_codes {endpoint.success_codes}"
        )

    schema = endpoint.response_schema
    if not schema:
        return violations

    # ---- try jsonschema first (best-effort) ------------------------------
    try:
        import jsonschema  # type: ignore[import-untyped]

        try:
            jsonschema.validate(response_body, schema)
        except jsonschema.ValidationError as exc:
            violations.append(f"Schema violation: {exc.message}")
        except jsonschema.SchemaError as exc:
            violations.append(f"Invalid schema definition: {exc.message}")
        return violations
    except ImportError:
        pass

    # ---- built-in lightweight validator ----------------------------------
    violations.extend(_validate_object(response_body, schema, path="$"))
    return violations


# ---------------------------------------------------------------------------
# Lightweight JSON Schema validator (type / required / properties / pattern)
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _validate_object(
    data: Any,
    schema: dict[str, Any],
    path: str,
) -> list[str]:
    violations: list[str] = []

    if not isinstance(schema, dict):
        return violations

    # type check
    schema_type = schema.get("type")
    if schema_type:
        expected_py = _TYPE_MAP.get(schema_type)
        if expected_py and not isinstance(data, expected_py):
            violations.append(
                f"{path}: expected type '{schema_type}', got '{type(data).__name__}'"
            )
            return violations  # further checks meaningless

    # required fields
    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                violations.append(f"{path}: required field '{req}' missing")

        # recurse into properties
        for prop, sub_schema in schema.get("properties", {}).items():
            if prop in data:
                violations.extend(_validate_object(data[prop], sub_schema, f"{path}.{prop}"))

    # array items
    if isinstance(data, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(data):
                violations.extend(_validate_object(item, items_schema, f"{path}[{i}]"))

    # string constraints
    if isinstance(data, str):
        min_len = schema.get("minLength")
        max_len = schema.get("maxLength")
        pattern = schema.get("pattern")
        if min_len is not None and len(data) < min_len:
            violations.append(f"{path}: string length {len(data)} < minLength {min_len}")
        if max_len is not None and len(data) > max_len:
            violations.append(f"{path}: string length {len(data)} > maxLength {max_len}")
        if pattern and not re.fullmatch(pattern, data):
            violations.append(f"{path}: '{data}' does not match pattern '{pattern}'")

    # numeric constraints
    if isinstance(data, (int, float)):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and data < minimum:
            violations.append(f"{path}: {data} < minimum {minimum}")
        if maximum is not None and data > maximum:
            violations.append(f"{path}: {data} > maximum {maximum}")

    # enum
    enum_vals = schema.get("enum")
    if enum_vals is not None and data not in enum_vals:
        violations.append(f"{path}: '{data}' not in enum {enum_vals}")

    return violations
