"""Authenticated encryption for TOTP secrets stored in the Booker database."""

from __future__ import annotations

import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from booker_api.config import settings

_PREFIX = "fernet:v1:"
_LOCAL_TEST_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(b"booker-local-test-only-totp-storage-v1").digest()
)


def _cipher() -> MultiFernet:
    configured = settings.totp_encryption_keys.strip()
    try:
        if configured:
            key_values = [key.strip().encode("ascii") for key in configured.split(",")]
        elif settings.runtime_env in {"local", "test"}:
            key_values = [_LOCAL_TEST_KEY]
        else:
            raise RuntimeError("TOTP encryption key is not configured")
        if not key_values or any(not key for key in key_values):
            raise ValueError("empty TOTP key")
        return MultiFernet([Fernet(key) for key in key_values])
    except (TypeError, ValueError, UnicodeError):
        raise RuntimeError("TOTP encryption key configuration is invalid") from None


def encrypt_totp_secret(secret: str) -> str:
    """Encrypt a Base32 secret. Only local/test may use the fixed test key."""
    if (not isinstance(secret, str) or len(secret) % 8 != 0
            or not re.fullmatch(r"[A-Z2-7]{16,64}", secret)):
        raise ValueError("TOTP secret must be unencrypted Base32")
    return _PREFIX + _cipher().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(stored: str) -> str:
    """Reject legacy/plaintext and tampered rows; a migration must scrub them first."""
    if not isinstance(stored, str) or not stored.startswith(_PREFIX):
        raise RuntimeError("TOTP secret storage requires migration")
    try:
        return _cipher().decrypt(stored[len(_PREFIX):].encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeError, ValueError):
        raise RuntimeError("TOTP secret storage is unreadable") from None


class EncryptedTotpSecret(TypeDecorator[str]):
    """Keep ORM callers compatible while encrypting every database bind."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        return None if value is None else encrypt_totp_secret(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        return None if value is None else decrypt_totp_secret(value)
