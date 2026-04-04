"""JWT creation/verification and password hashing."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import PyJWTError as JWTError
from passlib.context import CryptContext

from finspark.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Passwords ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT ────────────────────────────────────────────────────────────────────────

def create_access_token(subject: str | int, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | int) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on failure."""
    return jwt.decode(token, settings.APP_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "JWTError",
]
