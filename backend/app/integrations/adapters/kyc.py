"""
KYC Provider adapters — Aadhaar OTP, PAN verification, face-match.

V1: Aadhaar OTP-based eKYC + PAN verification
    Auth: client_id / client_secret (HMAC signed requests)

V2: Adds DigiLocker XML pull + video KYC initiation
    Auth: same scheme + consent artefact token
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from typing import Any

import httpx

from app.integrations.base import BaseAdapter
from app.integrations.config import KYCConfig, KYCConfigV2
from app.integrations.metadata import AdapterMetadata, FieldSchema, RateLimit
from app.integrations.types import AdapterPayload, AdapterResult, AuthType


_KYC_V1_FIELDS = (
    FieldSchema(
        name="aadhaar_number",
        dtype="str",
        required=False,
        description="12-digit Aadhaar number",
        example="234100000001",
        pattern=r"^\d{12}$",
        max_length=12,
    ),
    FieldSchema(
        name="pan",
        dtype="str",
        required=False,
        description="10-char PAN number",
        example="ABCDE1234F",
        pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$",
        max_length=10,
    ),
    FieldSchema(
        name="mobile",
        dtype="str",
        required=True,
        description="Aadhaar-linked 10-digit mobile",
        example="9876543210",
        pattern=r"^[6-9]\d{9}$",
        max_length=10,
    ),
    FieldSchema(
        name="otp",
        dtype="str",
        required=False,
        description="6-digit OTP received on mobile (required for eKYC verification step)",
        example="482913",
        pattern=r"^\d{6}$",
        max_length=6,
    ),
    FieldSchema(
        name="consent",
        dtype="bool",
        required=True,
        description="Explicit consent flag (must be True)",
        example=True,
    ),
    FieldSchema(
        name="kyc_type",
        dtype="enum",
        required=True,
        description="Type of KYC verification to perform",
        example="aadhaar_otp",
        enum_values=("aadhaar_otp", "pan_verify", "face_match"),
    ),
    FieldSchema(
        name="face_image_b64",
        dtype="str",
        required=False,
        description="Base64-encoded JPEG selfie (required when kyc_type=face_match)",
    ),
)

_KYC_V2_EXTRA_FIELDS = (
    FieldSchema(
        name="digilocker_token",
        dtype="str",
        required=False,
        description="DigiLocker OAuth access token for XML document pull",
    ),
    FieldSchema(
        name="document_type",
        dtype="enum",
        required=False,
        description="Document type to pull from DigiLocker",
        example="driving_license",
        enum_values=("aadhaar_xml", "driving_license", "voter_id", "passport"),
    ),
    FieldSchema(
        name="video_kyc_session_id",
        dtype="str",
        required=False,
        description="Pre-created video KYC session ID",
    ),
)


# ---------------------------------------------------------------------------
# HMAC request signing helper
# ---------------------------------------------------------------------------

def _hmac_signature(secret: str, body: str, timestamp: str) -> str:
    message = f"{timestamp}:{body}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# V1
# ---------------------------------------------------------------------------

class KYCAdapterV1(BaseAdapter):
    """Aadhaar OTP eKYC + PAN verification (V1)."""

    metadata = AdapterMetadata(
        kind="kyc",
        version="v1",
        display_name="KYC Provider — Aadhaar OTP + PAN (V1)",
        provider="AadhaarBridge",
        supported_fields=_KYC_V1_FIELDS,
        auth_types=(AuthType.HMAC,),
        rate_limit=RateLimit(requests_per_second=5.0, daily_quota=10000, burst_size=10),
        endpoint_template="https://api.kyc-provider.in/v1/{kyc_type}",
        sandbox_url="https://sandbox.kyc-provider.in/v1/{kyc_type}",
        response_codes={
            200: "Verification successful",
            400: "Invalid request parameters",
            401: "Authentication failed",
            403: "Consent not provided",
            404: "Aadhaar/PAN not found",
            410: "OTP expired",
            422: "Face match failed",
            429: "Rate limit exceeded",
        },
        tags=("kyc", "aadhaar", "pan", "face_match"),
    )

    Config = KYCConfig
    auto_register = True

    async def connect(self) -> None:
        cfg: KYCConfig = self.config  # type: ignore[assignment]
        if cfg.sandbox_mode:
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            ts = str(int(time.time()))
            sig = _hmac_signature(cfg.client_secret.get_secret_value(), "", ts)
            resp = await client.get(
                f"{cfg.base_url}/health",
                headers={
                    "X-Client-Id": cfg.client_id,
                    "X-Timestamp": ts,
                    "X-Signature": sig,
                },
            )
            if resp.status_code not in (200, 204):
                raise ConnectionError(f"KYC provider health check failed: {resp.status_code}")

    def validate(self, payload: AdapterPayload) -> list[str]:
        errors: list[str] = []

        kyc_type = payload.get("kyc_type")
        if not kyc_type:
            errors.append("kyc_type is required")
        elif kyc_type not in ("aadhaar_otp", "pan_verify", "face_match"):
            errors.append(f"kyc_type {kyc_type!r} is invalid")

        if not payload.get("consent"):
            errors.append("consent must be True")

        mobile = payload.get("mobile")
        if not mobile:
            errors.append("mobile is required")
        elif not re.match(r"^[6-9]\d{9}$", str(mobile)):
            errors.append(f"mobile {mobile!r} is not a valid Indian mobile number")

        if kyc_type == "aadhaar_otp":
            aadhaar = payload.get("aadhaar_number")
            if not aadhaar:
                errors.append("aadhaar_number is required for kyc_type=aadhaar_otp")
            elif not re.match(r"^\d{12}$", str(aadhaar)):
                errors.append("aadhaar_number must be 12 digits")

        if kyc_type == "pan_verify":
            pan = payload.get("pan")
            if not pan:
                errors.append("pan is required for kyc_type=pan_verify")
            elif not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", str(pan)):
                errors.append(f"pan {pan!r} is invalid")

        if kyc_type == "face_match" and not payload.get("face_image_b64"):
            errors.append("face_image_b64 is required for kyc_type=face_match")

        return errors

    def transform(self, raw_response: dict[str, Any]) -> AdapterResult:
        return {
            "success": raw_response.get("status") == "success",
            "adapter": self.adapter_id,
            "data": {
                "kyc_status": raw_response.get("status"),
                "name": raw_response.get("name"),
                "dob": raw_response.get("dob"),
                "gender": raw_response.get("gender"),
                "address": raw_response.get("address", {}),
                "photo_b64": raw_response.get("photo"),
                "mobile_linked": raw_response.get("mobileLinked", False),
                "pan_name_match": raw_response.get("panNameMatch"),
                "face_match_score": raw_response.get("faceMatchScore"),
                "reference_id": raw_response.get("referenceId"),
                "timestamp": raw_response.get("timestamp"),
            },
        }

    async def _call(self, payload: AdapterPayload) -> dict[str, Any]:
        cfg: KYCConfig = self.config  # type: ignore[assignment]

        if cfg.sandbox_mode:
            return self._sandbox_response(payload)

        kyc_type = payload["kyc_type"]
        endpoint_map = {
            "aadhaar_otp": cfg.aadhaar_otp_url,
            "pan_verify": cfg.pan_verify_url,
            "face_match": f"{cfg.base_url}/face-match",
        }
        url = endpoint_map[kyc_type]

        ts = str(int(time.time()))
        body_str = json.dumps(payload)
        sig = _hmac_signature(cfg.client_secret.get_secret_value(), body_str, ts)

        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(
                url,
                content=body_str,
                headers={
                    "Content-Type": "application/json",
                    "X-Client-Id": cfg.client_id,
                    "X-Timestamp": ts,
                    "X-Signature": sig,
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _sandbox_response(payload: AdapterPayload) -> dict[str, Any]:
        aadhaar = str(payload.get("aadhaar_number", "000000000000"))
        seed = int(hashlib.md5(aadhaar.encode(), usedforsecurity=False).hexdigest(), 16)  # noqa: S324
        return {
            "status": "success",
            "name": "SANDBOX USER",
            "dob": "1990-01-01",
            "gender": "M" if seed % 2 == 0 else "F",
            "address": {
                "house": f"{seed % 999 + 1}",
                "street": "Test Street",
                "locality": "Test Area",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400001",
            },
            "photo": None,
            "mobileLinked": True,
            "panNameMatch": True,
            "faceMatchScore": 0.95,
            "referenceId": f"KYC{seed % 9999999:07d}",
            "timestamp": "2025-03-01T10:00:00+05:30",
        }


# ---------------------------------------------------------------------------
# V2 — DigiLocker + Video KYC
# ---------------------------------------------------------------------------

class KYCAdapterV2(BaseAdapter):
    """KYC V2 — adds DigiLocker XML pull and video KYC initiation."""

    metadata = AdapterMetadata(
        kind="kyc",
        version="v2",
        display_name="KYC Provider — Aadhaar + DigiLocker + Video KYC (V2)",
        provider="AadhaarBridge",
        supported_fields=_KYC_V1_FIELDS + _KYC_V2_EXTRA_FIELDS,
        auth_types=(AuthType.HMAC, AuthType.OAUTH2),
        rate_limit=RateLimit(requests_per_second=3.0, daily_quota=8000, burst_size=8),
        endpoint_template="https://api.kyc-provider.in/v2/{kyc_type}",
        sandbox_url="https://sandbox.kyc-provider.in/v2/{kyc_type}",
        response_codes={
            200: "Verification successful",
            202: "Video KYC session created",
            400: "Invalid parameters",
            401: "Authentication failed",
            403: "Consent artefact expired",
            404: "Record not found",
            409: "Session already active",
            429: "Rate limit exceeded",
        },
        tags=("kyc", "aadhaar", "digilocker", "video_kyc", "pan"),
    )

    Config = KYCConfigV2
    auto_register = True

    async def connect(self) -> None:
        cfg: KYCConfigV2 = self.config  # type: ignore[assignment]
        if cfg.sandbox_mode:
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            ts = str(int(time.time()))
            sig = _hmac_signature(cfg.client_secret.get_secret_value(), "", ts)
            resp = await client.get(
                f"{cfg.base_url}/health",
                headers={"X-Client-Id": cfg.client_id, "X-Timestamp": ts, "X-Signature": sig},
            )
            if resp.status_code not in (200, 204):
                raise ConnectionError(f"KYC V2 health check failed: {resp.status_code}")

    # V2 extends V1 enum with these additional types
    _V2_TYPES = frozenset({"aadhaar_otp", "pan_verify", "face_match", "digilocker_pull", "video_kyc"})

    def validate(self, payload: AdapterPayload) -> list[str]:
        errors: list[str] = []
        kyc_type = payload.get("kyc_type")

        if not kyc_type:
            errors.append("kyc_type is required")
        elif kyc_type not in self._V2_TYPES:
            errors.append(f"kyc_type {kyc_type!r} is invalid for V2 (valid: {sorted(self._V2_TYPES)})")

        if not payload.get("consent"):
            errors.append("consent must be True")

        mobile = payload.get("mobile")
        if not mobile:
            errors.append("mobile is required")
        elif not re.match(r"^[6-9]\d{9}$", str(mobile)):
            errors.append(f"mobile {mobile!r} is not a valid Indian mobile number")

        if kyc_type == "aadhaar_otp":
            aadhaar = payload.get("aadhaar_number")
            if not aadhaar:
                errors.append("aadhaar_number is required for kyc_type=aadhaar_otp")
            elif not re.match(r"^\d{12}$", str(aadhaar)):
                errors.append("aadhaar_number must be 12 digits")

        if kyc_type == "pan_verify":
            pan = payload.get("pan")
            if not pan:
                errors.append("pan is required for kyc_type=pan_verify")
            elif not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", str(pan)):
                errors.append(f"pan {pan!r} is invalid")

        if kyc_type == "face_match" and not payload.get("face_image_b64"):
            errors.append("face_image_b64 is required for kyc_type=face_match")

        if kyc_type == "digilocker_pull":
            if not payload.get("digilocker_token"):
                errors.append("digilocker_token is required for kyc_type=digilocker_pull")
            if not payload.get("document_type"):
                errors.append("document_type is required for kyc_type=digilocker_pull")

        return errors

    def transform(self, raw_response: dict[str, Any]) -> AdapterResult:
        result = {
            "success": raw_response.get("status") in ("success", "created"),
            "adapter": self.adapter_id,
            "data": {
                "kyc_status": raw_response.get("status"),
                "name": raw_response.get("name"),
                "dob": raw_response.get("dob"),
                "gender": raw_response.get("gender"),
                "address": raw_response.get("address", {}),
                "reference_id": raw_response.get("referenceId"),
                "timestamp": raw_response.get("timestamp"),
                # V2 extras
                "document_type": raw_response.get("documentType"),
                "document_number": raw_response.get("documentNumber"),
                "document_expiry": raw_response.get("documentExpiry"),
                "video_kyc_session_url": raw_response.get("videoKycSessionUrl"),
                "consent_artefact_id": raw_response.get("consentArtefactId"),
            },
        }
        return result

    async def _call(self, payload: AdapterPayload) -> dict[str, Any]:
        cfg: KYCConfigV2 = self.config  # type: ignore[assignment]

        if cfg.sandbox_mode:
            return self._sandbox_response(payload)

        kyc_type = payload.get("kyc_type", "aadhaar_otp")
        endpoint_map = {
            "aadhaar_otp": cfg.aadhaar_otp_url,
            "pan_verify": cfg.pan_verify_url,
            "face_match": f"{cfg.base_url}/face-match",
            "digilocker_pull": cfg.digilocker_url,
            "video_kyc": cfg.video_kyc_url,
        }
        url = endpoint_map.get(kyc_type, cfg.base_url)

        ts = str(int(time.time()))
        body_str = json.dumps(payload)
        sig = _hmac_signature(cfg.client_secret.get_secret_value(), body_str, ts)

        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(
                url,
                content=body_str,
                headers={
                    "Content-Type": "application/json",
                    "X-Client-Id": cfg.client_id,
                    "X-Timestamp": ts,
                    "X-Signature": sig,
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _sandbox_response(payload: AdapterPayload) -> dict[str, Any]:
        kyc_type = payload.get("kyc_type", "aadhaar_otp")
        base: dict[str, Any] = {
            "status": "success",
            "name": "SANDBOX USER V2",
            "dob": "1990-01-01",
            "gender": "M",
            "address": {"city": "Bengaluru", "state": "Karnataka", "pincode": "560001"},
            "referenceId": "KYCV2SANDBOX001",
            "timestamp": "2025-03-01T10:00:00+05:30",
        }
        if kyc_type == "digilocker_pull":
            base.update({
                "documentType": payload.get("document_type", "driving_license"),
                "documentNumber": "DL-2010-0123456",
                "documentExpiry": "2030-12-31",
                "consentArtefactId": "CONSENT-SANDBOX-001",
            })
        if kyc_type == "video_kyc":
            base.update({
                "status": "created",
                "videoKycSessionUrl": "https://sandbox.kyc-provider.in/video/SESSION001",
            })
        return base
