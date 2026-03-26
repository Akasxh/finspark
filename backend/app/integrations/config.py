"""
Per-adapter configuration validated through pydantic v2 models.

Each concrete adapter declares a config class that subclasses AdapterConfig.
The registry calls .model_validate() before instantiating an adapter, so
misconfigured adapters are rejected at startup — not at request time.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class AdapterConfig(BaseModel):
    """
    Root config shared by all adapters.

    Subclasses add adapter-specific fields.  The model is immutable after
    construction (model_config frozen=True) to prevent accidental mutation
    inside hook closures.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30.0
    max_retries: Annotated[int, Field(ge=0, le=10)] = 3
    retry_backoff_factor: Annotated[float, Field(ge=0.0, le=10.0)] = 0.5
    sandbox_mode: bool = False
    log_requests: bool = True


# ---------------------------------------------------------------------------
# Credit Bureau (CIBIL-like)
# ---------------------------------------------------------------------------

class CreditBureauConfig(AdapterConfig):
    api_key: SecretStr
    member_id: str = Field(min_length=6, max_length=20)
    product_code: str = Field(default="CIBILTUSC3", pattern=r"^[A-Z0-9]{5,20}$")
    base_url: str = Field(default="https://api.cibil.com/v1")
    sandbox_base_url: str = Field(default="https://sandbox.cibil.com/v1")
    include_account_summary: bool = True
    include_enquiry_summary: bool = True


# ---------------------------------------------------------------------------
# KYC Provider (Aadhaar / PAN / DigiLocker)
# ---------------------------------------------------------------------------

class KYCConfig(AdapterConfig):
    client_id: str = Field(min_length=8)
    client_secret: SecretStr
    base_url: str = Field(default="https://api.kyc-provider.in/v2")
    aadhaar_otp_url: str = Field(default="https://api.kyc-provider.in/v2/aadhaar/otp")
    pan_verify_url: str = Field(default="https://api.kyc-provider.in/v2/pan/verify")
    face_match_enabled: bool = False
    liveness_check_enabled: bool = False

    @field_validator("client_id")
    @classmethod
    def client_id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("client_id must not contain spaces")
        return v


class KYCConfigV2(KYCConfig):
    """V2 adds DigiLocker and video KYC endpoints."""

    digilocker_url: str = Field(default="https://api.kyc-provider.in/v2/digilocker")
    video_kyc_url: str = Field(default="https://api.kyc-provider.in/v2/video-kyc")
    video_kyc_enabled: bool = False
    consent_artefact_ttl_seconds: int = Field(default=600, ge=60, le=3600)


# ---------------------------------------------------------------------------
# GST Service
# ---------------------------------------------------------------------------

class GSTConfig(AdapterConfig):
    gstn_username: str = Field(min_length=3)
    gstn_password: SecretStr
    app_key: SecretStr                          # AES-256 session key seed
    base_url: str = Field(default="https://api.gst.gov.in/commonapi/v1.1")
    state_code: str = Field(default="27", pattern=r"^\d{2}$")   # Maharashtra default

    @field_validator("state_code")
    @classmethod
    def valid_state_code(cls, v: str) -> str:
        valid = {str(i).zfill(2) for i in range(1, 38)}
        if v not in valid:
            raise ValueError(f"state_code {v!r} is not a valid GST state code")
        return v


# ---------------------------------------------------------------------------
# Payment Gateway (Razorpay / CCAvenue style)
# ---------------------------------------------------------------------------

class PaymentGatewayConfig(AdapterConfig):
    key_id: str = Field(min_length=14)
    key_secret: SecretStr
    webhook_secret: SecretStr
    base_url: str = Field(default="https://api.razorpay.com/v1")
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    capture_mode: str = Field(default="automatic", pattern=r"^(automatic|manual)$")
    payment_expiry_seconds: int = Field(default=900, ge=300, le=86400)

    @model_validator(mode="after")
    def warn_on_long_expiry(self) -> "PaymentGatewayConfig":
        if self.payment_expiry_seconds > 3600:
            # Not a hard error — just a guardrail note embedded in the object
            object.__setattr__(self, "_long_expiry_warning", True)
        return self


# ---------------------------------------------------------------------------
# SMS Gateway (Twilio / Kaleyra / ValueFirst)
# ---------------------------------------------------------------------------

class SMSGatewayConfig(AdapterConfig):
    api_key: SecretStr
    sender_id: str = Field(min_length=4, max_length=11)     # DLT registered sender
    base_url: str = Field(default="https://api.kaleyra.io/v1")
    dlt_entity_id: str = Field(min_length=19, max_length=19)   # TRAI DLT entity ID
    dlt_template_id: str = Field(min_length=19, max_length=19)
    unicode_support: bool = True
    flash_sms: bool = False


# ---------------------------------------------------------------------------
# Config type map — used by registry for look-up
# ---------------------------------------------------------------------------

CONFIG_CLASS_MAP: dict[str, type[AdapterConfig]] = {
    "credit_bureau:v1": CreditBureauConfig,
    "credit_bureau:v2": CreditBureauConfig,
    "kyc:v1": KYCConfig,
    "kyc:v2": KYCConfigV2,
    "gst:v1": GSTConfig,
    "payment_gateway:v1": PaymentGatewayConfig,
    "sms_gateway:v1": SMSGatewayConfig,
}


def get_config_class(kind: str, version: str) -> type[AdapterConfig]:
    key = f"{kind}:{version}"
    cls = CONFIG_CLASS_MAP.get(key)
    if cls is None:
        raise KeyError(f"No config class registered for {key!r}. Known keys: {list(CONFIG_CLASS_MAP)}")
    return cls


def validate_config(kind: str, version: str, raw: dict[str, Any]) -> AdapterConfig:
    """Resolve the config class and run pydantic validation in one call."""
    cls = get_config_class(kind, version)
    return cls.model_validate(raw)
