"""
Payment Gateway adapter — Razorpay-style integration.

Operations:
  create_order      — create a payment order
  capture_payment   — capture an authorised payment
  refund_payment    — initiate a full or partial refund
  verify_signature  — verify Razorpay webhook/payment signature
  fetch_settlement  — fetch settlement details by settlement_id

Auth: key_id + key_secret (HTTP Basic Auth, base64 encoded)
Webhook verification: HMAC-SHA256 of payload using webhook_secret
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

import httpx

from app.integrations.base import BaseAdapter
from app.integrations.config import PaymentGatewayConfig
from app.integrations.metadata import AdapterMetadata, FieldSchema, RateLimit
from app.integrations.types import AdapterPayload, AdapterResult, AuthType


_PG_FIELDS = (
    FieldSchema(
        name="operation",
        dtype="enum",
        required=True,
        description="Payment Gateway operation",
        example="create_order",
        enum_values=("create_order", "capture_payment", "refund_payment", "verify_signature", "fetch_settlement"),
    ),
    FieldSchema(
        name="amount_paise",
        dtype="int",
        required=False,
        description="Amount in Indian Paise (1 INR = 100 paise). Required for create_order.",
        example=50000,
    ),
    FieldSchema(
        name="order_id",
        dtype="str",
        required=False,
        description="Razorpay order ID (order_XXXXXXXX). Required for capture_payment and refund_payment.",
        example="order_LMqjNFcABDOaUi",
        pattern=r"^order_[A-Za-z0-9]{14}$",
    ),
    FieldSchema(
        name="payment_id",
        dtype="str",
        required=False,
        description="Razorpay payment ID. Required for capture_payment and refund_payment.",
        example="pay_LMqjNFcABDOaUi",
        pattern=r"^pay_[A-Za-z0-9]{14}$",
    ),
    FieldSchema(
        name="refund_amount_paise",
        dtype="int",
        required=False,
        description="Refund amount in paise (partial refund). Defaults to full amount if omitted.",
    ),
    FieldSchema(
        name="receipt",
        dtype="str",
        required=False,
        description="Merchant receipt ID for order (max 40 chars)",
        max_length=40,
    ),
    FieldSchema(
        name="notes",
        dtype="str",
        required=False,
        description="Key-value metadata attached to order (JSON string)",
    ),
    FieldSchema(
        name="razorpay_signature",
        dtype="str",
        required=False,
        description="HMAC signature from Razorpay webhook / payment response",
    ),
    FieldSchema(
        name="settlement_id",
        dtype="str",
        required=False,
        description="Razorpay settlement ID. Required for fetch_settlement.",
        pattern=r"^setl_[A-Za-z0-9]{14}$",
    ),
    FieldSchema(
        name="customer_email",
        dtype="str",
        required=False,
        description="Customer email for order",
        example="customer@example.com",
    ),
    FieldSchema(
        name="customer_mobile",
        dtype="str",
        required=False,
        description="Customer mobile number",
        pattern=r"^[6-9]\d{9}$",
    ),
    FieldSchema(
        name="upi_vpa",
        dtype="str",
        required=False,
        description="UPI Virtual Payment Address for collect request",
        example="customer@upi",
    ),
)


class PaymentGatewayAdapterV1(BaseAdapter):
    """Razorpay-style payment gateway — orders, captures, refunds, settlements."""

    metadata = AdapterMetadata(
        kind="payment_gateway",
        version="v1",
        display_name="Payment Gateway — Razorpay (V1)",
        provider="Razorpay",
        supported_fields=_PG_FIELDS,
        auth_types=(AuthType.BASIC,),
        rate_limit=RateLimit(requests_per_second=10.0, daily_quota=None, burst_size=20),
        endpoint_template="https://api.razorpay.com/v1/{resource}",
        sandbox_url="https://api.razorpay.com/v1/{resource}",   # Razorpay test keys use same URL
        response_codes={
            200: "Success",
            201: "Created",
            400: "Bad request",
            401: "Unauthorised — invalid key_id/key_secret",
            404: "Resource not found",
            409: "Payment already captured / refunded",
            429: "Rate limit exceeded",
            500: "Razorpay server error",
        },
        tags=("payment", "razorpay", "upi", "netbanking", "refund", "settlement"),
    )

    Config = PaymentGatewayConfig
    auto_register = True

    async def connect(self) -> None:
        cfg: PaymentGatewayConfig = self.config  # type: ignore[assignment]
        if cfg.sandbox_mode:
            return
        async with httpx.AsyncClient(
            auth=(cfg.key_id, cfg.key_secret.get_secret_value()),
            timeout=10.0,
        ) as client:
            resp = await client.get(f"{cfg.base_url}/payments?count=1")
            if resp.status_code not in (200, 201):
                raise ConnectionError(f"Razorpay connectivity check failed: {resp.status_code}")

    def validate(self, payload: AdapterPayload) -> list[str]:
        errors: list[str] = []
        operation = payload.get("operation")

        if not operation:
            errors.append("operation is required")
            return errors

        valid_ops = ("create_order", "capture_payment", "refund_payment", "verify_signature", "fetch_settlement")
        if operation not in valid_ops:
            errors.append(f"operation {operation!r} must be one of {valid_ops}")

        if operation == "create_order":
            amount = payload.get("amount_paise")
            if amount is None:
                errors.append("amount_paise is required for create_order")
            elif not isinstance(amount, int) or amount <= 0:
                errors.append("amount_paise must be a positive integer")

        if operation in ("capture_payment", "refund_payment"):
            if not payload.get("payment_id"):
                errors.append("payment_id is required for capture/refund operations")
            elif not re.match(r"^pay_[A-Za-z0-9]{14}$", str(payload["payment_id"])):
                errors.append("payment_id format is invalid (expected pay_XXXXXXXXXXXXXX)")

        if operation == "verify_signature":
            for field in ("order_id", "payment_id", "razorpay_signature"):
                if not payload.get(field):
                    errors.append(f"{field} is required for verify_signature")

        if operation == "fetch_settlement":
            sid = payload.get("settlement_id")
            if not sid:
                errors.append("settlement_id is required for fetch_settlement")
            elif not re.match(r"^setl_[A-Za-z0-9]{14}$", str(sid)):
                errors.append("settlement_id format is invalid")

        email = payload.get("customer_email")
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(email)):
            errors.append(f"customer_email {email!r} is not valid")

        return errors

    def transform(self, raw_response: dict[str, Any]) -> AdapterResult:
        op = raw_response.get("_operation", "unknown")

        if op == "create_order":
            data = {
                "order_id": raw_response.get("id"),
                "amount_paise": raw_response.get("amount"),
                "amount_inr": raw_response.get("amount", 0) / 100,
                "currency": raw_response.get("currency", "INR"),
                "status": raw_response.get("status"),
                "receipt": raw_response.get("receipt"),
                "attempts": raw_response.get("attempts", 0),
                "created_at": raw_response.get("created_at"),
            }
        elif op == "capture_payment":
            data = {
                "payment_id": raw_response.get("id"),
                "order_id": raw_response.get("order_id"),
                "amount_paise": raw_response.get("amount"),
                "status": raw_response.get("status"),
                "method": raw_response.get("method"),
                "bank": raw_response.get("bank"),
                "vpa": raw_response.get("vpa"),
                "captured_at": raw_response.get("created_at"),
            }
        elif op == "refund_payment":
            data = {
                "refund_id": raw_response.get("id"),
                "payment_id": raw_response.get("payment_id"),
                "amount_paise": raw_response.get("amount"),
                "status": raw_response.get("status"),
                "speed_processed": raw_response.get("speed_processed"),
                "created_at": raw_response.get("created_at"),
            }
        elif op == "verify_signature":
            data = {
                "valid": raw_response.get("valid", False),
                "payment_id": raw_response.get("payment_id"),
                "order_id": raw_response.get("order_id"),
            }
        elif op == "fetch_settlement":
            data = {
                "settlement_id": raw_response.get("id"),
                "entity": raw_response.get("entity"),
                "amount": raw_response.get("amount", 0),
                "status": raw_response.get("status"),
                "fees": raw_response.get("fees", 0),
                "tax": raw_response.get("tax", 0),
                "utr": raw_response.get("utr"),
                "created_at": raw_response.get("created_at"),
            }
        else:
            data = raw_response

        return {"success": True, "adapter": self.adapter_id, "data": data}

    async def _call(self, payload: AdapterPayload) -> dict[str, Any]:
        cfg: PaymentGatewayConfig = self.config  # type: ignore[assignment]

        if cfg.sandbox_mode:
            return self._sandbox_response(payload)

        operation = payload["operation"]
        auth = (cfg.key_id, cfg.key_secret.get_secret_value())

        async with httpx.AsyncClient(auth=auth, timeout=cfg.timeout_seconds) as client:
            if operation == "create_order":
                body = {
                    "amount": payload["amount_paise"],
                    "currency": cfg.currency,
                    "receipt": payload.get("receipt"),
                    "payment_capture": 1 if cfg.capture_mode == "automatic" else 0,
                }
                resp = await client.post(f"{cfg.base_url}/orders", json=body)
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "create_order"
                return data

            if operation == "capture_payment":
                pid = payload["payment_id"]
                body = {"amount": payload.get("amount_paise")}
                resp = await client.post(f"{cfg.base_url}/payments/{pid}/capture", json=body)
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "capture_payment"
                return data

            if operation == "refund_payment":
                pid = payload["payment_id"]
                body = {}
                if payload.get("refund_amount_paise"):
                    body["amount"] = payload["refund_amount_paise"]
                resp = await client.post(f"{cfg.base_url}/payments/{pid}/refund", json=body)
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "refund_payment"
                return data

            if operation == "verify_signature":
                generated = hmac.new(
                    cfg.webhook_secret.get_secret_value().encode(),
                    f"{payload['order_id']}|{payload['payment_id']}".encode(),
                    hashlib.sha256,
                ).hexdigest()
                is_valid = hmac.compare_digest(generated, str(payload["razorpay_signature"]))
                return {
                    "_operation": "verify_signature",
                    "valid": is_valid,
                    "payment_id": payload["payment_id"],
                    "order_id": payload["order_id"],
                }

            if operation == "fetch_settlement":
                sid = payload["settlement_id"]
                resp = await client.get(f"{cfg.base_url}/settlements/{sid}")
                resp.raise_for_status()
                data = resp.json()
                data["_operation"] = "fetch_settlement"
                return data

        raise ValueError(f"Unknown operation {operation!r}")

    @staticmethod
    def _sandbox_response(payload: AdapterPayload) -> dict[str, Any]:
        import time
        operation = str(payload.get("operation", "create_order"))
        ts = int(time.time())

        if operation == "create_order":
            return {
                "_operation": "create_order",
                "id": "order_SBXTestOrder0001",
                "amount": payload.get("amount_paise", 100000),
                "currency": "INR",
                "status": "created",
                "receipt": payload.get("receipt", "rcpt_001"),
                "attempts": 0,
                "created_at": ts,
            }
        if operation == "capture_payment":
            return {
                "_operation": "capture_payment",
                "id": payload.get("payment_id", "pay_SBXTestPay00001"),
                "order_id": "order_SBXTestOrder0001",
                "amount": 100000,
                "status": "captured",
                "method": "upi",
                "vpa": "sandbox@upi",
                "created_at": ts,
            }
        if operation == "refund_payment":
            return {
                "_operation": "refund_payment",
                "id": "rfnd_SBXTestRefund001",
                "payment_id": payload.get("payment_id", "pay_SBXTestPay00001"),
                "amount": payload.get("refund_amount_paise", 100000),
                "status": "processed",
                "speed_processed": "normal",
                "created_at": ts,
            }
        if operation == "verify_signature":
            return {
                "_operation": "verify_signature",
                "valid": True,
                "payment_id": payload.get("payment_id"),
                "order_id": payload.get("order_id"),
            }
        # fetch_settlement
        return {
            "_operation": "fetch_settlement",
            "id": payload.get("settlement_id", "setl_SBXTestSetl0001"),
            "entity": "settlement",
            "amount": 500000,
            "status": "processed",
            "fees": 1800,
            "tax": 324,
            "utr": "NEFT2025030100001",
            "created_at": ts,
        }
