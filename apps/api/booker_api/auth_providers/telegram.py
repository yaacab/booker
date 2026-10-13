"""Verify Telegram Mini App initData before it can identify a Booker user.

Protocol: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
This module does not grant a Booker session or consume a replay key.
"""

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

MAX_INIT_DATA_BYTES = 8192
MAX_AGE_SECONDS = 300
MAX_FUTURE_SKEW_SECONDS = 30
_HASH_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class InvalidTelegramInitData(ValueError):
    """Untrusted, expired or malformed Mini App claim."""


@dataclass(frozen=True)
class TelegramClaim:
    subject: str
    first_name: str
    last_name: str | None
    auth_date: int
    proof_hash: str


def verify_init_data(
    raw: str,
    *,
    bot_token: str,
    now_epoch: int | None = None,
    max_age_seconds: int = MAX_AGE_SECONDS,
) -> TelegramClaim:
    """Validate the signed payload; caller must consume proof_hash once."""
    if not bot_token or max_age_seconds <= 0 or not raw:
        raise InvalidTelegramInitData("Telegram validation is unavailable")
    try:
        encoded = raw.encode("utf-8", errors="strict")
        if len(encoded) > MAX_INIT_DATA_BYTES:
            raise InvalidTelegramInitData("Telegram data is too large")
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True,
                          max_num_fields=32, encoding="utf-8", errors="strict")
    except (UnicodeError, ValueError) as exc:
        raise InvalidTelegramInitData("Malformed Telegram data") from exc
    fields: dict[str, str] = {}
    for key, value in pairs:
        if not key or key in fields:
            raise InvalidTelegramInitData("Duplicate or empty Telegram field")
        fields[key] = value
    supplied_hash = fields.get("hash", "")
    if not _HASH_RE.fullmatch(supplied_hash):
        raise InvalidTelegramInitData("Missing Telegram hash")
    # Bot-token HMAC includes every received field except hash, including
    # signature when present. Only the separate Ed25519 third-party flow
    # excludes both hash and signature from its data-check-string.
    signed_fields = {key: value for key, value in fields.items() if key != "hash"}
    check_string = "\n".join(f"{key}={signed_fields[key]}" for key in sorted(signed_fields))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_hash.lower()):
        raise InvalidTelegramInitData("Invalid Telegram signature")

    timestamp = fields.get("auth_date", "")
    if not timestamp.isascii() or not timestamp.isdecimal():
        raise InvalidTelegramInitData("Invalid Telegram timestamp")
    auth_date = int(timestamp)
    current = int(time.time()) if now_epoch is None else now_epoch
    if auth_date <= 0 or current - auth_date > max_age_seconds or (
        auth_date - current > MAX_FUTURE_SKEW_SECONDS
    ):
        raise InvalidTelegramInitData("Telegram data is expired or from the future")
    try:
        user = json.loads(fields["user"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidTelegramInitData("Missing Telegram user") from exc
    if not isinstance(user, dict):
        raise InvalidTelegramInitData("Invalid Telegram user")
    user_id = user.get("id")
    first_name = user.get("first_name")
    last_name = user.get("last_name")
    if (
        isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0
        or not isinstance(first_name, str) or not first_name.strip()
        or len(first_name) > 255
        or (last_name is not None and (
            not isinstance(last_name, str) or len(last_name) > 255
        ))
    ):
        raise InvalidTelegramInitData("Invalid Telegram user")
    return TelegramClaim(
        subject=str(user_id), first_name=first_name.strip(),
        last_name=last_name.strip() if last_name else None,
        auth_date=auth_date, proof_hash=expected,
    )
