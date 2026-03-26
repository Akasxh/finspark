"""
SMS Gateway adapter — Kaleyra / ValueFirst / Twilio India style.

Operations:
  send_otp         — send OTP SMS via DLT-registered template
  send_transactional — send transactional alert (loan disbursement, EMI reminder)
  send_promotional — send promotional SMS (lower priority, restricted hours)
  check_delivery   — fetch delivery report for a message_id

Auth: API key in X-API-Key header
DLT: Indian TRAI DLT compliance fields are mandatory for all templates.

Sandbox: messages are accepted but not actually sent; DLT validation is skipped.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx

from app.integrations.base import BaseAdapter
from app.integrations.config import SMSGatewayConfig
from app.integrations.metadata import AdapterMetadata, FieldSchema, RateLimit
from app.integrations.types import AdapterPayload, AdapterResult, AuthType


_SMS_FIELDS = (
    FieldSchema(
        name="operation",
        dtype="enum",
        required=True,
        description="SMS operation to perform",
        example="send_otp",
        enum_values=("send_otp", "send_transactional", "send_promotional", "check_delivery"),
    ),
    FieldSchema(
        name="mobile",
        dtype="str",
        required=False,
        description="Recipient 10-digit Indian mobile number",
        example="9876543210",
        pattern=r"^[6-9]\d{9}$",
        max_length=10,
    ),
    FieldSchema(
        name="message",
        dtype="str",
        required=False,
        description="SMS message body. Must match the DLT template.",
        max_length=1600,
    ),
    FieldSchema(
        name="template_id",
        dtype="str",
        required=False,
        description="TRAI DLT template ID (19 digits). Overrides config default.",
        pattern=r"^\d{19}$",
        max_length=19,
    ),
    FieldSchema(
        name="otp",
        dtype="str",
        required=False,
        description="6-digit OTP to embed in template (for send_otp)",
        pattern=r"^\d{4,8}$",
    ),
    FieldSchema(
        name="applicant_name",
        dtype="str",
        required=False,
        description="Applicant name for personalised templates",
    ),
    FieldSchema(
        name="loan_amount_inr",
        dtype="float",
        required=False,
        description="Loan amount in INR (for transactional templates)",
    ),
    FieldSchema(
        name="due_date",
        dtype="date",
        required=False,
        description="EMI due date (YYYY-MM-DD) for reminder templates",
    ),
    FieldSchema(
        name="message_id",
        dtype="str",
        required=False,
        description="Message ID returned from a prior send_* call (for check_delivery)",
    ),
    FieldSchema(
        name="unicode",
        dtype="bool",
        required=False,
        description="Send as Unicode SMS (required for Hindi/regional language content)",
    ),
    FieldSchema(
        name="flash",
        dtype="bool",
        required=False,
        description="Send as flash SMS (class 0, displayed immediately, not stored)",
    ),
)

# Pre-defined DLT-style message templates
_OTP_TEMPLATE = "Dear Customer, your OTP for {purpose} is {otp}. Valid for 10 minutes. Do not share. -FinSpark"
_DISBURSAL_TEMPLATE = (
    "Dear {applicant_name}, your loan of Rs.{loan_amount_inr} has been disbursed to your account. "
    "Ref: {reference_id}. -FinSpark"
)
_EMI_REMINDER_TEMPLATE = (
    "Dear {applicant_name}, your EMI of Rs.{emi_amount} is due on {due_date}. "
    "Pay via app or bank. -FinSpark"
)


class SMSGatewayAdapterV1(BaseAdapter):
    """Kaleyra-style SMS gateway — OTP, transactional, promotional, delivery report."""

    metadata = AdapterMetadata(
        kind="sms_gateway",
        version="v1",
        display_name="SMS Gateway — Kaleyra India DLT (V1)",
        provider="Kaleyra",
        supported_fields=_SMS_FIELDS,
        auth_types=(AuthType.API_KEY,),
        rate_limit=RateLimit(requests_per_second=20.0, daily_quota=100000, burst_size=50),
        endpoint_template="https://api.kaleyra.io/v1/{operation}",
        sandbox_url="https://sandbox.kaleyra.io/v1/{operation}",
        response_codes={
            200: "Message accepted",
            400: "Invalid parameters or DLT violation",
            401: "Invalid API key",
            403: "Sender ID not registered / DLT entity mismatch",
            404: "Message ID not found (check_delivery)",
            429: "Rate limit exceeded",
            503: "SMS gateway unavailable",
        },
        tags=("sms", "otp", "transactional", "promotional", "dlt", "india"),
    )

    Config = SMSGatewayConfig
    auto_register = True

    async def connect(self) -> None:
        cfg: SMSGatewayConfig = self.config  # type: ignore[assignment]
        if cfg.sandbox_mode:
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{cfg.base_url}/health",
                headers={"X-API-Key": cfg.api_key.get_secret_value()},
            )
            if resp.status_code not in (200, 204):
                raise ConnectionError(f"SMS gateway health check failed: {resp.status_code}")

    def validate(self, payload: AdapterPayload) -> list[str]:
        errors: list[str] = []
        operation = payload.get("operation")

        if not operation:
            errors.append("operation is required")
            return errors

        valid_ops = ("send_otp", "send_transactional", "send_promotional", "check_delivery")
        if operation not in valid_ops:
            errors.append(f"operation {operation!r} is invalid")

        if operation in ("send_otp", "send_transactional", "send_promotional"):
            mobile = payload.get("mobile")
            if not mobile:
                errors.append("mobile is required for send operations")
            elif not re.match(r"^[6-9]\d{9}$", str(mobile)):
                errors.append(f"mobile {mobile!r} is not a valid Indian mobile number")

        if operation == "send_otp":
            otp = payload.get("otp")
            if otp and not re.match(r"^\d{4,8}$", str(otp)):
                errors.append("otp must be 4–8 digits")

        if operation in ("send_transactional", "send_promotional"):
            if not payload.get("message"):
                errors.append("message is required for transactional/promotional SMS")
            elif len(str(payload["message"])) > 1600:
                errors.append("message must not exceed 1600 characters")

        if operation == "check_delivery" and not payload.get("message_id"):
            errors.append("message_id is required for check_delivery")

        return errors

    def transform(self, raw_response: dict[str, Any]) -> AdapterResult:
        op = raw_response.get("_operation", "unknown")

        if op in ("send_otp", "send_transactional", "send_promotional"):
            data = {
                "message_id": raw_response.get("message_id"),
                "mobile": raw_response.get("mobile"),
                "status": raw_response.get("status"),
                "credits_used": raw_response.get("credits", 1),
                "submitted_at": raw_response.get("submitted_at"),
                "dlt_entity_id": raw_response.get("dlt_entity_id"),
            }
        elif op == "check_delivery":
            data = {
                "message_id": raw_response.get("message_id"),
                "mobile": raw_response.get("mobile"),
                "delivery_status": raw_response.get("delivery_status"),
                "delivered_at": raw_response.get("delivered_at"),
                "operator": raw_response.get("operator"),
                "error_code": raw_response.get("error_code"),
            }
        else:
            data = raw_response

        return {"success": True, "adapter": self.adapter_id, "data": data}

    async def _call(self, payload: AdapterPayload) -> dict[str, Any]:
        cfg: SMSGatewayConfig = self.config  # type: ignore[assignment]

        if cfg.sandbox_mode:
            return self._sandbox_response(payload)

        operation = payload["operation"]
        headers = {
            "X-API-Key": cfg.api_key.get_secret_value(),
            "Content-Type": "application/json",
        }

        if operation == "send_otp":
            otp_val = str(payload.get("otp", ""))
            text = _OTP_TEMPLATE.format(
                purpose=payload.get("purpose", "verification"),
                otp=otp_val,
            )
            body = {
                "to": payload["mobile"],
                "from": cfg.sender_id,
                "body": text,
                "dlt_entity_id": cfg.dlt_entity_id,
                "dlt_template_id": payload.get("template_id", cfg.dlt_template_id),
                "type": "OTP",
            }
            async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                resp = await client.post(f"{cfg.base_url}/messages", headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "send_otp"
                data["mobile"] = payload["mobile"]
                return data

        if operation in ("send_transactional", "send_promotional"):
            msg_type = "TRANS" if operation == "send_transactional" else "PROMO"
            body = {
                "to": payload["mobile"],
                "from": cfg.sender_id,
                "body": payload["message"],
                "dlt_entity_id": cfg.dlt_entity_id,
                "dlt_template_id": payload.get("template_id", cfg.dlt_template_id),
                "type": msg_type,
                "unicode": payload.get("unicode", cfg.unicode_support),
                "flash": payload.get("flash", cfg.flash_sms),
            }
            async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                resp = await client.post(f"{cfg.base_url}/messages", headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = operation
                data["mobile"] = payload["mobile"]
                return data

        if operation == "check_delivery":
            mid = payload["message_id"]
            async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                resp = await client.get(
                    f"{cfg.base_url}/messages/{mid}/delivery", headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "check_delivery"
                return data

        raise ValueError(f"Unknown operation {operation!r}")

    @staticmethod
    def _sandbox_response(payload: AdapterPayload) -> dict[str, Any]:
        import time
        operation = str(payload.get("operation", "send_otp"))
        mobile = str(payload.get("mobile", "9999999999"))
        seed = int(hashlib.md5(mobile.encode(), usedforsecurity=False).hexdigest(), 16)  # noqa: S324
        msg_id = f"MSGSBX{seed % 9999999:07d}"

        if operation == "check_delivery":
            return {
                "_operation": "check_delivery",
                "message_id": payload.get("message_id", msg_id),
                "mobile": mobile,
                "delivery_status": "DELIVERED",
                "delivered_at": "2025-03-01T10:05:00+05:30",
                "operator": "Jio",
                "error_code": None,
            }
        return {
            "_operation": operation,
            "message_id": msg_id,
            "mobile": mobile,
            "status": "ACCEPTED",
            "credits": 1,
            "submitted_at": str(int(time.time())),
            "dlt_entity_id": "SANDBOX_DLT_ENTITY",
        }
