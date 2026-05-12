"""Custom transformation engine for field mapping pipelines.

Public surface:

* :func:`apply_transformation` — the safe pipe-chained DSL used by configurations
  with a ``transformation_expr`` set on a :class:`~finspark.schemas.configurations.FieldMapping`.
* :class:`TransformationEngine` — legacy named-transform engine that powers the
  existing ``transformation`` enum (kept for backward compatibility).
* :class:`DSLError` — raised by the DSL on parse/runtime errors.
"""

from finspark.services.transformation.dsl import (
    DSLError,
    apply_transformation,
    parse_expression,
    validate_expression,
)
from finspark.services.transformation.engine import TransformationEngine

__all__ = [
    "DSLError",
    "TransformationEngine",
    "apply_transformation",
    "parse_expression",
    "validate_expression",
]
