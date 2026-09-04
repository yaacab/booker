"""TOTP verification for admin second factor."""

from __future__ import annotations

import pyotp


def verify_totp_code(secret: str | None, code: str | None) -> bool:
    if not secret or not code:
        return False
    normalized = code.strip()
    if not normalized.isdigit() or len(normalized) != 6:
        return False
    try:
        return pyotp.TOTP(secret).verify(normalized, valid_window=1)
    except (TypeError, ValueError):
        return False
