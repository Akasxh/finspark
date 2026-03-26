"""
Shared enums and type aliases for the integration layer.

This module is the canonical source of truth for adapter taxonomy inside the
finspark package.  The legacy app/integrations/types.py in the backend/app
tree duplicates these — consolidate there once that package is fully migrated.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class AdapterKind(str, Enum):
    CREDIT_BUREAU = "credit_bureau"
    KYC = "kyc"
    GST = "gst"
    PAYMENT_GATEWAY = "payment_gateway"
    SMS_GATEWAY = "sms_gateway"
    BANKING = "banking"
    INSURANCE = "insurance"


class AuthType(str, Enum):
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    MUTUAL_TLS = "mutual_tls"
    HMAC = "hmac"
    NONE = "none"


class AdapterVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"


# Lightweight containers — no ORM coupling
AdapterPayload = dict[str, Any]
AdapterResult = dict[str, Any]
