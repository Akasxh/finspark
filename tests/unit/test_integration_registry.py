"""
Unit tests for the Integration Adapter Registry.

Coverage:
  - Registry registration and discovery
  - Version coexistence (v1 + v2)
  - Config validation (valid + invalid)
  - BaseAdapter validation / transform / execute lifecycle
  - Hook engine (pre_request, post_response, on_error)
  - Built-in hooks (correlation_id, pii_mask, rate_limit_guard)
  - All 5 concrete adapters in sandbox mode
  - AdapterMetadata field verification
"""

from __future__ import annotations

import re
from typing import Any

# Force adapter registration by importing the adapters package
import app.integrations.adapters  # noqa: F401
import pytest
from app.integrations import AdapterRegistry, get_registry
from app.integrations.adapters.credit_bureau import CIBILAdapterV1, CIBILAdapterV2
from app.integrations.adapters.gst import GSTAdapterV1
from app.integrations.adapters.kyc import KYCAdapterV1, KYCAdapterV2
from app.integrations.adapters.payment_gateway import PaymentGatewayAdapterV1
from app.integrations.adapters.sms_gateway import SMSGatewayAdapterV1
from app.integrations.config import (
    CreditBureauConfig,
    GSTConfig,
    KYCConfig,
    KYCConfigV2,
    PaymentGatewayConfig,
    SMSGatewayConfig,
    get_config_class,
    validate_config,
)
from app.integrations.hooks.builtin import RateLimitGuard, pii_mask_hook
from app.integrations.hooks.engine import HookContext, HookEngine, HookPhase, hook
from app.integrations.metadata import RateLimit
from app.integrations.types import AuthType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> AdapterRegistry:
    return get_registry()


@pytest.fixture()
def cibil_v1_config() -> dict[str, Any]:
    return {
        "api_key": "test-api-key-cibil-001",
        "member_id": "MBR12345",
        "sandbox_mode": True,
    }


@pytest.fixture()
def cibil_v2_config() -> dict[str, Any]:
    return {
        "api_key": "test-api-key-cibil-002",
        "member_id": "MBR12345",
        "sandbox_mode": True,
    }


@pytest.fixture()
def kyc_v1_config() -> dict[str, Any]:
    return {
        "client_id": "kyc-client-001",
        "client_secret": "secret-kyc-v1",
        "sandbox_mode": True,
    }


@pytest.fixture()
def kyc_v2_config() -> dict[str, Any]:
    return {
        "client_id": "kyc-client-002",
        "client_secret": "secret-kyc-v2",
        "sandbox_mode": True,
    }


@pytest.fixture()
def gst_config() -> dict[str, Any]:
    return {
        "gstn_username": "gstuser",
        "gstn_password": "gstpassword",
        "app_key": "appsecretkey1234",
        "sandbox_mode": True,
    }


@pytest.fixture()
def pg_config() -> dict[str, Any]:
    return {
        "key_id": "rzp_test_00000000000001",
        "key_secret": "secret-razorpay-key",
        "webhook_secret": "webhook-secret-key",
        "sandbox_mode": True,
    }


@pytest.fixture()
def sms_config() -> dict[str, Any]:
    return {
        "api_key": "kaleyra-api-key-001",
        "sender_id": "FINSRK",
        "dlt_entity_id": "1234567890123456789",
        "dlt_template_id": "9876543210987654321",
        "sandbox_mode": True,
    }


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    @pytest.mark.unit
    def test_all_adapters_registered(self, registry: AdapterRegistry) -> None:
        kinds = registry.list_kinds()
        assert "credit_bureau" in kinds
        assert "kyc" in kinds
        assert "gst" in kinds
        assert "payment_gateway" in kinds
        assert "sms_gateway" in kinds

    @pytest.mark.unit
    def test_version_coexistence_credit_bureau(self, registry: AdapterRegistry) -> None:
        versions = registry.list_versions("credit_bureau")
        assert "v1" in versions
        assert "v2" in versions

    @pytest.mark.unit
    def test_version_coexistence_kyc(self, registry: AdapterRegistry) -> None:
        versions = registry.list_versions("kyc")
        assert "v1" in versions
        assert "v2" in versions

    @pytest.mark.unit
    def test_latest_version_credit_bureau(self, registry: AdapterRegistry) -> None:
        latest = registry.latest_version("credit_bureau")
        assert latest == "v2"

    @pytest.mark.unit
    def test_has_returns_true_for_registered(self, registry: AdapterRegistry) -> None:
        assert registry.has("credit_bureau", "v1")
        assert registry.has("gst", "v1")

    @pytest.mark.unit
    def test_has_returns_false_for_unknown(self, registry: AdapterRegistry) -> None:
        assert not registry.has("credit_bureau", "v99")
        assert not registry.has("unknown_kind", "v1")

    @pytest.mark.unit
    def test_get_raises_for_unknown_adapter(
        self, registry: AdapterRegistry, cibil_v1_config: dict[str, Any]
    ) -> None:
        with pytest.raises(KeyError, match="No adapter registered"):
            registry.get("nonexistent", "v1", cibil_v1_config)

    @pytest.mark.unit
    def test_get_returns_correct_adapter_class(
        self, registry: AdapterRegistry, cibil_v1_config: dict[str, Any]
    ) -> None:
        adapter = registry.get("credit_bureau", "v1", cibil_v1_config)
        assert isinstance(adapter, CIBILAdapterV1)

    @pytest.mark.unit
    def test_get_latest_returns_v2_for_credit_bureau(
        self, registry: AdapterRegistry, cibil_v2_config: dict[str, Any]
    ) -> None:
        adapter = registry.get_latest("credit_bureau", cibil_v2_config)
        assert isinstance(adapter, CIBILAdapterV2)

    @pytest.mark.unit
    def test_discover_returns_all_metadata(self, registry: AdapterRegistry) -> None:
        results = registry.discover()
        kinds = {m.kind for m in results}
        assert {"credit_bureau", "kyc", "gst", "payment_gateway", "sms_gateway"}.issubset(kinds)

    @pytest.mark.unit
    def test_discover_filters_by_kind(self, registry: AdapterRegistry) -> None:
        results = registry.discover(kind="gst")
        assert all(m.kind == "gst" for m in results)
        assert len(results) >= 1

    @pytest.mark.unit
    def test_discover_filters_by_version(self, registry: AdapterRegistry) -> None:
        results = registry.discover(version="v1")
        assert all(m.version == "v1" for m in results)

    @pytest.mark.unit
    def test_duplicate_registration_raises(self) -> None:
        fresh = AdapterRegistry()
        fresh._register_class(CIBILAdapterV1)  # type: ignore[attr-defined]
        with pytest.raises(RuntimeError, match="Adapter conflict"):
            fresh._register_class(CIBILAdapterV1)  # type: ignore[attr-defined]

    @pytest.mark.unit
    def test_unregister_returns_true_when_found(self) -> None:
        fresh = AdapterRegistry()
        fresh._register_class(GSTAdapterV1)  # type: ignore[attr-defined]
        assert fresh.unregister("gst", "v1") is True
        assert not fresh.has("gst", "v1")

    @pytest.mark.unit
    def test_unregister_returns_false_when_not_found(self, registry: AdapterRegistry) -> None:
        assert registry.unregister("nonexistent", "v99") is False


# ---------------------------------------------------------------------------
# Config validation tests
# ---------------------------------------------------------------------------


class TestConfigValidation:
    @pytest.mark.unit
    def test_credit_bureau_config_valid(self, cibil_v1_config: dict[str, Any]) -> None:
        cfg = validate_config("credit_bureau", "v1", cibil_v1_config)
        assert isinstance(cfg, CreditBureauConfig)

    @pytest.mark.unit
    def test_credit_bureau_config_missing_api_key(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            validate_config("credit_bureau", "v1", {"member_id": "MBR001"})

    @pytest.mark.unit
    def test_credit_bureau_config_invalid_product_code(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            validate_config(
                "credit_bureau",
                "v1",
                {
                    "api_key": "key",
                    "member_id": "MBR001",
                    "product_code": "invalid code!",
                },
            )

    @pytest.mark.unit
    def test_kyc_config_client_id_no_spaces(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="must not contain spaces"):
            validate_config(
                "kyc",
                "v1",
                {
                    "client_id": "bad id with spaces",
                    "client_secret": "secret",
                },
            )

    @pytest.mark.unit
    def test_gst_config_invalid_state_code(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="state_code"):
            validate_config(
                "gst",
                "v1",
                {
                    "gstn_username": "user",
                    "gstn_password": "pass",
                    "app_key": "appkey",
                    "state_code": "99",
                },
            )

    @pytest.mark.unit
    def test_payment_gateway_config_invalid_currency(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            validate_config(
                "payment_gateway",
                "v1",
                {
                    "key_id": "rzp_test_00000000000001",
                    "key_secret": "secret",
                    "webhook_secret": "wsecret",
                    "currency": "inr",  # must be uppercase
                },
            )

    @pytest.mark.unit
    def test_sms_config_sender_id_too_long(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            validate_config(
                "sms_gateway",
                "v1",
                {
                    "api_key": "key",
                    "sender_id": "TOOLONGID1234",  # 13 chars, exceeds max_length=11
                    "dlt_entity_id": "1" * 19,
                    "dlt_template_id": "1" * 19,
                },
            )

    @pytest.mark.unit
    def test_get_config_class_raises_for_unknown(self) -> None:
        with pytest.raises(KeyError, match="No config class"):
            get_config_class("unknown", "v99")

    @pytest.mark.unit
    def test_adapter_config_immutable(self, cibil_v1_config: dict[str, Any]) -> None:
        from pydantic import ValidationError

        cfg = validate_config("credit_bureau", "v1", cibil_v1_config)
        with pytest.raises((ValidationError, TypeError)):
            cfg.timeout_seconds = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Adapter metadata tests
# ---------------------------------------------------------------------------


class TestAdapterMetadata:
    @pytest.mark.unit
    def test_cibil_v1_metadata(self) -> None:
        meta = CIBILAdapterV1.metadata
        assert meta.kind == "credit_bureau"
        assert meta.version == "v1"
        assert meta.provider == "TransUnion CIBIL"
        assert AuthType.API_KEY in meta.auth_types
        assert meta.rate_limit.requests_per_second == 2.0
        assert meta.rate_limit.daily_quota == 5000

    @pytest.mark.unit
    def test_cibil_v2_has_extra_fields(self) -> None:
        v1_names = {f.name for f in CIBILAdapterV1.metadata.supported_fields}
        v2_names = {f.name for f in CIBILAdapterV2.metadata.supported_fields}
        # V2 must be a strict superset of V1 fields
        assert v1_names.issubset(v2_names)
        assert "gstin" in v2_names
        assert "bureau_segment" in v2_names

    @pytest.mark.unit
    def test_kyc_v2_has_digilocker_fields(self) -> None:
        v2_names = {f.name for f in KYCAdapterV2.metadata.supported_fields}
        assert "digilocker_token" in v2_names
        assert "video_kyc_session_id" in v2_names

    @pytest.mark.unit
    def test_all_adapters_have_rate_limit(self) -> None:
        for cls in (
            CIBILAdapterV1,
            CIBILAdapterV2,
            KYCAdapterV1,
            KYCAdapterV2,
            GSTAdapterV1,
            PaymentGatewayAdapterV1,
            SMSGatewayAdapterV1,
        ):
            assert isinstance(cls.metadata.rate_limit, RateLimit)
            assert cls.metadata.rate_limit.requests_per_second > 0

    @pytest.mark.unit
    def test_all_adapters_have_response_codes(self) -> None:
        for cls in (
            CIBILAdapterV1,
            CIBILAdapterV2,
            KYCAdapterV1,
            KYCAdapterV2,
            GSTAdapterV1,
            PaymentGatewayAdapterV1,
            SMSGatewayAdapterV1,
        ):
            assert 200 in cls.metadata.response_codes


# ---------------------------------------------------------------------------
# Hook engine tests
# ---------------------------------------------------------------------------


class TestHookEngine:
    @pytest.mark.unit
    async def test_pre_request_hook_runs(self) -> None:
        engine = HookEngine()
        calls: list[str] = []

        async def my_hook(ctx: HookContext) -> None:
            calls.append("pre")

        engine.register(HookPhase.PRE_REQUEST, my_hook)
        ctx = HookContext("test", "v1", "op", {"key": "val"})
        await engine.run(HookPhase.PRE_REQUEST, ctx)
        assert calls == ["pre"]

    @pytest.mark.unit
    async def test_hooks_run_in_priority_order(self) -> None:
        engine = HookEngine()
        order: list[int] = []

        async def hook_30(ctx: HookContext) -> None:
            order.append(30)

        async def hook_10(ctx: HookContext) -> None:
            order.append(10)

        async def hook_20(ctx: HookContext) -> None:
            order.append(20)

        engine.register(HookPhase.PRE_REQUEST, hook_30, priority=30)
        engine.register(HookPhase.PRE_REQUEST, hook_10, priority=10)
        engine.register(HookPhase.PRE_REQUEST, hook_20, priority=20)

        ctx = HookContext("test", "v1", "op", {})
        await engine.run(HookPhase.PRE_REQUEST, ctx)
        assert order == [10, 20, 30]

    @pytest.mark.unit
    async def test_abort_stops_chain(self) -> None:
        engine = HookEngine()
        calls: list[str] = []

        async def hook_a(ctx: HookContext) -> None:
            calls.append("a")
            ctx.abort = True

        async def hook_b(ctx: HookContext) -> None:
            calls.append("b")

        engine.register(HookPhase.PRE_REQUEST, hook_a, priority=1)
        engine.register(HookPhase.PRE_REQUEST, hook_b, priority=2)

        ctx = HookContext("test", "v1", "op", {})
        await engine.run(HookPhase.PRE_REQUEST, ctx)
        assert calls == ["a"]

    @pytest.mark.unit
    async def test_on_error_hook_can_suppress_error(self) -> None:
        engine = HookEngine()

        async def suppress(ctx: HookContext) -> None:
            ctx.result = {"success": False, "suppressed": True}
            ctx.error = None

        engine.register(HookPhase.ON_ERROR, suppress)
        ctx = HookContext("test", "v1", "op", {})
        ctx.error = ValueError("boom")
        await engine.run(HookPhase.ON_ERROR, ctx)
        assert ctx.error is None
        assert ctx.result == {"success": False, "suppressed": True}

    @pytest.mark.unit
    async def test_hook_decorator_registers(self) -> None:
        engine = HookEngine()
        calls: list[str] = []

        @hook(HookPhase.POST_RESPONSE, engine, priority=5)
        async def decorated(ctx: HookContext) -> None:
            calls.append("decorated")

        ctx = HookContext("test", "v1", "op", {})
        await engine.run(HookPhase.POST_RESPONSE, ctx)
        assert "decorated" in calls

    @pytest.mark.unit
    def test_unregister_hook(self) -> None:
        engine = HookEngine()

        async def my_hook(ctx: HookContext) -> None:
            pass

        engine.register(HookPhase.PRE_REQUEST, my_hook)
        assert engine.unregister(HookPhase.PRE_REQUEST, my_hook) is True
        assert engine.unregister(HookPhase.PRE_REQUEST, my_hook) is False


# ---------------------------------------------------------------------------
# Built-in hook tests
# ---------------------------------------------------------------------------


class TestBuiltinHooks:
    @pytest.mark.unit
    async def test_correlation_id_hook_stamps_payload(self) -> None:
        from app.integrations.hooks.builtin import correlation_id_hook

        ctx = HookContext("gst", "v1", "op", {})
        await correlation_id_hook(ctx)
        assert "x_correlation_id" in ctx.payload
        assert re.match(r"^[0-9a-f-]{36}$", ctx.payload["x_correlation_id"])

    @pytest.mark.unit
    async def test_correlation_id_not_overwritten(self) -> None:
        from app.integrations.hooks.builtin import correlation_id_hook

        ctx = HookContext("gst", "v1", "op", {"x_correlation_id": "fixed-id"})
        await correlation_id_hook(ctx)
        assert ctx.payload["x_correlation_id"] == "fixed-id"

    @pytest.mark.unit
    async def test_pii_mask_redacts_pan(self) -> None:
        ctx = HookContext("kyc", "v1", "op", {"pan": "ABCDE1234F", "name": "Test"})
        await pii_mask_hook(ctx)
        assert "ABCDE1234F" not in str(ctx.payload)

    @pytest.mark.unit
    async def test_pii_mask_redacts_aadhaar(self) -> None:
        ctx = HookContext("kyc", "v1", "op", {"aadhaar": "2341 0000 0001"})
        await pii_mask_hook(ctx)
        assert "2341 0000 0001" not in str(ctx.payload)

    @pytest.mark.unit
    async def test_rate_limit_guard_raises_on_burst_exceeded(self) -> None:
        guard = RateLimitGuard(requests_per_second=1.0, burst_size=2)
        ctx = HookContext("test", "v1", "op", {})
        await guard(ctx)
        await guard(ctx)
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await guard(ctx)

    @pytest.mark.unit
    async def test_error_to_result_hook_suppresses_error(self) -> None:
        from app.integrations.hooks.builtin import error_to_result_hook

        ctx = HookContext("credit_bureau", "v1", "test_op", {})
        ctx.error = ValueError("network error")
        await error_to_result_hook(ctx)
        assert ctx.error is None
        assert ctx.result is not None
        assert ctx.result["success"] is False
        assert ctx.result["error_type"] == "ValueError"


# ---------------------------------------------------------------------------
# Concrete adapter sandbox tests
# ---------------------------------------------------------------------------


class TestCIBILAdapterV1:
    @pytest.mark.unit
    async def test_sandbox_execute_returns_score(self, cibil_v1_config: dict[str, Any]) -> None:
        adapter = CIBILAdapterV1(CreditBureauConfig.model_validate(cibil_v1_config))
        result = await adapter.execute(
            "fetch_credit_score",
            {
                "pan": "ABCDE1234F",
                "full_name": "Ravi Kumar",
                "dob": "1990-05-15",
            },
        )
        assert result["success"] is True
        score = result["data"]["credit_score"]
        assert 300 <= score <= 899

    @pytest.mark.unit
    async def test_sandbox_score_is_deterministic(self, cibil_v1_config: dict[str, Any]) -> None:
        adapter = CIBILAdapterV1(CreditBureauConfig.model_validate(cibil_v1_config))
        payload = {"pan": "PQRST5678U", "full_name": "Test User", "dob": "1985-01-01"}
        r1 = await adapter.execute("fetch_credit_score", payload)
        r2 = await adapter.execute("fetch_credit_score", payload)
        assert r1["data"]["credit_score"] == r2["data"]["credit_score"]

    @pytest.mark.unit
    def test_validate_missing_pan(self, cibil_v1_config: dict[str, Any]) -> None:
        adapter = CIBILAdapterV1(CreditBureauConfig.model_validate(cibil_v1_config))
        errors = adapter.validate({"full_name": "Test", "dob": "1990-01-01"})
        assert any("pan" in e for e in errors)

    @pytest.mark.unit
    def test_validate_invalid_pan_pattern(self, cibil_v1_config: dict[str, Any]) -> None:
        adapter = CIBILAdapterV1(CreditBureauConfig.model_validate(cibil_v1_config))
        errors = adapter.validate({"pan": "invalid", "full_name": "Test", "dob": "1990-01-01"})
        assert any("pan" in e for e in errors)

    @pytest.mark.unit
    def test_validate_invalid_mobile(self, cibil_v1_config: dict[str, Any]) -> None:
        adapter = CIBILAdapterV1(CreditBureauConfig.model_validate(cibil_v1_config))
        errors = adapter.validate(
            {
                "pan": "ABCDE1234F",
                "full_name": "Test",
                "dob": "1990-01-01",
                "mobile": "1234567890",  # starts with 1, invalid
            }
        )
        assert any("mobile" in e for e in errors)

    @pytest.mark.unit
    async def test_execute_raises_on_validation_failure(
        self, cibil_v1_config: dict[str, Any]
    ) -> None:
        adapter = CIBILAdapterV1(CreditBureauConfig.model_validate(cibil_v1_config))
        with pytest.raises(ValueError, match="Payload validation failed"):
            await adapter.execute("fetch_credit_score", {"pan": "bad"})

    @pytest.mark.unit
    def test_adapter_id(self, cibil_v1_config: dict[str, Any]) -> None:
        adapter = CIBILAdapterV1(CreditBureauConfig.model_validate(cibil_v1_config))
        assert adapter.adapter_id == "credit_bureau:v1"

    @pytest.mark.unit
    def test_wrong_config_type_raises(self) -> None:
        cfg = KYCConfig.model_validate(
            {
                "client_id": "kyc-client-001",
                "client_secret": "secret",
                "sandbox_mode": True,
            }
        )
        with pytest.raises(TypeError, match="expects config of type"):
            CIBILAdapterV1(cfg)


class TestCIBILAdapterV2:
    @pytest.mark.unit
    async def test_sandbox_execute_returns_consumer_and_commercial(
        self, cibil_v2_config: dict[str, Any]
    ) -> None:
        adapter = CIBILAdapterV2(CreditBureauConfig.model_validate(cibil_v2_config))
        result = await adapter.execute(
            "fetch_bureau_report",
            {
                "pan": "ABCDE1234F",
                "full_name": "Ravi Kumar",
                "dob": "1990-05-15",
            },
        )
        assert result["success"] is True
        assert "consumer" in result["data"]
        assert "commercial" in result["data"]

    @pytest.mark.unit
    def test_validate_invalid_gstin(self, cibil_v2_config: dict[str, Any]) -> None:
        adapter = CIBILAdapterV2(CreditBureauConfig.model_validate(cibil_v2_config))
        errors = adapter.validate(
            {
                "pan": "ABCDE1234F",
                "full_name": "Test",
                "dob": "1990-01-01",
                "gstin": "INVALID_GSTIN",
            }
        )
        assert any("gstin" in e for e in errors)


class TestKYCAdapterV1:
    @pytest.mark.unit
    async def test_sandbox_aadhaar_otp(self, kyc_v1_config: dict[str, Any]) -> None:
        adapter = KYCAdapterV1(KYCConfig.model_validate(kyc_v1_config))
        result = await adapter.execute(
            "verify_aadhaar",
            {
                "kyc_type": "aadhaar_otp",
                "aadhaar_number": "234100000001",
                "mobile": "9876543210",
                "otp": "123456",
                "consent": True,
            },
        )
        assert result["success"] is True
        assert result["data"]["kyc_status"] == "success"

    @pytest.mark.unit
    async def test_sandbox_pan_verify(self, kyc_v1_config: dict[str, Any]) -> None:
        adapter = KYCAdapterV1(KYCConfig.model_validate(kyc_v1_config))
        result = await adapter.execute(
            "verify_pan",
            {
                "kyc_type": "pan_verify",
                "pan": "ABCDE1234F",
                "mobile": "9876543210",
                "consent": True,
            },
        )
        assert result["success"] is True

    @pytest.mark.unit
    def test_validate_missing_consent(self, kyc_v1_config: dict[str, Any]) -> None:
        adapter = KYCAdapterV1(KYCConfig.model_validate(kyc_v1_config))
        errors = adapter.validate(
            {
                "kyc_type": "pan_verify",
                "pan": "ABCDE1234F",
                "mobile": "9876543210",
                "consent": False,  # must be True
            }
        )
        assert any("consent" in e for e in errors)

    @pytest.mark.unit
    def test_validate_face_match_requires_image(self, kyc_v1_config: dict[str, Any]) -> None:
        adapter = KYCAdapterV1(KYCConfig.model_validate(kyc_v1_config))
        errors = adapter.validate(
            {
                "kyc_type": "face_match",
                "mobile": "9876543210",
                "consent": True,
            }
        )
        assert any("face_image_b64" in e for e in errors)


class TestKYCAdapterV2:
    @pytest.mark.unit
    async def test_sandbox_digilocker_pull(self, kyc_v2_config: dict[str, Any]) -> None:
        adapter = KYCAdapterV2(KYCConfigV2.model_validate(kyc_v2_config))
        result = await adapter.execute(
            "digilocker_pull",
            {
                "kyc_type": "digilocker_pull",
                "mobile": "9876543210",
                "consent": True,
                "digilocker_token": "tok_abc123",
                "document_type": "driving_license",
            },
        )
        assert result["success"] is True
        assert result["data"]["document_type"] == "driving_license"

    @pytest.mark.unit
    async def test_sandbox_video_kyc_session(self, kyc_v2_config: dict[str, Any]) -> None:
        adapter = KYCAdapterV2(KYCConfigV2.model_validate(kyc_v2_config))
        result = await adapter.execute(
            "video_kyc",
            {
                "kyc_type": "video_kyc",
                "mobile": "9876543210",
                "consent": True,
            },
        )
        assert result["data"]["video_kyc_session_url"] is not None


class TestGSTAdapterV1:
    @pytest.mark.unit
    async def test_sandbox_gstin_verify(self, gst_config: dict[str, Any]) -> None:
        adapter = GSTAdapterV1(GSTConfig.model_validate(gst_config))
        result = await adapter.execute(
            "gstin_verify",
            {
                "gstin": "27ABCDE1234F1Z5",
                "operation": "gstin_verify",
            },
        )
        assert result["success"] is True
        assert result["data"]["status"] == "Active"

    @pytest.mark.unit
    async def test_sandbox_returns_summary(self, gst_config: dict[str, Any]) -> None:
        adapter = GSTAdapterV1(GSTConfig.model_validate(gst_config))
        result = await adapter.execute(
            "returns_summary",
            {
                "gstin": "27ABCDE1234F1Z5",
                "operation": "returns_summary",
                "financial_year": "2024-25",
                "return_type": "GSTR3B",
            },
        )
        assert result["success"] is True
        assert "filings" in result["data"]

    @pytest.mark.unit
    async def test_sandbox_ledger_summary(self, gst_config: dict[str, Any]) -> None:
        adapter = GSTAdapterV1(GSTConfig.model_validate(gst_config))
        result = await adapter.execute(
            "ledger_summary",
            {
                "gstin": "27ABCDE1234F1Z5",
                "operation": "ledger_summary",
                "ledger_type": "CREDIT",
            },
        )
        assert result["success"] is True
        assert "igst_balance" in result["data"]

    @pytest.mark.unit
    def test_validate_missing_financial_year(self, gst_config: dict[str, Any]) -> None:
        adapter = GSTAdapterV1(GSTConfig.model_validate(gst_config))
        errors = adapter.validate(
            {
                "gstin": "27ABCDE1234F1Z5",
                "operation": "returns_summary",
                "return_type": "GSTR3B",
            }
        )
        assert any("financial_year" in e for e in errors)

    @pytest.mark.unit
    def test_validate_invalid_gstin(self, gst_config: dict[str, Any]) -> None:
        adapter = GSTAdapterV1(GSTConfig.model_validate(gst_config))
        errors = adapter.validate({"gstin": "INVALID", "operation": "gstin_verify"})
        assert any("gstin" in e for e in errors)


class TestPaymentGatewayAdapterV1:
    @pytest.mark.unit
    async def test_sandbox_create_order(self, pg_config: dict[str, Any]) -> None:
        adapter = PaymentGatewayAdapterV1(PaymentGatewayConfig.model_validate(pg_config))
        result = await adapter.execute(
            "create_order",
            {
                "operation": "create_order",
                "amount_paise": 100000,
                "receipt": "LOAN-EMI-001",
            },
        )
        assert result["success"] is True
        assert result["data"]["order_id"] == "order_SBXTestOrder0001"
        assert result["data"]["amount_inr"] == 1000.0

    @pytest.mark.unit
    async def test_sandbox_capture_payment(self, pg_config: dict[str, Any]) -> None:
        adapter = PaymentGatewayAdapterV1(PaymentGatewayConfig.model_validate(pg_config))
        result = await adapter.execute(
            "capture_payment",
            {
                "operation": "capture_payment",
                "payment_id": "pay_TestPay0000001",  # exactly 14 chars after pay_
            },
        )
        assert result["success"] is True
        assert result["data"]["status"] == "captured"

    @pytest.mark.unit
    async def test_sandbox_refund(self, pg_config: dict[str, Any]) -> None:
        adapter = PaymentGatewayAdapterV1(PaymentGatewayConfig.model_validate(pg_config))
        result = await adapter.execute(
            "refund",
            {
                "operation": "refund_payment",
                "payment_id": "pay_TestPay0000001",  # exactly 14 chars after pay_
                "refund_amount_paise": 50000,
            },
        )
        assert result["success"] is True
        assert result["data"]["status"] == "processed"

    @pytest.mark.unit
    async def test_sandbox_verify_signature(self, pg_config: dict[str, Any]) -> None:
        adapter = PaymentGatewayAdapterV1(PaymentGatewayConfig.model_validate(pg_config))
        result = await adapter.execute(
            "verify",
            {
                "operation": "verify_signature",
                "order_id": "order_SBXTestOrder0001",
                "payment_id": "pay_SBXTestPay00001",
                "razorpay_signature": "dummy_signature",
            },
        )
        assert result["success"] is True

    @pytest.mark.unit
    def test_validate_missing_amount_for_create_order(self, pg_config: dict[str, Any]) -> None:
        adapter = PaymentGatewayAdapterV1(PaymentGatewayConfig.model_validate(pg_config))
        errors = adapter.validate({"operation": "create_order"})
        assert any("amount_paise" in e for e in errors)

    @pytest.mark.unit
    def test_validate_invalid_payment_id_format(self, pg_config: dict[str, Any]) -> None:
        adapter = PaymentGatewayAdapterV1(PaymentGatewayConfig.model_validate(pg_config))
        errors = adapter.validate(
            {
                "operation": "capture_payment",
                "payment_id": "invalid_id",
            }
        )
        assert any("payment_id" in e for e in errors)


class TestSMSGatewayAdapterV1:
    @pytest.mark.unit
    async def test_sandbox_send_otp(self, sms_config: dict[str, Any]) -> None:
        adapter = SMSGatewayAdapterV1(SMSGatewayConfig.model_validate(sms_config))
        result = await adapter.execute(
            "send_otp",
            {
                "operation": "send_otp",
                "mobile": "9876543210",
                "otp": "482913",
            },
        )
        assert result["success"] is True
        assert result["data"]["status"] == "ACCEPTED"

    @pytest.mark.unit
    async def test_sandbox_send_transactional(self, sms_config: dict[str, Any]) -> None:
        adapter = SMSGatewayAdapterV1(SMSGatewayConfig.model_validate(sms_config))
        result = await adapter.execute(
            "send_trans",
            {
                "operation": "send_transactional",
                "mobile": "9876543210",
                "message": "Dear Customer, your loan of Rs.50000 has been disbursed. -FinSpark",
            },
        )
        assert result["success"] is True

    @pytest.mark.unit
    async def test_sandbox_check_delivery(self, sms_config: dict[str, Any]) -> None:
        adapter = SMSGatewayAdapterV1(SMSGatewayConfig.model_validate(sms_config))
        result = await adapter.execute(
            "check_delivery",
            {
                "operation": "check_delivery",
                "message_id": "MSGSBX0001234",
            },
        )
        assert result["success"] is True
        assert result["data"]["delivery_status"] == "DELIVERED"

    @pytest.mark.unit
    def test_validate_invalid_mobile(self, sms_config: dict[str, Any]) -> None:
        adapter = SMSGatewayAdapterV1(SMSGatewayConfig.model_validate(sms_config))
        errors = adapter.validate(
            {
                "operation": "send_otp",
                "mobile": "1234567890",  # starts with 1
            }
        )
        assert any("mobile" in e for e in errors)

    @pytest.mark.unit
    def test_validate_message_required_for_transactional(self, sms_config: dict[str, Any]) -> None:
        adapter = SMSGatewayAdapterV1(SMSGatewayConfig.model_validate(sms_config))
        errors = adapter.validate(
            {
                "operation": "send_transactional",
                "mobile": "9876543210",
            }
        )
        assert any("message" in e for e in errors)


# ---------------------------------------------------------------------------
# End-to-end registry instantiation test
# ---------------------------------------------------------------------------


class TestEndToEnd:
    @pytest.mark.unit
    async def test_registry_get_and_execute_credit_bureau(self) -> None:
        registry = get_registry()
        adapter = registry.get(
            "credit_bureau",
            "v1",
            {
                "api_key": "e2e-test-key",
                "member_id": "MBR99999",
                "sandbox_mode": True,
            },
        )
        result = await adapter.execute(
            "fetch_score",
            {
                "pan": "ZZZZZ9999Z",
                "full_name": "E2E Test User",
                "dob": "1988-12-25",
            },
        )
        assert result["success"] is True
        assert 300 <= result["data"]["credit_score"] <= 899

    @pytest.mark.unit
    async def test_registry_get_latest_kyc_and_execute(self) -> None:
        registry = get_registry()
        adapter = registry.get_latest(
            "kyc",
            {
                "client_id": "e2e-kyc-client",
                "client_secret": "e2e-secret",
                "sandbox_mode": True,
            },
        )
        # Should be V2
        assert adapter.metadata.version == "v2"
        result = await adapter.execute(
            "aadhaar_otp",
            {
                "kyc_type": "aadhaar_otp",
                "aadhaar_number": "234100000001",
                "mobile": "9000000001",
                "consent": True,
            },
        )
        assert result["success"] is True
