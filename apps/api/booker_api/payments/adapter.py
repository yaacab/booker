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


def payment_stub_enabled() -> bool:
    return (
        settings.environment.strip().lower() in {"dev", "development", "test"}
        and settings.payment_allow_stub
        and settings.payment_provider.strip().lower() == "stub"
    )


def payment_live_enabled() -> bool:
    # No live implementation is registered yet. Credentials alone cannot enable it.
    return False


def payment_capabilities() -> dict:
    stub = payment_stub_enabled()
    external = settings.payment_provider.strip().lower() == "external"
    return {
        "available": stub or external or payment_live_enabled(),
        "test_mode": stub,
        "message": (
            "Тестовая оплата: деньги не списываются" if stub else
            "Перевод вне платформы подтверждает оператор" if external else
            "Оплата пока недоступна: платёжный партнёр не подключён"
        ),
    }


def get_payment_adapter() -> PaymentAdapter:
    from booker_api.payments.external import ExternalPaymentAdapter
    from booker_api.payments.stub import StubPaymentAdapter

    provider = settings.payment_provider.strip().lower()
    if payment_stub_enabled():
        return StubPaymentAdapter()
    if provider == "external":
        return ExternalPaymentAdapter()
    raise HTTPException(503, "Оплата пока недоступна: платёжный партнёр не подключён")
