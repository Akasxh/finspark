"""
Credit Bureau adapters — CIBIL-like integration.

V1: Consumer bureau pull (TransUnion CIBIL TUSC3 product)
    Supports: credit score, account summary, enquiry history
    Auth: API key + member ID

V2: Adds commercial bureau (CIBIL MSME) fields + account-level risk flags
    Auth: API key + member ID (same scheme, different endpoints)

Sandbox mode returns deterministic fake data based on PAN hash —
no real network calls are made.
"""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from app.integrations.base import BaseAdapter
from app.integrations.config import CreditBureauConfig
from app.integrations.metadata import AdapterMetadata, FieldSchema, RateLimit
from app.integrations.types import (
    AdapterPayload,
    AdapterResult,
    AuthType,
)


# ---------------------------------------------------------------------------
# Shared field schemas
# ---------------------------------------------------------------------------

_COMMON_FIELDS = (
    FieldSchema(
        name="pan",
        dtype="str",
        required=True,
        description="10-char Permanent Account Number",
        example="ABCDE1234F",
        pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$",
        max_length=10,
    ),
    FieldSchema(
        name="full_name",
        dtype="str",
        required=True,
        description="Applicant full name as on PAN card",
        example="Ravi Kumar Sharma",
        max_length=120,
    ),
    FieldSchema(
        name="dob",
        dtype="date",
        required=True,
        description="Date of birth (YYYY-MM-DD)",
        example="1990-05-15",
    ),
    FieldSchema(
        name="mobile",
        dtype="str",
        required=False,
        description="10-digit mobile number (without country code)",
        example="9876543210",
        pattern=r"^[6-9]\d{9}$",
        max_length=10,
    ),
    FieldSchema(
        name="address_pin",
        dtype="str",
        required=False,
        description="6-digit postal PIN code",
        example="400001",
        pattern=r"^\d{6}$",
        max_length=6,
    ),
)

_V2_EXTRA_FIELDS = (
    FieldSchema(
        name="gstin",
        dtype="str",
        required=False,
        description="15-char GST Identification Number (for MSME bureau)",
        example="27ABCDE1234F1Z5",
        pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
        max_length=15,
    ),
    FieldSchema(
        name="udyam_number",
        dtype="str",
        required=False,
        description="Udyam Registration Number",
        example="UDYAM-MH-10-0012345",
        max_length=25,
    ),
    FieldSchema(
        name="bureau_segment",
        dtype="enum",
        required=False,
        description="Target bureau segment",
        example="consumer",
        enum_values=("consumer", "msme", "commercial"),
    ),
)


# ---------------------------------------------------------------------------
# V1 Adapter
# ---------------------------------------------------------------------------

class CIBILAdapterV1(BaseAdapter):
    """CIBIL consumer credit pull — TransUnion TUSC3 product."""

    metadata = AdapterMetadata(
        kind="credit_bureau",
        version="v1",
        display_name="CIBIL Consumer Bureau (V1)",
        provider="TransUnion CIBIL",
        supported_fields=_COMMON_FIELDS,
        auth_types=(AuthType.API_KEY,),
        rate_limit=RateLimit(requests_per_second=2.0, daily_quota=5000, burst_size=5),
        endpoint_template="https://api.cibil.com/v1/consumer/score",
        sandbox_url="https://sandbox.cibil.com/v1/consumer/score",
        response_codes={
            200: "Score retrieved successfully",
            400: "Invalid input parameters",
            401: "Invalid API key or member ID",
            403: "Consent not provided",
            404: "No bureau record found",
            429: "Rate limit exceeded",
            503: "CIBIL service unavailable",
        },
        tags=("credit_score", "consumer", "bureau"),
    )

    Config = CreditBureauConfig
    auto_register = True

    async def connect(self) -> None:
        cfg: CreditBureauConfig = self.config  # type: ignore[assignment]
        if cfg.sandbox_mode:
            return   # no real ping in sandbox
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{cfg.base_url}/health",
                headers={"X-API-Key": cfg.api_key.get_secret_value()},
            )
            if resp.status_code not in (200, 204):
                raise ConnectionError(
                    f"CIBIL health check failed: HTTP {resp.status_code}"
                )

    def validate(self, payload: AdapterPayload) -> list[str]:
        errors: list[str] = []
        import re

        pan = payload.get("pan", "")
        if not pan:
            errors.append("pan is required")
        elif not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", str(pan)):
            errors.append(f"pan {pan!r} does not match pattern [A-Z]{{5}}[0-9]{{4}}[A-Z]")

        if not payload.get("full_name"):
            errors.append("full_name is required")

        if not payload.get("dob"):
            errors.append("dob is required")

        mobile = payload.get("mobile")
        if mobile and not re.match(r"^[6-9]\d{9}$", str(mobile)):
            errors.append(f"mobile {mobile!r} must be a 10-digit Indian mobile number")

        return errors

    def transform(self, raw_response: dict[str, Any]) -> AdapterResult:
        return {
            "success": True,
            "adapter": self.adapter_id,
            "data": {
                "credit_score": raw_response.get("score", 0),
                "score_version": raw_response.get("scoreVersion", "CIBIL_V3"),
                "credit_rank": raw_response.get("creditRank"),
                "account_summary": {
                    "total_accounts": raw_response.get("totalAccounts", 0),
                    "active_accounts": raw_response.get("activeAccounts", 0),
                    "closed_accounts": raw_response.get("closedAccounts", 0),
                    "delinquent_accounts": raw_response.get("delinquentAccounts", 0),
                    "overdue_amount_inr": raw_response.get("overdueAmount", 0),
                },
                "enquiry_summary": {
                    "total_enquiries_6m": raw_response.get("enquiries6Months", 0),
                    "total_enquiries_12m": raw_response.get("enquiries12Months", 0),
                    "last_enquiry_date": raw_response.get("lastEnquiryDate"),
                },
                "report_date": raw_response.get("reportDate"),
                "control_number": raw_response.get("controlNumber"),
            },
        }

    async def _call(self, payload: AdapterPayload) -> dict[str, Any]:
        cfg: CreditBureauConfig = self.config  # type: ignore[assignment]

        if cfg.sandbox_mode:
            return self._sandbox_response(payload)

        url = cfg.base_url + "/consumer/score"
        headers = {
            "X-API-Key": cfg.api_key.get_secret_value(),
            "X-Member-Id": cfg.member_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        request_body = {
            "productCode": cfg.product_code,
            "requestFields": {
                "pan": payload["pan"],
                "fullName": payload["full_name"],
                "dateOfBirth": payload["dob"],
                "mobilePhone": payload.get("mobile"),
                "address": {"pinCode": payload.get("address_pin")},
            },
            "includeAccountSummary": cfg.include_account_summary,
            "includeEnquirySummary": cfg.include_enquiry_summary,
        }
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=request_body)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _sandbox_response(payload: AdapterPayload) -> dict[str, Any]:
        """Deterministic fake response based on PAN hash — no RNG variance."""
        pan = str(payload.get("pan", "XXXXX0000X"))
        seed = int(hashlib.md5(pan.encode(), usedforsecurity=False).hexdigest(), 16)  # noqa: S324
        score = 300 + (seed % 600)          # 300–899 CIBIL range
        return {
            "score": score,
            "scoreVersion": "CIBIL_V3",
            "creditRank": "1" if score > 750 else ("2" if score > 650 else "5"),
            "totalAccounts": (seed % 8) + 1,
            "activeAccounts": (seed % 4) + 1,
            "closedAccounts": seed % 4,
            "delinquentAccounts": seed % 2,
            "overdueAmount": (seed % 50000),
            "enquiries6Months": seed % 5,
            "enquiries12Months": seed % 8,
            "lastEnquiryDate": "2024-11-01",
            "reportDate": "2025-03-01",
            "controlNumber": f"CIBIL{seed % 9999999:07d}",
        }


# ---------------------------------------------------------------------------
# V2 Adapter — extends V1 with MSME + commercial bureau fields
# ---------------------------------------------------------------------------

class CIBILAdapterV2(BaseAdapter):
    """CIBIL V2 — consumer + MSME commercial bureau pull."""

    metadata = AdapterMetadata(
        kind="credit_bureau",
        version="v2",
        display_name="CIBIL Consumer + MSME Bureau (V2)",
        provider="TransUnion CIBIL",
        supported_fields=_COMMON_FIELDS + _V2_EXTRA_FIELDS,
        auth_types=(AuthType.API_KEY,),
        rate_limit=RateLimit(requests_per_second=1.5, daily_quota=3000, burst_size=5),
        endpoint_template="https://api.cibil.com/v2/bureau/pull",
        sandbox_url="https://sandbox.cibil.com/v2/bureau/pull",
        response_codes={
            200: "Report retrieved successfully",
            400: "Invalid input parameters",
            401: "Invalid credentials",
            403: "Consent artefact missing or expired",
            404: "No bureau record found",
            422: "Business entity not found in MSME bureau",
            429: "Rate limit exceeded",
            503: "CIBIL service unavailable",
        },
        tags=("credit_score", "consumer", "msme", "commercial", "bureau"),
    )

    Config = CreditBureauConfig
    auto_register = True

    async def connect(self) -> None:
        cfg: CreditBureauConfig = self.config  # type: ignore[assignment]
        if cfg.sandbox_mode:
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{cfg.base_url}/health",
                headers={"X-API-Key": cfg.api_key.get_secret_value()},
            )
            if resp.status_code not in (200, 204):
                raise ConnectionError(f"CIBIL V2 health check failed: HTTP {resp.status_code}")

    def validate(self, payload: AdapterPayload) -> list[str]:
        import re
        errors: list[str] = []

        pan = payload.get("pan", "")
        if not pan:
            errors.append("pan is required")
        elif not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", str(pan)):
            errors.append(f"pan {pan!r} is invalid")

        if not payload.get("full_name"):
            errors.append("full_name is required")

        if not payload.get("dob"):
            errors.append("dob is required")

        gstin = payload.get("gstin")
        if gstin and not re.match(
            r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", str(gstin)
        ):
            errors.append(f"gstin {gstin!r} is not a valid GSTIN")

        segment = payload.get("bureau_segment")
        if segment and segment not in ("consumer", "msme", "commercial"):
            errors.append(f"bureau_segment {segment!r} must be one of consumer/msme/commercial")

        return errors

    def transform(self, raw_response: dict[str, Any]) -> AdapterResult:
        base = {
            "success": True,
            "adapter": self.adapter_id,
            "data": {
                "consumer": {
                    "credit_score": raw_response.get("consumerScore", 0),
                    "score_version": raw_response.get("consumerScoreVersion", "CIBIL_V3"),
                    "account_summary": raw_response.get("consumerAccountSummary", {}),
                },
                "commercial": {
                    "company_credit_rank": raw_response.get("commercialCreditRank"),
                    "commercial_score": raw_response.get("commercialScore"),
                    "payment_behaviour_score": raw_response.get("paymentBehaviourScore"),
                    "delinquency_score": raw_response.get("delinquencyScore"),
                    "outstanding_balance_inr": raw_response.get("outstandingBalance", 0),
                    "credit_utilisation_pct": raw_response.get("creditUtilisation"),
                },
                "risk_flags": raw_response.get("riskFlags", []),
                "report_date": raw_response.get("reportDate"),
                "control_number": raw_response.get("controlNumber"),
            },
        }
        return base

    async def _call(self, payload: AdapterPayload) -> dict[str, Any]:
        cfg: CreditBureauConfig = self.config  # type: ignore[assignment]

        if cfg.sandbox_mode:
            return self._sandbox_response(payload)

        url = cfg.base_url + "/bureau/pull"
        headers = {
            "X-API-Key": cfg.api_key.get_secret_value(),
            "X-Member-Id": cfg.member_id,
            "Content-Type": "application/json",
        }
        body = {
            "pan": payload["pan"],
            "fullName": payload["full_name"],
            "dob": payload["dob"],
            "mobile": payload.get("mobile"),
            "gstin": payload.get("gstin"),
            "bureauSegment": payload.get("bureau_segment", "consumer"),
        }
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _sandbox_response(payload: AdapterPayload) -> dict[str, Any]:
        pan = str(payload.get("pan", "XXXXX0000X"))
        seed = int(hashlib.md5(pan.encode(), usedforsecurity=False).hexdigest(), 16)  # noqa: S324
        consumer_score = 300 + (seed % 600)
        return {
            "consumerScore": consumer_score,
            "consumerScoreVersion": "CIBIL_V3",
            "consumerAccountSummary": {
                "totalAccounts": (seed % 8) + 1,
                "activeAccounts": (seed % 4) + 1,
                "delinquentAccounts": seed % 2,
            },
            "commercialCreditRank": str((seed % 10) + 1),
            "commercialScore": 400 + (seed % 400),
            "paymentBehaviourScore": 50 + (seed % 50),
            "delinquencyScore": seed % 30,
            "outstandingBalance": (seed % 5000000),
            "creditUtilisation": round((seed % 100) / 100, 2),
            "riskFlags": ["MULTIPLE_ENQUIRIES"] if seed % 3 == 0 else [],
            "reportDate": "2025-03-01",
            "controlNumber": f"CIBIL2V{seed % 9999999:07d}",
        }
