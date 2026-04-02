"""Tests for adapter-specific mock API response generators."""

from finspark.services.simulation.mock_responses import generate_mock_response


class TestCIBILMockResponses:
    def test_credit_score_endpoint(self) -> None:
        response = generate_mock_response(
            adapter_name="CIBIL Credit Bureau",
            endpoint_path="/credit-score",
            request_payload={"pan_number": "ABCDE1234F", "full_name": "Rajesh Kumar"},
        )
        assert "credit_score" in response
        assert 300 <= response["credit_score"] <= 899
        assert response["score_version"] == "CIBIL_V3"
        assert "account_summary" in response
        assert "enquiry_summary" in response
        assert "control_number" in response
        assert response["control_number"].startswith("CIBIL")

    def test_credit_report_endpoint(self) -> None:
        response = generate_mock_response(
            adapter_name="CIBIL Credit Bureau",
            endpoint_path="/credit-report",
            request_payload={"pan_number": "ABCDE1234F"},
        )
        assert "credit_score" in response
        assert "report_id" in response
        assert "accounts" in response
        assert isinstance(response["accounts"], list)
        assert len(response["accounts"]) > 0

    def test_deterministic_responses(self) -> None:
        """Same PAN should always produce the same score."""
        r1 = generate_mock_response(
            adapter_name="CIBIL Credit Bureau",
            endpoint_path="/credit-score",
            request_payload={"pan_number": "XYZAB9876C"},
        )
        r2 = generate_mock_response(
            adapter_name="CIBIL Credit Bureau",
            endpoint_path="/credit-score",
            request_payload={"pan_number": "XYZAB9876C"},
        )
        assert r1["credit_score"] == r2["credit_score"]

    def test_different_pan_different_score(self) -> None:
        r1 = generate_mock_response(
            adapter_name="CIBIL Credit Bureau",
            endpoint_path="/credit-score",
            request_payload={"pan_number": "ABCDE1234F"},
        )
        r2 = generate_mock_response(
            adapter_name="CIBIL Credit Bureau",
            endpoint_path="/credit-score",
            request_payload={"pan_number": "ZZZZZ9999Z"},
        )
        assert r1["credit_score"] != r2["credit_score"]

    def test_bulk_inquiry_endpoint(self) -> None:
        response = generate_mock_response(
            adapter_name="CIBIL Credit Bureau",
            endpoint_path="/bulk-inquiry",
            request_payload={"pan_number": "ABCDE1234F"},
        )
        assert "batch_id" in response
        assert "results" in response
        assert response["status"] == "completed"


class TestKYCMockResponses:
    def test_aadhaar_verification(self) -> None:
        response = generate_mock_response(
            adapter_name="Aadhaar eKYC Provider",
            endpoint_path="/verify/aadhaar",
            request_payload={"aadhaar_number": "234100000001", "customer_name": "Rajesh Kumar"},
        )
        assert response["verification_status"] == "verified"
        assert "name" in response
        assert "address" in response
        assert "city" in response["address"]
        assert "reference_id" in response
        assert response["reference_id"].startswith("KYC")

    def test_pan_verification(self) -> None:
        response = generate_mock_response(
            adapter_name="Aadhaar eKYC Provider",
            endpoint_path="/verify/pan",
            request_payload={"pan_number": "ABCDE1234F", "customer_name": "Rajesh Kumar"},
        )
        assert response["verification_status"] == "verified"
        assert response["pan_status"] == "VALID"
        assert "name_on_pan" in response

    def test_digilocker_fetch(self) -> None:
        response = generate_mock_response(
            adapter_name="Aadhaar eKYC Provider",
            endpoint_path="/digilocker/fetch",
            request_payload={"aadhaar_number": "234100000001"},
        )
        assert "document_type" in response
        assert "document_number" in response
        assert "consent_artefact_id" in response


class TestGSTMockResponses:
    def test_gstin_verification(self) -> None:
        response = generate_mock_response(
            adapter_name="GST Verification Service",
            endpoint_path="/verify/gstin",
            request_payload={"gstin": "29ABCDE1234F1ZK"},
        )
        assert "legal_name" in response
        assert "registration_date" in response
        assert response["gstin"] == "29ABCDE1234F1ZK"
        assert response["taxpayer_type"] == "Regular"
        assert response["status"] == "Active"

    def test_returns_status(self) -> None:
        response = generate_mock_response(
            adapter_name="GST Verification Service",
            endpoint_path="/returns/status",
            request_payload={"gstin": "29ABCDE1234F1ZK", "financial_year": "2024-25"},
        )
        assert "filings" in response
        assert isinstance(response["filings"], list)
        assert len(response["filings"]) > 0
        assert "period" in response["filings"][0]

    def test_taxpayer_profile(self) -> None:
        response = generate_mock_response(
            adapter_name="GST Verification Service",
            endpoint_path="/profile",
            request_payload={"gstin": "29ABCDE1234F1ZK"},
        )
        assert "legal_name" in response
        assert "trade_name" in response
        assert "constitution" in response


class TestPaymentMockResponses:
    def test_create_payment(self) -> None:
        response = generate_mock_response(
            adapter_name="Payment Gateway",
            endpoint_path="/payments/create",
            request_payload={"amount": 500000, "reference_id": "REF001"},
        )
        assert response["status"] == "success"
        assert response["order_id"].startswith("order_")
        assert response["payment_id"].startswith("pay_")
        assert "amount" in response
        assert "currency" in response

    def test_get_payment_status(self) -> None:
        response = generate_mock_response(
            adapter_name="Payment Gateway",
            endpoint_path="/payments/{id}",
            request_payload={"reference_id": "REF001"},
        )
        assert response["payment_status"] == "captured"
        assert response["method"] == "upi"

    def test_create_transfer(self) -> None:
        response = generate_mock_response(
            adapter_name="Payment Gateway",
            endpoint_path="/transfers/create",
            request_payload={
                "account_number": "1234567890",
                "ifsc_code": "SBIN0001234",
                "amount": 100000,
            },
        )
        assert response["transfer_id"].startswith("trf_")
        assert response["utr_number"].startswith("NEFT")
        assert response["transfer_status"] == "processed"

    def test_create_refund(self) -> None:
        response = generate_mock_response(
            adapter_name="Payment Gateway",
            endpoint_path="/refunds/create",
            request_payload={"reference_id": "pay_001", "amount": 100000},
        )
        assert response["refund_id"].startswith("rfnd_")
        assert response["refund_status"] == "processed"


class TestFraudMockResponses:
    def test_fraud_score(self) -> None:
        response = generate_mock_response(
            adapter_name="Fraud Detection Engine",
            endpoint_path="/score",
            request_payload={"customer_id": "CUST001", "transaction_amount": 50000},
        )
        assert 0 <= response["fraud_score"] <= 1.0
        assert response["risk_level"] in ("low", "medium", "high")
        assert response["recommendation"] in ("approve", "review")
        assert "risk_factors" in response
        assert len(response["risk_factors"]) > 0
        assert response["reference_id"].startswith("FRD")

    def test_device_verification(self) -> None:
        response = generate_mock_response(
            adapter_name="Fraud Detection Engine",
            endpoint_path="/verify/device",
            request_payload={"customer_id": "CUST001", "device_id": "DEV001"},
        )
        assert "device_trust_score" in response
        assert "device_fingerprint" in response
        assert isinstance(response["known_device"], bool)
        assert response["reference_id"].startswith("DVC")

    def test_velocity_check(self) -> None:
        response = generate_mock_response(
            adapter_name="Fraud Detection Engine",
            endpoint_path="/verify/velocity",
            request_payload={"customer_id": "CUST001"},
        )
        assert response["velocity_check"] in ("pass", "fail")
        assert "transactions_24h" in response
        assert "amount_24h" in response
        assert response["reference_id"].startswith("VEL")


class TestSMSMockResponses:
    def test_send_sms(self) -> None:
        response = generate_mock_response(
            adapter_name="SMS Gateway",
            endpoint_path="/send",
            request_payload={"mobile_number": "9876543210", "message": "Test"},
        )
        assert response["message_id"].startswith("MSG")
        assert response["delivery_status"] == "ACCEPTED"
        assert response["credits_used"] == 1

    def test_check_delivery_status(self) -> None:
        response = generate_mock_response(
            adapter_name="SMS Gateway",
            endpoint_path="/status/{id}",
            request_payload={"mobile_number": "9876543210", "message_id": "MSG001"},
        )
        assert response["delivery_status"] == "DELIVERED"
        assert response["operator"] in ("Jio", "Airtel", "Vi", "BSNL")

    def test_list_templates(self) -> None:
        response = generate_mock_response(
            adapter_name="SMS Gateway",
            endpoint_path="/templates",
            request_payload={},
        )
        assert "templates" in response
        assert len(response["templates"]) >= 3


class TestAccountAggregatorMockResponses:
    def test_create_consent(self) -> None:
        response = generate_mock_response(
            adapter_name="Account Aggregator (AA Framework)",
            endpoint_path="/consent/create",
            request_payload={"customer_vua": "user@aa-provider", "fi_types": ["DEPOSIT"]},
        )
        assert response["consent_handle"].startswith("CNS")
        assert response["consent_status"] == "PENDING"
        assert "redirect_url" in response

    def test_check_consent_status(self) -> None:
        response = generate_mock_response(
            adapter_name="Account Aggregator (AA Framework)",
            endpoint_path="/consent/{id}/status",
            request_payload={"customer_vua": "user@aa-provider"},
        )
        assert response["consent_status"] == "APPROVED"

    def test_fetch_fi_data(self) -> None:
        response = generate_mock_response(
            adapter_name="Account Aggregator (AA Framework)",
            endpoint_path="/fi/{session_id}",
            request_payload={"customer_vua": "user@aa-provider"},
        )
        assert "fi_data" in response
        assert len(response["fi_data"]) == 2
        assert response["fi_data"][0]["fip_id"] == "FIP_SBI"
        assert "accounts" in response["fi_data"][0]
        assert "balance" in response["fi_data"][0]["accounts"][0]

    def test_fi_fetch_initiation(self) -> None:
        response = generate_mock_response(
            adapter_name="Account Aggregator (AA Framework)",
            endpoint_path="/fi/fetch",
            request_payload={"customer_vua": "user@aa-provider"},
        )
        assert response["fi_data_ready"] is True
        assert response["session_id"].startswith("SES")


class TestEmailMockResponses:
    def test_send_email(self) -> None:
        response = generate_mock_response(
            adapter_name="Email Notification Gateway",
            endpoint_path="/send",
            request_payload={"to": "test@example.com", "subject": "Test", "body": "Hello"},
        )
        assert response["email_id"].startswith("EML")
        assert response["delivery_status"] == "ACCEPTED"

    def test_check_email_status(self) -> None:
        response = generate_mock_response(
            adapter_name="Email Notification Gateway",
            endpoint_path="/status/{id}",
            request_payload={"to": "test@example.com"},
        )
        assert response["delivery_status"] == "DELIVERED"
        assert isinstance(response["bounced"], bool)

    def test_list_email_templates(self) -> None:
        response = generate_mock_response(
            adapter_name="Email Notification Gateway",
            endpoint_path="/templates",
            request_payload={},
        )
        assert "templates" in response
        assert len(response["templates"]) >= 4


class TestBaseURLFallback:
    def test_cibil_by_url(self) -> None:
        response = generate_mock_response(
            adapter_name="some-uuid",
            endpoint_path="/credit-score",
            request_payload={"pan_number": "ABCDE1234F"},
            base_url="https://api.cibil.com/v1",
        )
        assert "credit_score" in response
        assert 300 <= response["credit_score"] <= 899

    def test_kyc_by_url(self) -> None:
        response = generate_mock_response(
            adapter_name="some-uuid",
            endpoint_path="/verify/aadhaar",
            request_payload={"aadhaar_number": "234100000001"},
            base_url="https://api.ekyc-provider.com/v1",
        )
        assert response["verification_status"] == "verified"

    def test_gst_by_url(self) -> None:
        response = generate_mock_response(
            adapter_name="some-uuid",
            endpoint_path="/verify/gstin",
            request_payload={"gstin": "29ABCDE1234F1ZK"},
            base_url="https://api.gst-verify.com/v1",
        )
        assert response["taxpayer_type"] == "Regular"

    def test_payment_by_url(self) -> None:
        response = generate_mock_response(
            adapter_name="some-uuid",
            endpoint_path="/payments/create",
            request_payload={"amount": 500000, "reference_id": "REF001"},
            base_url="https://api.payment-gateway.com/v1",
        )
        assert response["order_id"].startswith("order_")

    def test_fraud_by_url(self) -> None:
        response = generate_mock_response(
            adapter_name="some-uuid",
            endpoint_path="/score",
            request_payload={"customer_id": "CUST001"},
            base_url="https://api.fraud-detect.com/v1",
        )
        assert "fraud_score" in response

    def test_sms_by_url(self) -> None:
        response = generate_mock_response(
            adapter_name="some-uuid",
            endpoint_path="/send",
            request_payload={"mobile_number": "9876543210"},
            base_url="https://api.sms-gateway.com/v1",
        )
        assert response["message_id"].startswith("MSG")

    def test_aa_by_url(self) -> None:
        response = generate_mock_response(
            adapter_name="some-uuid",
            endpoint_path="/consent/create",
            request_payload={"customer_vua": "user@aa"},
            base_url="https://api.account-aggregator.com/v1",
        )
        assert response["consent_handle"].startswith("CNS")

    def test_email_by_url(self) -> None:
        response = generate_mock_response(
            adapter_name="some-uuid",
            endpoint_path="/send",
            request_payload={"to": "test@example.com"},
            base_url="https://api.email-gateway.com/v1",
        )
        assert response["email_id"].startswith("EML")


class TestUnknownAdapter:
    def test_unknown_adapter_returns_default(self) -> None:
        response = generate_mock_response(
            adapter_name="Unknown Service",
            endpoint_path="/anything",
            request_payload={},
        )
        assert response["status"] == "success"
        assert response["adapter"] == "Unknown Service"
