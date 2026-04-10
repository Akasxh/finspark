"""Credential vault abstraction for adapter authentication.

Supports environment-variable-based credential storage for development
and Fernet-encrypted storage for production. Extensible to HashiCorp
Vault or AWS Secrets Manager.
"""

import logging
import os

from finspark.core.security import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)


class CredentialVault:
    """Manages adapter credentials with encryption at rest.

    Storage formats:
    - "vault:encrypted_data" — Fernet-encrypted, decrypted on resolve
    - "env:VAR_NAME" — read from environment variable
    - plain string — returned as-is (backward compat)
    """

    def store(self, credentials: dict[str, str]) -> dict[str, str]:
        """Encrypt credentials, returning vault references (not plaintext)."""
        refs: dict[str, str] = {}
        for key, value in credentials.items():
            if value:
                refs[key] = f"vault:{encrypt_value(value)}"
            else:
                refs[key] = ""
        return refs

    def resolve(self, credential_refs: dict[str, str]) -> dict[str, str]:
        """Resolve credential references back to plaintext values."""
        resolved: dict[str, str] = {}
        for key, ref in credential_refs.items():
            if not ref:
                resolved[key] = ""
            elif ref.startswith("vault:"):
                try:
                    resolved[key] = decrypt_value(ref[6:])
                except Exception:
                    logger.warning("Failed to decrypt credential %s", key)
                    resolved[key] = ""
            elif ref.startswith("env:"):
                resolved[key] = os.environ.get(ref[4:], "")
            else:
                resolved[key] = ref
        return resolved

    def redact(self, credential_refs: dict[str, str]) -> dict[str, str]:
        """Return redacted view of credentials for API responses."""
        return {key: "********" if ref else "" for key, ref in credential_refs.items()}
