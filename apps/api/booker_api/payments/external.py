from __future__ import annotations

from booker_api.payments.adapter import (
    PaymentAdapter,
    PaymentAdapterError,
    PaymentSession,
    RefundOutcome,
    WebhookEvent,
)


class ExternalPaymentAdapter(PaymentAdapter):
    """Off-platform transfer: pending until concierge/admin confirms (audit)."""

    name = "external"

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
            checkout_url=None,
            provider_reference=f"external-{payment_id}",
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
        # External mode does not accept partner webhooks; admin confirm uses internal path.
        raise PaymentAdapterError("External-payment не принимает webhook партнёра")

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
        raise PaymentAdapterError("Внешний перевод возвращают стороны вне Букера; автоматический возврат недоступен")
