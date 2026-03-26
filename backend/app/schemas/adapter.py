"""
Integration adapter definition schemas.
An Adapter represents a versioned, reusable connector to an external service
(credit bureau, KYC provider, payment gateway, etc.).
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator

from .common import (
    NonEmptyStr,
    OrchestratorBase,
    ResourceId,
    SemVer,
    SlugStr,
    TenantId,
    TimestampedMixin,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AdapterCategory(StrEnum):
    CREDIT_BUREAU = "credit_bureau"
    KYC = "kyc"
    GST = "gst"
    FRAUD_ENGINE = "fraud_engine"
    PAYMENT_GATEWAY = "payment_gateway"
    OPEN_BANKING = "open_banking"
    COMMUNICATION = "communication"
    DOCUMENT_VERIFICATION = "document_verification"
    COLLECTIONS = "collections"
    CUSTOM = "custom"


class AuthSchemeType(StrEnum):
    API_KEY = "api_key"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"
    OAUTH2_AUTHORIZATION_CODE = "oauth2_authorization_code"
    BASIC = "basic"
    BEARER = "bearer"
    MTLS = "mtls"
    HMAC_SHA256 = "hmac_sha256"
    NONE = "none"


class AdapterStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class EndpointRole(StrEnum):
    HEALTH_CHECK = "health_check"
    AUTHENTICATE = "authenticate"
    QUERY = "query"
    SUBMIT = "submit"
    CALLBACK = "callback"
    WEBHOOK_REGISTER = "webhook_register"
    WEBHOOK_DEREGISTER = "webhook_deregister"
    CUSTOM = "custom"


class RateLimitStrategy(StrEnum):
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"


# ---------------------------------------------------------------------------
# Auth scheme — discriminated union on `type`
# ---------------------------------------------------------------------------

class ApiKeyAuth(OrchestratorBase):
    type: Literal[AuthSchemeType.API_KEY] = AuthSchemeType.API_KEY
    header_name: str = "X-API-Key"
    query_param_name: str | None = None  # alternative: pass via query string
    prefix: str | None = None  # e.g. "Bearer " — left blank if not required


class OAuth2ClientCredentials(OrchestratorBase):
    type: Literal[AuthSchemeType.OAUTH2_CLIENT_CREDENTIALS] = (
        AuthSchemeType.OAUTH2_CLIENT_CREDENTIALS
    )
    token_url: HttpUrl
    scopes: list[str] = Field(default_factory=list)
    token_expiry_buffer_seconds: int = Field(default=60, ge=0)
    audience: str | None = None


class OAuth2AuthorizationCode(OrchestratorBase):
    type: Literal[AuthSchemeType.OAUTH2_AUTHORIZATION_CODE] = (
        AuthSchemeType.OAUTH2_AUTHORIZATION_CODE
    )
    auth_url: HttpUrl
    token_url: HttpUrl
    scopes: list[str] = Field(default_factory=list)
    redirect_uri: HttpUrl | None = None


class BasicAuth(OrchestratorBase):
    type: Literal[AuthSchemeType.BASIC] = AuthSchemeType.BASIC


class BearerAuth(OrchestratorBase):
    type: Literal[AuthSchemeType.BEARER] = AuthSchemeType.BEARER
    header_name: str = "Authorization"
    prefix: str = "Bearer"


class MtlsAuth(OrchestratorBase):
    type: Literal[AuthSchemeType.MTLS] = AuthSchemeType.MTLS
    cert_vault_key: str  # path in vault where cert + key are stored
    ca_bundle_vault_key: str | None = None


class HmacAuth(OrchestratorBase):
    type: Literal[AuthSchemeType.HMAC_SHA256] = AuthSchemeType.HMAC_SHA256
    signature_header: str = "X-Signature"
    timestamp_header: str = "X-Timestamp"
    signed_headers: list[str] = Field(default_factory=lambda: ["date", "content-type"])


class NoAuth(OrchestratorBase):
    type: Literal[AuthSchemeType.NONE] = AuthSchemeType.NONE


AuthScheme = Annotated[
    ApiKeyAuth
    | OAuth2ClientCredentials
    | OAuth2AuthorizationCode
    | BasicAuth
    | BearerAuth
    | MtlsAuth
    | HmacAuth
    | NoAuth,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class RateLimitConfig(OrchestratorBase):
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    requests_per_window: int = Field(..., ge=1)
    window_seconds: int = Field(..., ge=1)
    burst_allowance: int = Field(default=0, ge=0)
    retry_after_header: str = "Retry-After"


# ---------------------------------------------------------------------------
# Endpoint definition
# ---------------------------------------------------------------------------

class EndpointParam(OrchestratorBase):
    name: NonEmptyStr
    location: Literal["path", "query", "header", "body"] = "query"
    required: bool = True
    data_type: str = "string"
    description: str | None = None
    example: Any | None = None


class AdapterEndpoint(OrchestratorBase):
    endpoint_id: str = Field(default_factory=lambda: str(__import__("uuid").uuid4()))
    role: EndpointRole = EndpointRole.CUSTOM
    method: str = Field(..., pattern=r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$")
    path: NonEmptyStr  # relative to adapter base_url, e.g. "/v2/score"
    summary: str | None = None
    description: str | None = None
    params: list[EndpointParam] = Field(default_factory=list)
    request_schema: dict[str, Any] | None = None   # JSON Schema object
    response_schema: dict[str, Any] | None = None  # JSON Schema object
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    idempotent: bool = False
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Adapter version
# ---------------------------------------------------------------------------

class AdapterVersionCreate(OrchestratorBase):
    version: SemVer
    base_url: HttpUrl
    auth_scheme: AuthScheme
    endpoints: list[AdapterEndpoint] = Field(..., min_length=1)
    rate_limit: RateLimitConfig | None = None
    request_headers: dict[str, str] = Field(default_factory=dict)
    tls_verify: bool = True
    changelog: str | None = Field(default=None, max_length=5000)
    breaking_changes: list[str] = Field(default_factory=list)
    deprecated_at: str | None = None  # ISO-8601 date string

    @field_validator("request_headers")
    @classmethod
    def no_auth_headers_in_static(cls, v: dict[str, str]) -> dict[str, str]:
        forbidden = {"authorization", "x-api-key"}
        bad = {k for k in v if k.lower() in forbidden}
        if bad:
            raise ValueError(
                f"Auth credentials must not appear in static headers: {bad}. "
                "Use the auth_scheme field instead."
            )
        return v


class AdapterVersionRead(TimestampedMixin):
    id: ResourceId
    adapter_id: ResourceId
    version: SemVer
    base_url: str  # cast from HttpUrl for serialisation
    auth_scheme: AuthScheme
    endpoints: list[AdapterEndpoint]
    rate_limit: RateLimitConfig | None
    request_headers: dict[str, str]
    tls_verify: bool
    changelog: str | None
    breaking_changes: list[str]
    deprecated_at: str | None
    status: AdapterStatus


# ---------------------------------------------------------------------------
# Adapter (catalog entry)
# ---------------------------------------------------------------------------

class AdapterCreate(OrchestratorBase):
    slug: SlugStr
    name: NonEmptyStr = Field(..., max_length=120)
    category: AdapterCategory
    description: str | None = Field(default=None, max_length=2000)
    provider_url: HttpUrl | None = None
    logo_url: HttpUrl | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    is_public: bool = True  # False = tenant-private custom adapter
    owner_tenant_id: TenantId | None = None  # set for private adapters

    @model_validator(mode="after")
    def private_adapter_requires_tenant(self) -> "AdapterCreate":
        if not self.is_public and self.owner_tenant_id is None:
            raise ValueError("Private adapters must specify owner_tenant_id.")
        return self


class AdapterUpdate(OrchestratorBase):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    provider_url: HttpUrl | None = None
    logo_url: HttpUrl | None = None
    tags: list[str] | None = None
    status: AdapterStatus | None = None


class AdapterRead(TimestampedMixin):
    id: ResourceId
    slug: SlugStr
    name: NonEmptyStr
    category: AdapterCategory
    description: str | None
    provider_url: str | None
    logo_url: str | None
    tags: list[str]
    is_public: bool
    owner_tenant_id: TenantId | None
    status: AdapterStatus
    versions: list[AdapterVersionRead] = Field(default_factory=list)
    latest_version: SemVer | None = None


class AdapterListItem(OrchestratorBase):
    id: ResourceId
    slug: SlugStr
    name: NonEmptyStr
    category: AdapterCategory
    status: AdapterStatus
    latest_version: SemVer | None
    is_public: bool
