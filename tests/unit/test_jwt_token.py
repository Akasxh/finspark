"""Tests for JWT token creation and decoding using PyJWT."""

import pytest

from finspark.core.security import create_jwt_token, decode_jwt_token


class TestJWTRoundtrip:
    def test_create_and_decode_token(self) -> None:
        data = {"tenant_id": "t-123", "role": "admin"}
        token = create_jwt_token(data)
        decoded = decode_jwt_token(token)
        assert decoded["tenant_id"] == "t-123"
        assert decoded["role"] == "admin"
        assert "exp" in decoded

    def test_decode_invalid_token_raises(self) -> None:
        with pytest.raises(Exception):
            decode_jwt_token("invalid.token.value")

    def test_token_contains_expiry(self) -> None:
        token = create_jwt_token({"sub": "user1"})
        decoded = decode_jwt_token(token)
        assert isinstance(decoded["exp"], int)
        assert decoded["exp"] > 0
