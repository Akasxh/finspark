"""
SchemaTransformer — type casting, format conversion, and nested field flattening.

Each TransformRule describes a single transformation step.  Rules are composable:
a field can chain through multiple rules (e.g. strip whitespace → upper → validate regex).

Built-in rule types:
  - type_cast     : str↔int↔float↔bool
  - format_conv   : date formats, phone normalisation, currency units
  - upper / lower : case normalisation
  - strip         : remove whitespace / non-numeric chars
  - regex_extract : extract sub-pattern from raw value
  - flatten       : expand a nested dict key "address.city" → "city"
  - mask          : partially mask sensitive fields (PAN, Aadhaar)
  - validate      : assert value matches pattern (raises ValueError on failure)

Usage::

    tr = SchemaTransformer()
    tr.register_rule(TransformRule(field="pan_number", operations=["strip", "upper", "validate_pan"]))
    result = tr.transform({"pan_number": " abcde1234f "})
    # → {"pan_number": "ABCDE1234F"}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Regex validators for Indian fintech identifiers
# ---------------------------------------------------------------------------

_VALIDATORS: dict[str, re.Pattern[str]] = {
    "pan": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    "aadhaar": re.compile(r"^\d{12}$"),
    "gstin": re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"),
    "ifsc": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
    "pincode": re.compile(r"^\d{6}$"),
    "mobile_in": re.compile(r"^[6-9]\d{9}$"),
    "tan": re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$"),
    "cin": re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$"),
    "upi": re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z]{3,}$"),
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
}

# Date format candidates tried in order for auto-detection
_DATE_FORMATS: list[str] = [
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
    "%d/%m/%y", "%d-%m-%y",
    "%Y%m%d", "%d%m%Y",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TransformRule:
    """
    Declarative specification for transforming a single field.

    operations is an ordered list of named operation strings.
    Custom callables can be injected via the custom_ops mapping.
    """

    field: str
    operations: list[str] = field(default_factory=list)
    # Inject per-rule custom ops: op_name → fn(value) → value
    custom_ops: dict[str, Callable[[Any], Any]] = field(default_factory=dict)
    # Target dtype for type_cast
    target_type: str = "str"                   # "str" | "int" | "float" | "bool"
    # Target date format for date conversions
    date_output_format: str = "%Y-%m-%d"       # ISO 8601 default


@dataclass
class FlattenResult:
    """Output of flattening a nested document payload."""

    flat: dict[str, Any]
    origin_paths: dict[str, str]               # flat_key → original dotted path


# ---------------------------------------------------------------------------
# SchemaTransformer
# ---------------------------------------------------------------------------

class SchemaTransformer:
    """
    Apply transformation rules to a field-value dictionary.

    Rules are registered by field name.  `transform()` applies them and
    returns the mutated dict plus a per-field log of applied operations.
    """

    def __init__(self) -> None:
        self._rules: dict[str, TransformRule] = {}

    # ------------------------------------------------------------------
    # Rule registration
    # ------------------------------------------------------------------

    def register_rule(self, rule: TransformRule) -> None:
        self._rules[rule.field] = rule

    def register_rules(self, rules: list[TransformRule]) -> None:
        for r in rules:
            self.register_rule(r)

    def auto_register(self, field_names: list[str]) -> None:
        """
        Automatically derive a rule set from field names using curated heuristics.
        Existing rules are not overwritten.
        """
        for fname in field_names:
            if fname not in self._rules:
                rule = _infer_rule(fname)
                if rule:
                    self._rules[fname] = rule

    # ------------------------------------------------------------------
    # Transform
    # ------------------------------------------------------------------

    def transform(
        self,
        data: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, list[str]]]:
        """
        Apply all registered rules to *data*.

        Returns:
            transformed_data: mutated copy
            applied_ops_log:  field → list of op names executed
        """
        result: dict[str, Any] = dict(data)
        log: dict[str, list[str]] = {}

        for fname, rule in self._rules.items():
            if fname not in result:
                continue
            value = result[fname]
            applied: list[str] = []
            for op in rule.operations:
                try:
                    value, op_name = _apply_op(op, value, rule)
                    applied.append(op_name)
                except (ValueError, TypeError, AttributeError) as exc:
                    applied.append(f"FAILED:{op}({exc})")
                    break
            result[fname] = value
            log[fname] = applied

        return result, log

    # ------------------------------------------------------------------
    # Flattening
    # ------------------------------------------------------------------

    @staticmethod
    def flatten(
        data: dict[str, Any],
        sep: str = ".",
        max_depth: int = 10,
    ) -> FlattenResult:
        """
        Recursively flatten a nested dict.

        {"address": {"city": "Mumbai", "pin": "400001"}}
        → {"address.city": "Mumbai", "address.pin": "400001"}
        """
        flat: dict[str, Any] = {}
        origins: dict[str, str] = {}
        _flatten_recursive(data, "", sep, flat, origins, 0, max_depth)
        return FlattenResult(flat=flat, origin_paths=origins)

    @staticmethod
    def unflatten(data: dict[str, Any], sep: str = ".") -> dict[str, Any]:
        """Inverse of flatten — reconstruct nested structure from dotted keys."""
        result: dict[str, Any] = {}
        for key, val in data.items():
            parts = key.split(sep)
            d = result
            for part in parts[:-1]:
                d = d.setdefault(part, {})
            d[parts[-1]] = val
        return result

    # ------------------------------------------------------------------
    # Individual converters (also callable externally)
    # ------------------------------------------------------------------

    @staticmethod
    def convert_date(value: str, output_format: str = "%Y-%m-%d") -> str:
        """Auto-detect input date format and convert to output_format."""
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(str(value).strip(), fmt)
                return dt.strftime(output_format)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date {value!r} — tried formats: {_DATE_FORMATS}")

    @staticmethod
    def normalise_mobile(value: str) -> str:
        """Strip country code, spaces, dashes → 10-digit Indian mobile."""
        digits = re.sub(r"\D", "", str(value))
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if len(digits) != 10:
            raise ValueError(f"Mobile {value!r} does not reduce to 10 digits")
        return digits

    @staticmethod
    def mask_aadhaar(value: str) -> str:
        """Return XXXX-XXXX-<last4>."""
        digits = re.sub(r"\D", "", str(value))
        if len(digits) != 12:
            raise ValueError("Aadhaar must be 12 digits")
        return f"XXXX-XXXX-{digits[-4:]}"

    @staticmethod
    def mask_pan(value: str) -> str:
        """Return <first2>XXXXXXX<last1>."""
        v = str(value).upper().strip()
        if len(v) != 10:
            raise ValueError("PAN must be 10 characters")
        return f"{v[:2]}XXXXXXX{v[-1]}"

    @staticmethod
    def paise_to_rupees(value: Any) -> float:
        """Convert integer paise to float rupees."""
        return float(value) / 100.0

    @staticmethod
    def rupees_to_paise(value: Any) -> int:
        """Convert float rupees to integer paise (round half-up)."""
        return round(float(value) * 100)

    @staticmethod
    def percent_to_decimal(value: Any) -> float:
        """12.5 (%) → 0.125."""
        v = float(value)
        return v / 100.0 if v > 1.0 else v

    @staticmethod
    def validate_field(value: str, validator_key: str) -> str:
        """Raise ValueError if value does not match the named validator pattern."""
        pattern = _VALIDATORS.get(validator_key)
        if pattern is None:
            raise KeyError(f"Unknown validator {validator_key!r}")
        if not pattern.match(str(value)):
            raise ValueError(f"{value!r} does not match {validator_key} pattern")
        return value


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_op(
    op: str,
    value: Any,
    rule: TransformRule,
) -> tuple[Any, str]:
    """Dispatch a single operation name to its implementation."""
    # Custom ops take priority
    if op in rule.custom_ops:
        return rule.custom_ops[op](value), op

    match op:
        case "strip":
            return str(value).strip(), op
        case "upper":
            return str(value).upper(), op
        case "lower":
            return str(value).lower(), op
        case "digits_only":
            return re.sub(r"\D", "", str(value)), op
        case "alpha_only":
            return re.sub(r"[^a-zA-Z]", "", str(value)), op
        case "alphanum_only":
            return re.sub(r"[^a-zA-Z0-9]", "", str(value)), op
        case "type_cast":
            return _type_cast(value, rule.target_type), op
        case "date_to_iso":
            return SchemaTransformer.convert_date(value, "%Y-%m-%d"), op
        case "date_to_ddmmyyyy":
            return SchemaTransformer.convert_date(value, "%d/%m/%Y"), op
        case "normalise_mobile":
            return SchemaTransformer.normalise_mobile(value), op
        case "mask_aadhaar":
            return SchemaTransformer.mask_aadhaar(value), op
        case "mask_pan":
            return SchemaTransformer.mask_pan(value), op
        case "paise_to_rupees":
            return SchemaTransformer.paise_to_rupees(value), op
        case "rupees_to_paise":
            return SchemaTransformer.rupees_to_paise(value), op
        case "percent_to_decimal":
            return SchemaTransformer.percent_to_decimal(value), op
        case _ if op.startswith("validate_"):
            key = op[len("validate_"):]
            return SchemaTransformer.validate_field(str(value).upper().strip(), key), op
        case _ if op.startswith("regex_extract:"):
            pattern = op[len("regex_extract:"):]
            m = re.search(pattern, str(value))
            if not m:
                raise ValueError(f"regex_extract: pattern {pattern!r} not found in {value!r}")
            return m.group(0), op
        case _:
            raise ValueError(f"Unknown operation: {op!r}")


def _type_cast(value: Any, target: str) -> Any:
    match target:
        case "str":
            return str(value)
        case "int":
            return int(float(str(value).replace(",", "")))
        case "float":
            return float(str(value).replace(",", ""))
        case "bool":
            if isinstance(value, bool):
                return value
            return str(value).lower() in {"true", "1", "yes", "y"}
        case _:
            raise ValueError(f"Unknown target type: {target!r}")


def _flatten_recursive(
    data: dict[str, Any],
    prefix: str,
    sep: str,
    flat: dict[str, Any],
    origins: dict[str, str],
    depth: int,
    max_depth: int,
) -> None:
    if depth > max_depth:
        return
    for key, val in data.items():
        full_key = f"{prefix}{sep}{key}" if prefix else key
        if isinstance(val, dict):
            _flatten_recursive(val, full_key, sep, flat, origins, depth + 1, max_depth)
        else:
            flat[full_key] = val
            origins[full_key] = full_key


def _infer_rule(fname: str) -> TransformRule | None:
    """Derive a default TransformRule from field name heuristics."""
    f = fname.lower()

    if "pan" in f:
        return TransformRule(fname, operations=["strip", "upper", "validate_pan"])
    if "aadhaar" in f or "aadhar" in f or "uid" in f:
        return TransformRule(fname, operations=["strip", "digits_only", "validate_aadhaar"])
    if "gstin" in f or "gst_number" in f:
        return TransformRule(fname, operations=["strip", "upper", "validate_gstin"])
    if "ifsc" in f:
        return TransformRule(fname, operations=["strip", "upper", "validate_ifsc"])
    if "pincode" in f or "pin_code" in f or "postal" in f:
        return TransformRule(fname, operations=["strip", "digits_only", "validate_pincode"])
    if "mobile" in f or "phone" in f:
        return TransformRule(fname, operations=["strip", "normalise_mobile", "validate_mobile_in"])
    if "email" in f:
        return TransformRule(fname, operations=["strip", "lower", "validate_email"])
    if "dob" in f or "date_of_birth" in f or "birth_date" in f:
        return TransformRule(fname, operations=["strip", "date_to_iso"])
    if "amount" in f or "loan_amount" in f:
        return TransformRule(fname, operations=["strip", "type_cast"], target_type="float")
    if "interest_rate" in f or "roi" in f:
        return TransformRule(fname, operations=["strip", "type_cast", "percent_to_decimal"], target_type="float")
    if "score" in f or "cibil" in f:
        return TransformRule(fname, operations=["strip", "type_cast"], target_type="int")
    if "name" in f:
        return TransformRule(fname, operations=["strip"])
    return None
