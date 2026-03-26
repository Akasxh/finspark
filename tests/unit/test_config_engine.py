"""
Unit tests for the auto-configuration generation engine.

Tests cover:
  - FieldMapper: exact, alias, fuzzy, deduplication
  - SchemaTransformer: individual ops, auto-register, flatten/unflatten
  - ConfigGenerator: full pipeline, template generation, missing required
  - ConfigDiffEngine: additions, deletions, modifications, sensitive masking
"""

from __future__ import annotations

from app.integrations.config_engine.config_diff import ConfigDiffEngine, DiffOp
from app.integrations.config_engine.config_generator import ConfigGenerator
from app.integrations.config_engine.field_mapper import FieldMapper, _normalise
from app.integrations.config_engine.schema_transformer import SchemaTransformer, TransformRule
from app.integrations.metadata import AdapterMetadata, FieldSchema, RateLimit
from app.integrations.types import AuthType

# ---------------------------------------------------------------------------
# Fixtures — reusable adapter metadata objects
# ---------------------------------------------------------------------------


def _kyc_fields() -> tuple[FieldSchema, ...]:
    return (
        FieldSchema(
            "pan_number",
            "str",
            required=True,
            description="PAN card number",
            pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$",
            max_length=10,
        ),
        FieldSchema(
            "aadhaar_number",
            "str",
            required=True,
            description="12-digit Aadhaar UID",
            pattern=r"^\d{12}$",
            max_length=12,
        ),
        FieldSchema(
            "full_name", "str", required=True, description="Legal full name", max_length=100
        ),
        FieldSchema("date_of_birth", "str", required=True, description="DOB in YYYY-MM-DD"),
        FieldSchema(
            "mobile_number",
            "str",
            required=True,
            description="10-digit mobile",
            pattern=r"^[6-9]\d{9}$",
            max_length=10,
        ),
        FieldSchema("email_address", "str", required=False, description="Email ID"),
        FieldSchema(
            "gender", "str", required=False, description="M/F/T", enum_values=("M", "F", "T")
        ),
        FieldSchema(
            "pincode",
            "str",
            required=False,
            description="6-digit PIN",
            pattern=r"^\d{6}$",
            max_length=6,
        ),
    )


def _kyc_metadata() -> AdapterMetadata:
    return AdapterMetadata(
        kind="kyc",
        version="v1",
        display_name="KYC Verify v1",
        provider="Aadhaar Bridge",
        supported_fields=_kyc_fields(),
        auth_types=(AuthType.API_KEY,),
        rate_limit=RateLimit(requests_per_second=10),
        endpoint_template="https://api.kyc-provider.in/v1/verify",
    )


def _gst_fields() -> tuple[FieldSchema, ...]:
    return (
        FieldSchema(
            "gstin",
            "str",
            required=True,
            description="15-char GSTIN",
            pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
            max_length=15,
        ),
        FieldSchema("company_name", "str", required=True, description="Registered company name"),
        FieldSchema(
            "state_code",
            "str",
            required=True,
            description="2-digit GST state code",
            pattern=r"^\d{2}$",
        ),
        FieldSchema("filing_period", "str", required=False, description="e.g. 2024-01"),
    )


def _gst_metadata() -> AdapterMetadata:
    return AdapterMetadata(
        kind="gst",
        version="v1",
        display_name="GST Lookup v1",
        provider="GSTN",
        supported_fields=_gst_fields(),
        auth_types=(AuthType.API_KEY,),
        rate_limit=RateLimit(requests_per_second=5),
        endpoint_template="https://api.gst.gov.in/commonapi/v1.1/search",
    )


# ---------------------------------------------------------------------------
# FieldMapper tests
# ---------------------------------------------------------------------------


class TestFieldMapper:
    def test_exact_match(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        matches = mapper.map(["pan_number"])
        assert len(matches) == 1
        assert matches[0].target_field == "pan_number"
        assert matches[0].confidence == 1.0
        assert matches[0].match_method == "exact"

    def test_alias_match_aadhaar(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        matches = mapper.map(["aadhar_no"])
        assert any(m.target_field == "aadhaar_number" for m in matches)
        top = next(m for m in matches if m.target_field == "aadhaar_number")
        assert top.confidence >= 0.90
        assert top.match_method == "alias"

    def test_alias_match_pan_synonyms(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        for syn in ["PAN", "pan_no", "Permanent Account Number"]:
            matches = mapper.map([syn])
            assert any(m.target_field == "pan_number" for m in matches), f"Failed for {syn!r}"

    def test_fuzzy_match_dob(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        matches = mapper.map(["birth_date"])
        assert any(m.target_field == "date_of_birth" for m in matches)

    def test_fuzzy_match_mobile(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        matches = mapper.map(["phone_number"])
        assert any(m.target_field == "mobile_number" for m in matches)

    def test_deduplication(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        # Both "pan_no" and "PAN" should map to pan_number; dedup keeps best
        matches = mapper.map(["pan_no", "PAN"])
        pan_matches = [m for m in matches if m.target_field == "pan_number"]
        assert len(pan_matches) == 1

    def test_below_threshold_excluded(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields(), min_confidence=0.9)
        matches = mapper.map(["completely_unrelated_field_xyz"])
        assert not any(m.confidence >= 0.9 for m in matches)

    def test_is_required_propagated(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        matches = mapper.map(["pan_number"])
        pan = next(m for m in matches if m.target_field == "pan_number")
        assert pan.is_required is True

    def test_transform_hint_present(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        matches = mapper.map(["pan_number"])
        pan = next(m for m in matches if m.target_field == "pan_number")
        assert pan.transform_hint is not None

    def test_score_pair(self) -> None:
        mapper = FieldMapper(target_fields=_kyc_fields())
        score = mapper.score_pair("aadhaar_no", "aadhaar_number")
        assert score > 0.5

    def test_normalise(self) -> None:
        # All-caps "PANNumber" — no lower→upper boundary, collapses to lowercase
        assert _normalise("PANNumber") == "pannumber"
        assert _normalise("  aadhaar-no  ") == "aadhaar_no"
        # camelCase boundary fires for lower→upper transition
        assert _normalise("dateOfBirth") == "date_of_birth"
        assert _normalise("loanAmount") == "loan_amount"

    def test_gstin_alias(self) -> None:
        mapper = FieldMapper(target_fields=_gst_fields())
        matches = mapper.map(["gst_number"])
        assert any(m.target_field == "gstin" for m in matches)


# ---------------------------------------------------------------------------
# SchemaTransformer tests
# ---------------------------------------------------------------------------


class TestSchemaTransformer:
    def test_strip_upper(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("pan", operations=["strip", "upper"]))
        result, log = tr.transform({"pan": " abcde1234f "})
        assert result["pan"] == "ABCDE1234F"
        assert "strip" in log["pan"]
        assert "upper" in log["pan"]

    def test_digits_only(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("aadhaar", operations=["strip", "digits_only"]))
        result, _ = tr.transform({"aadhaar": "1234 5678 9012"})
        assert result["aadhaar"] == "123456789012"

    def test_normalise_mobile(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("mobile", operations=["normalise_mobile"]))
        result, _ = tr.transform({"mobile": "+919876543210"})
        assert result["mobile"] == "9876543210"

    def test_normalise_mobile_with_country_code(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("mob", operations=["normalise_mobile"]))
        result, _ = tr.transform({"mob": "919876543210"})
        assert result["mob"] == "9876543210"

    def test_date_to_iso(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("dob", operations=["date_to_iso"]))
        result, _ = tr.transform({"dob": "15/08/1947"})
        assert result["dob"] == "1947-08-15"

    def test_date_to_ddmmyyyy(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("dob", operations=["date_to_ddmmyyyy"]))
        result, _ = tr.transform({"dob": "1947-08-15"})
        assert result["dob"] == "15/08/1947"

    def test_percent_to_decimal(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("roi", operations=["percent_to_decimal"]))
        result, _ = tr.transform({"roi": "12.5"})
        assert abs(result["roi"] - 0.125) < 1e-9

    def test_paise_to_rupees(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("amount", operations=["paise_to_rupees"]))
        result, _ = tr.transform({"amount": 100000})
        assert result["amount"] == 1000.0

    def test_type_cast_int(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("score", operations=["type_cast"], target_type="int"))
        result, _ = tr.transform({"score": "750"})
        assert result["score"] == 750
        assert isinstance(result["score"], int)

    def test_type_cast_bool(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("flag", operations=["type_cast"], target_type="bool"))
        for val, expected in [
            ("true", True),
            ("1", True),
            ("yes", True),
            ("false", False),
            ("0", False),
        ]:
            result, _ = tr.transform({"flag": val})
            assert result["flag"] is expected, f"Failed for {val!r}"

    def test_validate_pan_pass(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("pan", operations=["strip", "upper", "validate_pan"]))
        result, log = tr.transform({"pan": " abcde1234f "})
        assert result["pan"] == "ABCDE1234F"
        assert not any("FAILED" in op for op in log["pan"])

    def test_validate_pan_fail(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("pan", operations=["strip", "upper", "validate_pan"]))
        result, log = tr.transform({"pan": "INVALID"})
        assert any("FAILED" in op for op in log["pan"])

    def test_mask_aadhaar(self) -> None:
        assert SchemaTransformer.mask_aadhaar("123456789012") == "XXXX-XXXX-9012"

    def test_mask_pan(self) -> None:
        assert SchemaTransformer.mask_pan("ABCDE1234F") == "ABXXXXXXX F".replace(" ", "")

    def test_flatten_nested(self) -> None:
        data = {
            "applicant": {
                "identity": {"pan": "ABCDE1234F", "aadhaar": "123456789012"},
                "contact": {"mobile": "9876543210"},
            },
            "loan_amount": 500000,
        }
        fr = SchemaTransformer.flatten(data)
        assert fr.flat["applicant.identity.pan"] == "ABCDE1234F"
        assert fr.flat["applicant.contact.mobile"] == "9876543210"
        assert fr.flat["loan_amount"] == 500000

    def test_unflatten(self) -> None:
        flat = {"address.city": "Mumbai", "address.pin": "400001", "name": "Ravi"}
        nested = SchemaTransformer.unflatten(flat)
        assert nested["address"]["city"] == "Mumbai"
        assert nested["name"] == "Ravi"

    def test_auto_register_pan(self) -> None:
        tr = SchemaTransformer()
        tr.auto_register(["pan_number"])
        result, log = tr.transform({"pan_number": " abcde1234f "})
        assert result["pan_number"] == "ABCDE1234F"

    def test_auto_register_mobile(self) -> None:
        tr = SchemaTransformer()
        tr.auto_register(["mobile_number"])
        result, _ = tr.transform({"mobile_number": "+919876543210"})
        assert result["mobile_number"] == "9876543210"

    def test_regex_extract(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("raw", operations=["regex_extract:[A-Z]{5}[0-9]{4}[A-Z]"]))
        result, _ = tr.transform({"raw": "Customer PAN: ABCDE1234F, verified"})
        assert result["raw"] == "ABCDE1234F"

    def test_field_missing_skipped(self) -> None:
        tr = SchemaTransformer()
        tr.register_rule(TransformRule("pan_number", operations=["upper"]))
        result, log = tr.transform({"other_field": "value"})
        assert "pan_number" not in log
        assert result == {"other_field": "value"}


# ---------------------------------------------------------------------------
# ConfigGenerator tests
# ---------------------------------------------------------------------------


class TestConfigGenerator:
    def test_basic_kyc_generation(self) -> None:
        meta = _kyc_metadata()
        gen = ConfigGenerator(meta, min_confidence=0.45)
        doc = {
            "PAN": "ABCDE1234F",
            "aadhaar_no": "123456789012",
            "name": "Ravi Kumar",
            "dob": "15/08/1985",
            "mobile": "9876543210",
            "email": "ravi@example.com",
        }
        cfg = gen.generate(doc)
        assert cfg.adapter_kind == "kyc"
        assert cfg.adapter_version == "v1"
        assert "pan_number" in cfg.config_data or len(cfg.field_entries) > 0
        assert 0.0 <= cfg.overall_confidence <= 1.0

    def test_missing_required_detected(self) -> None:
        meta = _kyc_metadata()
        gen = ConfigGenerator(meta, min_confidence=0.50)
        # Provide only some fields
        doc = {"email": "test@example.com"}
        cfg = gen.generate(doc)
        # pan_number, aadhaar_number, full_name, date_of_birth, mobile_number are required
        assert "pan_number" in cfg.missing_required or len(cfg.missing_required) >= 1

    def test_nested_document_flattened(self) -> None:
        meta = _kyc_metadata()
        gen = ConfigGenerator(meta, min_confidence=0.45)
        doc = {
            "applicant": {
                "pan_number": "ABCDE1234F",
                "mobile_number": "9876543210",
            }
        }
        cfg = gen.generate(doc)
        # Nested pan_number should be found via flattening
        matched_targets = {e.target_field for e in cfg.field_entries}
        assert "pan_number" in matched_targets or "mobile_number" in matched_targets

    def test_overall_confidence_range(self) -> None:
        meta = _kyc_metadata()
        gen = ConfigGenerator(meta)
        cfg = gen.generate({})
        assert 0.0 <= cfg.overall_confidence <= 1.0

    def test_generate_template(self) -> None:
        meta = _kyc_metadata()
        gen = ConfigGenerator(meta)
        template = gen.generate_template()
        assert template["_adapter"]["kind"] == "kyc"
        assert "pan_number" in template["fields"]
        assert template["fields"]["pan_number"]["required"] is True

    def test_to_json_serialisable(self) -> None:
        meta = _kyc_metadata()
        gen = ConfigGenerator(meta)
        doc = {"PAN": "ABCDE1234F", "mobile": "9876543210"}
        cfg = gen.generate(doc)
        import json

        raw = cfg.to_json()
        parsed = json.loads(raw)
        assert "config_data" in parsed
        assert "field_entries" in parsed
        assert "overall_confidence" in parsed

    def test_include_unmatched_passthrough(self) -> None:
        meta = _kyc_metadata()
        gen = ConfigGenerator(meta, include_unmatched_in_config=True)
        doc = {"totally_unknown_field": "some_value"}
        cfg = gen.generate(doc)
        # With include_unmatched=True, unknown fields should appear
        passthrough = [e for e in cfg.field_entries if e.match_method == "passthrough"]
        assert len(passthrough) >= 1

    def test_validation_errors_captured(self) -> None:
        meta = _kyc_metadata()
        gen = ConfigGenerator(meta, min_confidence=0.45)
        doc = {"pan_number": "INVALID_PAN"}
        cfg = gen.generate(doc)
        # pan_number has a pattern — invalid value should generate a validation error
        assert "pan_number" in cfg.validation_errors

    def test_gst_generation(self) -> None:
        meta = _gst_metadata()
        gen = ConfigGenerator(meta, min_confidence=0.45)
        doc = {
            "gst_number": "27AABCU9603R1ZX",
            "business_name": "Acme Pvt Ltd",
            "state_code": "27",
        }
        cfg = gen.generate(doc)
        assert cfg.adapter_kind == "gst"
        assert len(cfg.field_entries) >= 1


# ---------------------------------------------------------------------------
# ConfigDiffEngine tests
# ---------------------------------------------------------------------------


class TestConfigDiffEngine:
    def test_no_changes(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({"pan": "ABCDE1234F"}, {"pan": "ABCDE1234F"})
        assert not diff.has_changes

    def test_addition(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({}, {"pan": "ABCDE1234F"})
        assert len(diff.additions) == 1
        assert diff.additions[0].path == "pan"
        assert diff.additions[0].op == DiffOp.ADDED
        assert diff.additions[0].new_value == "ABCDE1234F"

    def test_deletion(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({"pan": "ABCDE1234F"}, {})
        assert len(diff.deletions) == 1
        assert diff.deletions[0].path == "pan"
        assert diff.deletions[0].op == DiffOp.DELETED

    def test_modification(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({"score": 700}, {"score": 750})
        assert len(diff.modifications) == 1
        m = diff.modifications[0]
        assert m.op == DiffOp.MODIFIED
        assert m.old_value == 700
        assert m.new_value == 750

    def test_nested_diff(self) -> None:
        engine = ConfigDiffEngine()
        old = {"address": {"city": "Delhi", "pincode": "110001"}}
        new = {"address": {"city": "Mumbai", "pincode": "110001"}}
        diff = engine.diff(old, new)
        assert len(diff.modifications) == 1
        assert diff.modifications[0].path == "address.city"

    def test_sensitive_masking(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({"api_key": "old-secret"}, {"api_key": "new-secret"})
        m = diff.modifications[0]
        assert m.old_value == "***"
        assert m.new_value == "***"

    def test_type_change_noted(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({"amount": "5000"}, {"amount": 5000})
        assert diff.modifications[0].description != ""

    def test_include_unchanged(self) -> None:
        engine = ConfigDiffEngine(include_unchanged=True)
        diff = engine.diff({"pan": "ABCDE1234F"}, {"pan": "ABCDE1234F"})
        assert len(diff.unchanged) == 1
        assert not diff.has_changes

    def test_summary_format(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff(
            {"pan": "OLD", "loan_amount": 100000},
            {"pan": "NEW", "gstin": "27AABCU9603R1ZX"},
        )
        summary = diff.summary()
        assert "added" in summary.lower() or "ADDED" in summary
        assert "deleted" in summary.lower() or "DELETED" in summary
        assert "modified" in summary.lower() or "MODIFIED" in summary

    def test_to_json(self) -> None:
        import json

        engine = ConfigDiffEngine()
        diff = engine.diff({"x": 1}, {"x": 2, "y": 3})
        raw = diff.to_json()
        parsed = json.loads(raw)
        assert parsed["has_changes"] is True
        assert parsed["summary"]["added"] == 1
        assert parsed["summary"]["modified"] == 1

    def test_as_patch(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({"a": 1}, {"a": 2, "b": 3})
        patch = diff.as_patch()
        ops = patch["patch"]
        op_types = {o["op"] for o in ops}
        assert "replace" in op_types
        assert "add" in op_types

    def test_list_diff(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({"tags": ["kyc", "credit"]}, {"tags": ["kyc", "gst", "payment"]})
        assert len(diff.modifications) == 1
        assert "list length" in diff.modifications[0].description

    def test_diff_generated_json(self) -> None:
        engine = ConfigDiffEngine()
        import json

        old_json = json.dumps({"config_data": {"pan": "OLD", "mobile": "9876543210"}})
        new_json = json.dumps({"config_data": {"pan": "NEW", "mobile": "9876543210"}})
        diff = engine.diff_generated(old_json, new_json)
        assert len(diff.modifications) == 1
        assert diff.modifications[0].path == "pan"

    def test_empty_configs(self) -> None:
        engine = ConfigDiffEngine()
        diff = engine.diff({}, {})
        assert not diff.has_changes
