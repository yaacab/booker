from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException

from booker_api.config import settings


class PaymentAdapterError(Exception):
    """Base payment adapter error."""


class PaymentAdapterUnavailable(PaymentAdapterError):
    """Live provider requested but credentials/partner gate not satisfied (fail-closed)."""


@dataclass(frozen=True)
class PaymentSession:
    provider: str
    payment_id: str
    status: str
    checkout_url: str | None = None
    provider_reference: str | None = None


@dataclass(frozen=True)
class WebhookEvent:
    event_id: str
    payment_id: str
    status: str


@dataclass(frozen=True)
class RefundOutcome:
    refund_id: str
    amount_rub: int
    kind: str
    status: str


class LedgerHooks(Protocol):
    def on_session_created(self, payment_id: str, amount_rub: int) -> None: ...

    def on_capture(self, payment_id: str, amount_rub: int) -> None: ...

    def on_refund(self, payment_id: str, amount_rub: int, kind: str) -> None: ...


class NoOpLedgerHooks:
    def on_session_created(self, payment_id: str, amount_rub: int) -> None:
        return None

    def on_capture(self, payment_id: str, amount_rub: int) -> None:
        return None

    def on_refund(self, payment_id: str, amount_rub: int, kind: str) -> None:
        return None


class PaymentAdapter(ABC):
    name: str

    def __init__(self, ledger: LedgerHooks | None = None) -> None:
        self._ledger: LedgerHooks = ledger or NoOpLedgerHooks()

    @property
    def ledger(self) -> LedgerHooks:
        return self._ledger

    @abstractmethod
    def create_session(
        self,
        *,
        payment_id: str,
        amount_rub: int,
        idempotency_key: str,
        booking_id: str,
    ) -> PaymentSession: ...

    @abstractmethod
    def verify_webhook(
        self,
        *,
        event_id: str,
        payment_id: str,
        status: str,
        signature: str,
    ) -> WebhookEvent: ...

    @abstractmethod
    def normalize_idempotency_key(self, key: str) -> str: ...

    @abstractmethod
    def refund(
        self,
        *,
        payment_id: str,
        amount_rub: int,
        total_rub: int,
        idempotency_key: str | None = None,
    ) -> RefundOutcome: ...


def payment_live_enabled() -> bool:
    provider = settings.payment_provider.strip().lower()
    merchant = (settings.payment_merchant_id or "").strip()
    return provider not in {"", "stub", "disabled"} and bool(merchant)


def get_payment_adapter() -> PaymentAdapter:
    from booker_api.payments.live import LivePaymentAdapter
    from booker_api.payments.stub import StubPaymentAdapter

    provider = settings.payment_provider.strip().lower()
    if provider in {"", "stub"}:
        return StubPaymentAdapter()
    if not payment_live_enabled():
        raise HTTPException(
            501,
            "Боевой платёжный партнёр за фичефлагом: нужны BOOKER_PAYMENT_PROVIDER и "
            "BOOKER_PAYMENT_MERCHANT_ID",
        )
    return LivePaymentAdapter()
