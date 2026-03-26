"""Unit tests for security utilities."""

import pytest

from finspark.core.security import decrypt_value, encrypt_value, hash_value, mask_pii


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        plaintext = "my-secret-api-key-12345"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertexts(self) -> None:
        plaintext = "same-value"
        e1 = encrypt_value(plaintext)
        e2 = encrypt_value(plaintext)
        # Fernet uses random IV, so ciphertexts differ
        assert e1 != e2

    def test_decrypt_wrong_ciphertext_fails(self) -> None:
        with pytest.raises(Exception):
            decrypt_value("not-a-valid-ciphertext")


class TestPIIMasking:
    def test_mask_aadhaar(self) -> None:
        text = "Aadhaar: 1234 5678 9012"
        masked = mask_pii(text)
        assert "1234 5678 9012" not in masked
        assert "XXXX" in masked

    def test_mask_pan(self) -> None:
        text = "PAN: ABCDE1234F"
        masked = mask_pii(text)
        assert "ABCDE1234F" not in masked

    def test_mask_phone(self) -> None:
        text = "Phone: +91 9876543210"
        masked = mask_pii(text)
        assert "9876543210" not in masked

    def test_mask_email(self) -> None:
        text = "Email: test@example.com"
        masked = mask_pii(text)
        assert "test@example.com" not in masked

    def test_no_pii_unchanged(self) -> None:
        text = "This is a normal text with no PII"
        masked = mask_pii(text)
        assert masked == text


class TestHashing:
    def test_hash_deterministic(self) -> None:
        assert hash_value("test") == hash_value("test")

    def test_hash_different_inputs(self) -> None:
        assert hash_value("a") != hash_value("b")

    def test_hash_returns_hex_string(self) -> None:
        result = hash_value("test")
        assert len(result) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in result)
