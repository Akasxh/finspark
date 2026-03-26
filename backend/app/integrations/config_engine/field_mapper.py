"""
FieldMapper — fuzzy string matching + semantic heuristics for Indian fintech fields.

Matching pipeline (highest-confidence wins):
  1. Exact match            → 1.0
  2. Alias lookup           → 0.95  (curated fintech alias table)
  3. Token-set ratio        → rapidfuzz.fuzz.token_set_ratio / 100
  4. Partial ratio          → rapidfuzz.fuzz.partial_ratio / 100
  5. Semantic group match   → boost applied when source/target share a semantic group
     (identity, tax, payment, address, loan, compliance)

Final confidence = weighted combination; anything below MIN_CONFIDENCE is dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from app.integrations.metadata import FieldSchema


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_CONFIDENCE: float = 0.40

# Weights for combining individual similarity signals
_W_TOKEN_SET: float = 0.50
_W_PARTIAL: float = 0.25
_W_SEMANTIC: float = 0.25

# Curated alias table — key is canonical adapter field name,
# values are known document-side synonyms (all lower-snake).
_FIELD_ALIASES: dict[str, list[str]] = {
    # Identity
    "pan_number": ["pan", "pan_no", "permanent_account_number", "income_tax_pan", "it_pan"],
    "aadhaar_number": [
        "aadhaar", "aadhar", "uid", "uidai_number", "unique_id", "aadhaar_no",
        "aadhar_no", "aadhaar_card_number",
    ],
    "voter_id": ["epic", "voter_card", "election_id", "voter_id_number"],
    "passport_number": ["passport", "passport_no", "travel_document"],
    "driving_license": ["dl_number", "driving_licence", "dl_no"],
    "full_name": ["name", "customer_name", "applicant_name", "borrower_name", "legal_name"],
    "date_of_birth": ["dob", "birth_date", "birthdate", "date_birth", "born_on"],
    "gender": ["sex", "applicant_gender", "gender_code"],
    # Contact
    "mobile_number": ["mobile", "phone", "mobile_no", "phone_number", "contact_number", "cell"],
    "email_address": ["email", "email_id", "emailid", "e_mail", "mail"],
    # Address
    "address_line1": ["address", "addr1", "street_address", "permanent_address", "current_address"],
    "address_line2": ["addr2", "address_line_2", "locality", "area"],
    "city": ["town", "city_name", "district"],
    "state": ["state_name", "province", "state_code"],
    "pincode": ["pin", "pin_code", "postal_code", "zip_code", "zip"],
    # Tax / compliance
    "gstin": ["gst_number", "gstin_number", "gst_registration", "gst_no"],
    "tan_number": ["tan", "tax_deduction_number", "tds_tan"],
    "cin_number": ["cin", "company_identification_number", "corporate_id"],
    # Banking / payment
    "account_number": ["bank_account", "account_no", "acct_number", "bank_acct"],
    "ifsc_code": ["ifsc", "bank_ifsc", "ifsc_number", "rtgs_code"],
    "bank_name": ["bank", "lender_name", "financial_institution"],
    "upi_id": ["vpa", "upi_address", "upi_handle"],
    # Loan
    "loan_amount": ["amount", "loan_value", "principal", "sanctioned_amount", "disbursal_amount"],
    "loan_tenure": ["tenure", "repayment_period", "loan_period", "emi_tenure"],
    "interest_rate": ["rate", "roi", "rate_of_interest", "annual_rate"],
    "emi_amount": ["emi", "monthly_installment", "monthly_payment"],
    "cibil_score": ["credit_score", "bureau_score", "cibil", "credit_rating"],
    # Company
    "company_name": ["business_name", "org_name", "entity_name", "firm_name"],
    "incorporation_date": ["date_of_incorporation", "company_founded", "reg_date"],
    "registered_address": ["reg_address", "company_address", "office_address"],
}

# Reverse index: synonym → canonical
_ALIAS_REVERSE: dict[str, str] = {
    syn: canonical
    for canonical, synonyms in _FIELD_ALIASES.items()
    for syn in synonyms
}

# Semantic groups — fields in the same group get a similarity boost
_SEMANTIC_GROUPS: dict[str, list[str]] = {
    "identity": [
        "pan_number", "aadhaar_number", "voter_id", "passport_number",
        "driving_license", "full_name", "date_of_birth", "gender",
    ],
    "contact": ["mobile_number", "email_address"],
    "address": ["address_line1", "address_line2", "city", "state", "pincode"],
    "tax": ["gstin", "tan_number", "cin_number", "pan_number"],
    "banking": ["account_number", "ifsc_code", "bank_name", "upi_id"],
    "loan": ["loan_amount", "loan_tenure", "interest_rate", "emi_amount", "cibil_score"],
    "company": ["company_name", "incorporation_date", "registered_address", "gstin", "cin_number"],
}

# Pre-build: field → group
_FIELD_TO_GROUP: dict[str, str] = {
    f: g for g, fields in _SEMANTIC_GROUPS.items() for f in fields
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FieldMatch:
    """Single matched pair with confidence and provenance."""

    source_field: str
    target_field: str
    confidence: float                          # 0.0 – 1.0
    match_method: str                          # "exact" | "alias" | "fuzzy" | "semantic_boost"
    transform_hint: str | None = None          # e.g. "strip_spaces", "upper", "date_to_iso"
    is_required: bool = False                  # driven by target adapter FieldSchema
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_field": self.source_field,
            "target_field": self.target_field,
            "confidence": round(self.confidence, 4),
            "match_method": self.match_method,
            "transform_hint": self.transform_hint,
            "is_required": self.is_required,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(name: str) -> str:
    """Lower-snake: strip punctuation, collapse whitespace, replace camelCase."""
    # CamelCase → snake_case
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    # replace non-alphanum with underscore
    name = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return name.strip("_")


_TRANSFORM_HINTS: dict[str, str] = {
    "pan_number": "upper_alpha_strip",
    "aadhaar_number": "digits_only_12",
    "gstin": "upper_alphanum_15",
    "ifsc_code": "upper_alpha_11",
    "pincode": "digits_only_6",
    "mobile_number": "digits_only_10_strip_country",
    "date_of_birth": "date_to_ddmmyyyy",
    "email_address": "lower_strip",
    "account_number": "digits_only",
    "loan_amount": "paise_to_rupees",
    "interest_rate": "percent_to_decimal",
    "cibil_score": "int_cast",
    "gender": "gender_code_m_f_t",
}


# ---------------------------------------------------------------------------
# FieldMapper
# ---------------------------------------------------------------------------

class FieldMapper:
    """
    Match a list of source fields (from parsed document) against a target
    adapter's FieldSchema list using fuzzy + semantic heuristics.

    Usage::

        mapper = FieldMapper(target_fields=adapter.metadata.supported_fields)
        matches = mapper.map(source_fields=["PAN Number", "Aadhaar No", "GSTIN"])
    """

    def __init__(
        self,
        target_fields: tuple[FieldSchema, ...],
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        self._targets = target_fields
        self._min_confidence = min_confidence
        # Normalised target names → original FieldSchema
        self._target_index: dict[str, FieldSchema] = {
            _normalise(fs.name): fs for fs in target_fields
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map(
        self,
        source_fields: list[str],
        deduplicate: bool = True,
    ) -> list[FieldMatch]:
        """
        Return best match for each source field above min_confidence.

        When deduplicate=True each target is assigned to at most one source
        (the one with the highest confidence).
        """
        candidates: list[FieldMatch] = []
        for src in source_fields:
            match = self._best_match(src)
            if match is not None:
                candidates.append(match)

        if not deduplicate:
            return candidates

        return self._deduplicate(candidates)

    def score_pair(self, source: str, target: str) -> float:
        """Return confidence for a specific (source, target) pair. Useful for dry-runs."""
        norm_src = _normalise(source)
        norm_tgt = _normalise(target)
        schema = self._target_index.get(norm_tgt)
        return self._compute_confidence(norm_src, norm_tgt, schema)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _best_match(self, source: str) -> FieldMatch | None:
        norm_src = _normalise(source)
        best_conf = 0.0
        best_tgt_name: str | None = None
        best_method = "fuzzy"

        # 1. Exact match
        if norm_src in self._target_index:
            schema = self._target_index[norm_src]
            return self._make_match(source, norm_src, schema, 1.0, "exact")

        # 2. Alias lookup (src → canonical, then check if canonical is a target)
        canonical = _ALIAS_REVERSE.get(norm_src)
        if canonical and canonical in self._target_index:
            schema = self._target_index[canonical]
            return self._make_match(source, canonical, schema, 0.95, "alias")

        # 3. Fuzzy sweep over all targets
        for norm_tgt, schema in self._target_index.items():
            conf = self._compute_confidence(norm_src, norm_tgt, schema)
            if conf > best_conf:
                best_conf = conf
                best_tgt_name = norm_tgt
                best_method = "fuzzy"

        if best_tgt_name is None or best_conf < self._min_confidence:
            return None

        schema = self._target_index[best_tgt_name]
        return self._make_match(source, best_tgt_name, schema, best_conf, best_method)

    def _compute_confidence(
        self,
        norm_src: str,
        norm_tgt: str,
        schema: FieldSchema | None,
    ) -> float:
        token_set = fuzz.token_set_ratio(norm_src, norm_tgt) / 100.0
        partial = fuzz.partial_ratio(norm_src, norm_tgt) / 100.0

        # Semantic group boost: same group → 0.15 bonus on semantic weight
        src_group = _FIELD_TO_GROUP.get(norm_src) or _FIELD_TO_GROUP.get(
            _ALIAS_REVERSE.get(norm_src, ""), ""
        )
        tgt_group = _FIELD_TO_GROUP.get(norm_tgt, "")
        semantic_sim = 1.0 if (src_group and src_group == tgt_group) else 0.0

        return (
            _W_TOKEN_SET * token_set
            + _W_PARTIAL * partial
            + _W_SEMANTIC * semantic_sim
        )

    def _make_match(
        self,
        original_source: str,
        norm_target: str,
        schema: FieldSchema,
        confidence: float,
        method: str,
    ) -> FieldMatch:
        notes: list[str] = []
        if schema.pattern:
            notes.append(f"target expects pattern: {schema.pattern}")
        if schema.max_length:
            notes.append(f"target max_length: {schema.max_length}")
        if schema.enum_values:
            notes.append(f"target enum_values: {schema.enum_values}")

        return FieldMatch(
            source_field=original_source,
            target_field=schema.name,
            confidence=min(confidence, 1.0),
            match_method=method,
            transform_hint=_TRANSFORM_HINTS.get(norm_target),
            is_required=schema.required,
            notes=notes,
        )

    @staticmethod
    def _deduplicate(matches: list[FieldMatch]) -> list[FieldMatch]:
        """Keep highest-confidence match per target field."""
        best: dict[str, FieldMatch] = {}
        for m in matches:
            existing = best.get(m.target_field)
            if existing is None or m.confidence > existing.confidence:
                best[m.target_field] = m
        return sorted(best.values(), key=lambda x: x.confidence, reverse=True)
