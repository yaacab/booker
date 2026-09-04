from __future__ import annotations

import hashlib
import hmac
import secrets

from booker_api.config import settings
from booker_api.payments.adapter import (
    PaymentAdapter,
    PaymentAdapterError,
    PaymentSession,
    RefundOutcome,
    WebhookEvent,
)

_WEBHOOK_STATUSES = frozenset({"succeeded", "failed"})


class StubPaymentAdapter(PaymentAdapter):
    name = "stub"

    def create_session(
        self,
        *,
        payment_id: str,
        amount_rub: int,
        idempotency_key: str,
        booking_id: str,
    ) -> PaymentSession:
        self.normalize_idempotency_key(idempotency_key)
        session = PaymentSession(
            provider=self.name,
            payment_id=payment_id,
            status="pending",
            provider_reference=f"stub-{payment_id}",
        )
        self.ledger.on_session_created(payment_id, amount_rub)
        return session

    def verify_webhook(
        self,
        *,
        event_id: str,
        payment_id: str,
        status: str,
        signature: str,
    ) -> WebhookEvent:
        if status not in _WEBHOOK_STATUSES:
            raise PaymentAdapterError(f"status: {'|'.join(sorted(_WEBHOOK_STATUSES))}")
        payload = f"{event_id}:{payment_id}:{status}"
        expected = hmac.new(
            settings.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise PaymentAdapterError("Неверная подпись webhook")
        return WebhookEvent(event_id=event_id, payment_id=payment_id, status=status)

    def normalize_idempotency_key(self, key: str) -> str:
        normalized = key.strip()
        if not normalized:
            raise PaymentAdapterError("idempotency_key обязателен")
        if len(normalized) > 64:
            raise PaymentAdapterError("idempotency_key слишком длинный")
        return normalized

    def refund(
        self,
        *,
        payment_id: str,
        amount_rub: int,
        total_rub: int,
        idempotency_key: str | None = None,
    ) -> RefundOutcome:
        if idempotency_key:
            self.normalize_idempotency_key(idempotency_key)
        if amount_rub <= 0 or amount_rub > total_rub:
            raise PaymentAdapterError("Некорректная сумма возврата")
        kind = "full" if amount_rub == total_rub else "partial"
        refund_id = f"stub-refund-{payment_id}-{secrets.token_hex(4)}"
        self.ledger.on_refund(payment_id, amount_rub, kind)
        return RefundOutcome(
            refund_id=refund_id,
            amount_rub=amount_rub,
            kind=kind,
            status="succeeded",
        )
