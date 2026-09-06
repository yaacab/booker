from __future__ import annotations

from booker_api.payments.adapter import (
    PaymentAdapter,
    PaymentAdapterUnavailable,
    PaymentSession,
    RefundOutcome,
    WebhookEvent,
)


class LivePaymentAdapter(PaymentAdapter):
    """Fail-closed placeholder until payment partner integration (AUTO-017)."""

    name = "live"

    def _disabled(self) -> None:
        raise PaymentAdapterUnavailable(
            "Live payment adapter disabled until partner credentials and legal gate"
        )

    def create_session(
        self,
        *,
        payment_id: str,
        amount_rub: int,
        idempotency_key: str,
        booking_id: str,
    ) -> PaymentSession:
        self._disabled()
        raise AssertionError("unreachable")

    def verify_webhook(
        self,
        *,
        event_id: str,
        payment_id: str,
        status: str,
        signature: str,
    ) -> WebhookEvent:
        self._disabled()
        raise AssertionError("unreachable")

    def normalize_idempotency_key(self, key: str) -> str:
        self._disabled()
        raise AssertionError("unreachable")

    def refund(
        self,
        *,
        payment_id: str,
        amount_rub: int,
        total_rub: int,
        idempotency_key: str | None = None,
    ) -> RefundOutcome:
        self._disabled()
        raise AssertionError("unreachable")
