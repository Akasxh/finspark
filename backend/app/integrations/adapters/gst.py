"""
GST Service adapter — GSTN Public API (NIC / GST Suvidha Provider style).

Operations:
  gstin_verify    — validate GSTIN and fetch taxpayer profile
  returns_summary — fetch GSTR-3B / GSTR-1 return filing history
  ledger_summary  — electronic credit / cash ledger balances

Auth: username + password session token (encrypted via app_key AES-256).
All requests must be signed; session tokens expire every 6 hours.

Sandbox: GSTN provides a public sandbox at https://api.gst.gov.in/commonapi/sandbox
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx

from app.integrations.base import BaseAdapter
from app.integrations.config import GSTConfig
from app.integrations.metadata import AdapterMetadata, FieldSchema, RateLimit
from app.integrations.types import AdapterPayload, AdapterResult, AuthType


_GST_FIELDS = (
    FieldSchema(
        name="gstin",
        dtype="str",
        required=True,
        description="15-char GST Identification Number",
        example="27ABCDE1234F1Z5",
        pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
        max_length=15,
    ),
    FieldSchema(
        name="operation",
        dtype="enum",
        required=True,
        description="GST API operation to perform",
        example="gstin_verify",
        enum_values=("gstin_verify", "returns_summary", "ledger_summary"),
    ),
    FieldSchema(
        name="financial_year",
        dtype="str",
        required=False,
        description="Financial year in YYYY-YY format (required for returns_summary)",
        example="2024-25",
        pattern=r"^\d{4}-\d{2}$",
    ),
    FieldSchema(
        name="return_type",
        dtype="enum",
        required=False,
        description="GSTR return type (required for returns_summary)",
        example="GSTR3B",
        enum_values=("GSTR1", "GSTR3B", "GSTR9"),
    ),
    FieldSchema(
        name="ledger_type",
        dtype="enum",
        required=False,
        description="Ledger type (required for ledger_summary)",
        example="CREDIT",
        enum_values=("CREDIT", "CASH", "LIABILITY"),
    ),
)


class GSTAdapterV1(BaseAdapter):
    """GSTN API V1 — GSTIN verification, returns summary, ledger balances."""

    metadata = AdapterMetadata(
        kind="gst",
        version="v1",
        display_name="GST Network API (V1)",
        provider="GSTN / NIC",
        supported_fields=_GST_FIELDS,
        auth_types=(AuthType.BASIC,),
        rate_limit=RateLimit(requests_per_second=1.0, daily_quota=2000, burst_size=3),
        endpoint_template="https://api.gst.gov.in/commonapi/v1.1/{operation}?gstin={gstin}",
        sandbox_url="https://api.gst.gov.in/commonapi/sandbox/v1.1/{operation}",
        response_codes={
            200: "Success",
            400: "Bad request / invalid GSTIN",
            401: "Authentication failed",
            403: "IP not whitelisted",
            404: "GSTIN not registered",
            429: "Threshold limit exceeded",
            500: "GSTN server error",
        },
        tags=("gst", "tax", "gstin", "returns", "ledger"),
    )

    Config = GSTConfig
    auto_register = True

    # Session token cache (class-level; shared across instances with same config)
    _session_token: str | None = None
    _session_expiry: float = 0.0

    async def connect(self) -> None:
        cfg: GSTConfig = self.config  # type: ignore[assignment]
        if cfg.sandbox_mode:
            return
        await self._refresh_session(cfg)

    async def _refresh_session(self, cfg: GSTConfig) -> str:
        import time
        if self._session_token and time.time() < self._session_expiry:
            return self._session_token  # type: ignore[return-value]

        # GSTN token endpoint — simplified: real impl uses AES encryption of credentials
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(
                f"{cfg.base_url}/authenticate",
                json={
                    "username": cfg.gstn_username,
                    "password": cfg.gstn_password.get_secret_value(),
                    "app_key": cfg.app_key.get_secret_value(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self.__class__._session_token = data["authToken"]
            self.__class__._session_expiry = time.time() + 6 * 3600
        return self._session_token  # type: ignore[return-value]

    def validate(self, payload: AdapterPayload) -> list[str]:
        errors: list[str] = []

        gstin = payload.get("gstin", "")
        if not gstin:
            errors.append("gstin is required")
        elif not re.match(
            r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", str(gstin)
        ):
            errors.append(f"gstin {gstin!r} is not a valid GSTIN")

        operation = payload.get("operation")
        if not operation:
            errors.append("operation is required")
        elif operation not in ("gstin_verify", "returns_summary", "ledger_summary"):
            errors.append(f"operation {operation!r} is invalid")

        if operation == "returns_summary":
            if not payload.get("financial_year"):
                errors.append("financial_year is required for returns_summary")
            if not payload.get("return_type"):
                errors.append("return_type is required for returns_summary")

        if operation == "ledger_summary" and not payload.get("ledger_type"):
            errors.append("ledger_type is required for ledger_summary")

        return errors

    def transform(self, raw_response: dict[str, Any]) -> AdapterResult:
        operation = raw_response.get("_operation", "unknown")

        if operation == "gstin_verify":
            data = {
                "gstin": raw_response.get("gstin"),
                "legal_name": raw_response.get("lgnm"),
                "trade_name": raw_response.get("tradeNam"),
                "registration_date": raw_response.get("rgdt"),
                "cancellation_date": raw_response.get("cxdt"),
                "taxpayer_type": raw_response.get("dty"),
                "status": raw_response.get("sts"),
                "state_code": raw_response.get("stj", "")[:2],
                "constitution": raw_response.get("ctb"),
                "annual_aggregate_turnover": raw_response.get("aadhaarValidation"),
                "last_update": raw_response.get("lstupdt"),
            }
        elif operation == "returns_summary":
            data = {
                "gstin": raw_response.get("gstin"),
                "return_type": raw_response.get("rtntype"),
                "financial_year": raw_response.get("fy"),
                "filings": [
                    {
                        "period": f.get("taxp"),
                        "return_period": f.get("ret_prd"),
                        "filing_date": f.get("dof"),
                        "status": f.get("valid"),
                        "mode_of_filing": f.get("mof"),
                    }
                    for f in raw_response.get("filings", [])
                ],
            }
        elif operation == "ledger_summary":
            data = {
                "gstin": raw_response.get("gstin"),
                "ledger_type": raw_response.get("ledgerType"),
                "igst_balance": raw_response.get("igstBalance", 0),
                "cgst_balance": raw_response.get("cgstBalance", 0),
                "sgst_balance": raw_response.get("sgstBalance", 0),
                "cess_balance": raw_response.get("cessBalance", 0),
                "total_balance": raw_response.get("totalBalance", 0),
                "as_of_date": raw_response.get("balanceDate"),
            }
        else:
            data = raw_response

        return {"success": True, "adapter": self.adapter_id, "data": data}

    async def _call(self, payload: AdapterPayload) -> dict[str, Any]:
        cfg: GSTConfig = self.config  # type: ignore[assignment]

        if cfg.sandbox_mode:
            return self._sandbox_response(payload)

        operation = payload["operation"]
        gstin = payload["gstin"]
        base = cfg.base_url

        token = await self._refresh_session(cfg)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        if operation == "gstin_verify":
            url = f"{base}/search?gstin={gstin}"
            async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "gstin_verify"
                return data

        if operation == "returns_summary":
            url = f"{base}/returns?gstin={gstin}&fy={payload['financial_year']}&rtntype={payload['return_type']}"
            async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "returns_summary"
                return data

        if operation == "ledger_summary":
            url = f"{base}/ledgersummary?gstin={gstin}&type={payload['ledger_type']}"
            async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "ledger_summary"
                return data

        raise ValueError(f"Unknown operation {operation!r}")

    @staticmethod
    def _sandbox_response(payload: AdapterPayload) -> dict[str, Any]:
        gstin = str(payload.get("gstin", "27AAPFU0939F1ZV"))
        operation = str(payload.get("operation", "gstin_verify"))
        seed = int(hashlib.md5(gstin.encode(), usedforsecurity=False).hexdigest(), 16)  # noqa: S324

        if operation == "gstin_verify":
            return {
                "_operation": "gstin_verify",
                "gstin": gstin,
                "lgnm": "SANDBOX ENTERPRISES PVT LTD",
                "tradeNam": "SANDBOX ENT",
                "rgdt": "01/04/2018",
                "cxdt": "",
                "dty": "Regular",
                "sts": "Active",
                "stj": f"{gstin[:2]} - State Jurisdiction",
                "ctb": "Private Limited Company",
                "lstupdt": "01/01/2025",
            }
        if operation == "returns_summary":
            return {
                "_operation": "returns_summary",
                "gstin": gstin,
                "rtntype": payload.get("return_type", "GSTR3B"),
                "fy": payload.get("financial_year", "2024-25"),
                "filings": [
                    {"taxp": "042025", "ret_prd": "042025", "dof": "20-05-2025", "valid": "Y", "mof": "ONLINE"},
                    {"taxp": "032025", "ret_prd": "032025", "dof": "21-04-2025", "valid": "Y", "mof": "ONLINE"},
                    {"taxp": "022025", "ret_prd": "022025", "dof": "20-03-2025", "valid": "Y", "mof": "ONLINE"},
                ],
            }
        # ledger_summary
        return {
            "_operation": "ledger_summary",
            "gstin": gstin,
            "ledgerType": payload.get("ledger_type", "CREDIT"),
            "igstBalance": (seed % 500000),
            "cgstBalance": (seed % 250000),
            "sgstBalance": (seed % 250000),
            "cessBalance": seed % 10000,
            "totalBalance": (seed % 1000000),
            "balanceDate": "2025-03-01",
        }
