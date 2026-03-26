"""Comprehensive unit tests for PII masking across Indian financial data patterns."""

from finspark.core.security import mask_pii


class TestAadhaarMasking:
    """Aadhaar number masking (12-digit format with optional spaces/dashes)."""

    def test_aadhaar_with_spaces(self) -> None:
        text = "Aadhaar: 1234 5678 9012"
        masked = mask_pii(text)
        assert "1234 5678 9012" not in masked
        assert "1234" not in masked
        assert "9012" not in masked
        assert "XXXX" in masked

    def test_aadhaar_with_dashes(self) -> None:
        text = "Aadhaar number is 1234-5678-9012"
        masked = mask_pii(text)
        assert "1234-5678-9012" not in masked

    def test_aadhaar_without_separators(self) -> None:
        text = "aadhaar: 123456789012"
        masked = mask_pii(text)
        assert "123456789012" not in masked

    def test_multiple_aadhaar_numbers(self) -> None:
        text = "Primary: 1111 2222 3333, Secondary: 4444 5555 6666"
        masked = mask_pii(text)
        assert "1111 2222 3333" not in masked
        assert "4444 5555 6666" not in masked


class TestPANMasking:
    """PAN card masking (AAAAA9999A format)."""

    def test_pan_standard_format(self) -> None:
        text = "PAN: ABCDE1234F"
        masked = mask_pii(text)
        assert "ABCDE1234F" not in masked

    def test_pan_in_sentence(self) -> None:
        text = "The applicant's PAN number is ZYXWV9876A and it is verified."
        masked = mask_pii(text)
        assert "ZYXWV9876A" not in masked
        assert "applicant" in masked  # surrounding text preserved

    def test_multiple_pan_numbers(self) -> None:
        text = "PAN1: ABCDE1234F, PAN2: FGHIJ5678K"
        masked = mask_pii(text)
        assert "ABCDE1234F" not in masked
        assert "FGHIJ5678K" not in masked

    def test_pan_not_partial_match(self) -> None:
        """Lowercase or malformed PAN should not be masked."""
        text = "abcde1234f is not a valid PAN"
        masked = mask_pii(text)
        assert masked == text


class TestPhoneMasking:
    """Indian phone number masking."""

    def test_phone_with_country_code_space(self) -> None:
        text = "Phone: +91 9876543210"
        masked = mask_pii(text)
        assert "9876543210" not in masked

    def test_phone_with_country_code_no_space(self) -> None:
        text = "Call +919876543210"
        masked = mask_pii(text)
        assert "9876543210" not in masked

    def test_phone_without_country_code(self) -> None:
        text = "Mobile: 9876543210"
        masked = mask_pii(text)
        assert "9876543210" not in masked

    def test_multiple_phone_numbers(self) -> None:
        text = "Primary: +91 9876543210, Alt: 8765432109"
        masked = mask_pii(text)
        assert "9876543210" not in masked
        assert "8765432109" not in masked


class TestEmailMasking:
    """Email address masking."""

    def test_simple_email(self) -> None:
        text = "Email: test@example.com"
        masked = mask_pii(text)
        assert "test@example.com" not in masked
        assert "***@***.***" in masked

    def test_email_with_dots_and_plus(self) -> None:
        text = "Contact: user.name+tag@company.co.in"
        masked = mask_pii(text)
        assert "user.name+tag@company.co.in" not in masked

    def test_multiple_emails(self) -> None:
        text = "From: a@b.com, To: c@d.org"
        masked = mask_pii(text)
        assert "a@b.com" not in masked
        assert "c@d.org" not in masked


class TestNonPIIPreservation:
    """Non-PII text should pass through unchanged."""

    def test_plain_text_unchanged(self) -> None:
        text = "This is a normal text with no PII"
        assert mask_pii(text) == text

    def test_empty_string(self) -> None:
        assert mask_pii("") == ""

    def test_financial_terms_preserved(self) -> None:
        text = "The loan amount is INR 5,00,000 at 8.5% interest rate for 36 months"
        masked = mask_pii(text)
        assert "loan amount" in masked
        assert "8.5%" in masked
        assert "36 months" in masked

    def test_short_numbers_not_masked_as_aadhaar(self) -> None:
        """Numbers shorter than 12 digits should not trigger Aadhaar masking."""
        text = "Order ID: 12345"
        masked = mask_pii(text)
        assert "12345" in masked


class TestMixedPII:
    """Text containing multiple PII types simultaneously."""

    def test_all_pii_types_masked(self) -> None:
        text = (
            "Customer: Aadhaar 1234 5678 9012, PAN ABCDE1234F, "
            "Phone +91 9876543210, Email user@test.com"
        )
        masked = mask_pii(text)
        assert "1234 5678 9012" not in masked
        assert "ABCDE1234F" not in masked
        assert "9876543210" not in masked
        assert "user@test.com" not in masked
        # Context words survive
        assert "Customer" in masked

    def test_masked_output_does_not_contain_originals(self) -> None:
        """Ensure the masked output truly removes all original PII values."""
        originals = [
            "1234 5678 9012",
            "ABCDE1234F",
            "9876543210",
            "secret@mail.com",
        ]
        text = f"Aadhaar: {originals[0]}, PAN: {originals[1]}, Phone: +91 {originals[2]}, Email: {originals[3]}"
        masked = mask_pii(text)
        for original in originals:
            assert original not in masked, f"Original PII '{original}' leaked through masking"
