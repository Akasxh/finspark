"""
Shared enums, type aliases, and lightweight data containers used across the
integration layer.  No adapter-specific logic lives here.
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


class AuthType(str, Enum):
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    MUTUAL_TLS = "mutual_tls"
    HMAC = "hmac"


class AdapterVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"


# Lightweight containers — no ORM coupling, no DB imports
AdapterPayload = dict[str, Any]
AdapterResult = dict[str, Any]
