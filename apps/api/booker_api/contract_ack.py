"""Technical acknowledgement of an immutable contract draft."""

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from booker_api.models import OfferVersion

EFFECT = "technical_draft_acknowledgement"
LEGAL_PACK_VERSION = "2026-10-01-draft"
TEMPLATE_VERSION = "direct_draft_v2"
OTP_LIFETIME = timedelta(minutes=15)


def render_contract(
    version: OfferVersion,
    *,
    transaction: Mapping[str, object] | None = None,
) -> str:
    try:
        payment_terms = json.dumps(
            json.loads(version.payment_terms_json or "{}"),
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid payment terms") from exc
    transaction_json = json.dumps(
        dict(transaction or {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "Техническое подтверждение черновика условий. Юридическая сила электронной подписи "
        "не утверждена.\n"
        f"Версия шаблона: {TEMPLATE_VERSION}\n"
        f"Редакция юридического пакета: {LEGAL_PACK_VERSION}\n"
        f"quote_id={version.id}\n"
        f"Гонорар: {version.honorarium_rub} RUB\n"
        f"Комиссия: {version.commission_rub} RUB; ставка: {version.commission_rate}\n"
        f"Итого: {version.total_rub} RUB\n"
        f"Аванс: {version.advance_rub} RUB; остаток: {version.balance_rub} RUB; "
        f"обеспечительный платёж: {version.security_deposit_rub} RUB\n"
        f"Валюта: {version.currency}\n"
        f"Предмет и стороны сделки JSON: {transaction_json}\n"
        f"Условия предложения:\n{version.terms}\n"
        f"Условия платежей JSON: {payment_terms}\n"
    )


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def new_challenge() -> tuple[str, str, datetime]:
    code = f"{secrets.randbelow(900000) + 100000}"
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(salt), 200_000).hex()
    return code, f"{salt}${digest}", datetime.now(timezone.utc) + OTP_LIFETIME


def check_challenge(code: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(salt), 200_000)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (TypeError, ValueError):
        return False
