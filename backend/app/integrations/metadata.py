"""
AdapterMetadata — static descriptor attached to every adapter class.

Defines:
  - supported_fields    schema of accepted input fields (name, type, required, description)
  - auth_types          supported authentication mechanisms
  - rate_limit          requests/second and daily quota caps
  - endpoint_template   URL template (vars wrapped in {braces})
  - response_codes      map of HTTP status → semantic meaning
  - sandbox_url         test endpoint (can be None for adapters with local mocks)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.integrations.types import AuthType


@dataclass(frozen=True)
class FieldSchema:
    name: str
    dtype: str                  # "str" | "int" | "float" | "bool" | "date" | "enum"
    required: bool
    description: str
    example: Any = None
    enum_values: tuple[str, ...] = field(default_factory=tuple)
    max_length: int | None = None
    pattern: str | None = None  # regex for validation


@dataclass(frozen=True)
class RateLimit:
    requests_per_second: float
    daily_quota: int | None = None    # None → unlimited
    burst_size: int = 10              # token-bucket burst capacity


@dataclass(frozen=True)
class AdapterMetadata:
    kind: str
    version: str
    display_name: str
    provider: str                       # e.g. "CIBIL", "Aadhaar Bridge", "Razorpay"
    supported_fields: tuple[FieldSchema, ...]
    auth_types: tuple[AuthType, ...]
    rate_limit: RateLimit
    endpoint_template: str
    sandbox_url: str | None = None
    response_codes: dict[int, str] = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)
