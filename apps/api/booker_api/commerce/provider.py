"""Provider boundary: authenticated events, exact RUB amounts, no implicit success."""

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from booker_api.config import settings


class ProviderUnavailable(Exception):
    pass


class InvalidWebhook(Exception):
    pass


@dataclass(frozen=True)
class Checkout:
    reference: str
    status: str = "pending_payment"
    url: str | None = None
    subscription_reference: str | None = None


class ProviderEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event_id: str = Field(min_length=1, max_length=128)
    order_id: str = Field(min_length=1, max_length=36)
    reference: str = Field(min_length=1, max_length=128)
    status: Literal["paid", "failed", "refunded"]
    amount_rub: int = Field(gt=0)
    currency: Literal["RUB"]
    paid_at: AwareDatetime | None = None


class RenewalEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    event_id: str = Field(min_length=1, max_length=128)
    initial_order_id: str = Field(min_length=1, max_length=36)
    subscription_reference: str = Field(min_length=1, max_length=128)
    reference: str = Field(min_length=1, max_length=128)
    cycle_number: int = Field(ge=1, le=1200)
    period_start: AwareDatetime
    period_end: AwareDatetime
    occurred_at: AwareDatetime
    status: Literal['paid', 'failed']
    amount_rub: int = Field(gt=0)
    currency: Literal['RUB']


class CommerceProvider(Protocol):
    name: str
    test_mode: bool

    def create_checkout(
        self, *, order_id: str, amount_rub: int, currency: str, idempotency_key: str
    ) -> Checkout: ...
    def get_payment_status(self, reference: str) -> str: ...
    def verify_webhook(self, payload: bytes, signature: str) -> ProviderEvent: ...
    def verify_renewal_webhook(self, payload: bytes, signature: str) -> RenewalEvent: ...
    def refund(self, *, reference: str, amount_rub: int, idempotency_key: str) -> str: ...
    def create_subscription(
        self,
        *,
        order_id: str,
        amount_rub: int,
        currency: str,
        billing_period: str,
        idempotency_key: str,
    ) -> Checkout: ...
    def cancel_subscription(self, reference: str) -> None: ...


class DisabledProvider:
    name = "disabled"
    test_mode = False

    def _unavailable(self):
        raise ProviderUnavailable("Онлайн-оплата пока недоступна")

    def create_checkout(self, **kwargs) -> Checkout:
        return self._unavailable()

    def get_payment_status(self, reference: str) -> str:
        return self._unavailable()

    def verify_webhook(self, payload: bytes, signature: str) -> ProviderEvent:
        return self._unavailable()

    def verify_renewal_webhook(self, payload: bytes, signature: str) -> RenewalEvent:
        return self._unavailable()

    def refund(self, **kwargs) -> str:
        return self._unavailable()

    def create_subscription(self, **kwargs) -> Checkout:
        return self._unavailable()

    def cancel_subscription(self, reference: str) -> None:
        self._unavailable()


def stub_enabled() -> bool:
    return (
        settings.environment in {"dev", "test"}
        and settings.commerce_allow_stub
        and settings.commerce_provider == "stub"
        and len(settings.commerce_webhook_secret) >= 32
    )


class StubProvider:
    name = "stub"
    test_mode = True

    def __init__(self):
        if not stub_enabled():
            raise ProviderUnavailable("Тестовая оплата выключена")

    def create_checkout(
        self, *, order_id: str, amount_rub: int, currency: str, idempotency_key: str
    ) -> Checkout:
        return Checkout(reference=f"stub:{order_id}")

    def get_payment_status(self, reference: str) -> str:
        # No external money exists. Only an explicit signed test event can settle an order.
        return "pending_payment"

    def verify_webhook(self, payload: bytes, signature: str) -> ProviderEvent:
        expected = hmac.new(
            settings.commerce_webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise InvalidWebhook("Неверная подпись уведомления")
        try:
            return ProviderEvent.model_validate_json(payload)
        except ValidationError as exc:
            raise InvalidWebhook("Некорректное уведомление провайдера") from exc

    def verify_renewal_webhook(self, payload: bytes, signature: str) -> RenewalEvent:
        expected = hmac.new(settings.commerce_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected.encode(), signature.encode()):
            raise InvalidWebhook('Неверная подпись уведомления')
        try:
            return RenewalEvent.model_validate_json(payload)
        except ValidationError:
            raise InvalidWebhook('Некорректное уведомление продления') from None

    def refund(self, *, reference: str, amount_rub: int, idempotency_key: str) -> str:
        return "pending"  # Settlement still requires an authenticated refunded event.

    def create_subscription(
        self,
        *,
        order_id: str,
        amount_rub: int,
        currency: str,
        billing_period: str,
        idempotency_key: str,
    ) -> Checkout:
        return Checkout(reference=f"stub:{order_id}", subscription_reference=f"sub:{order_id}")

    def cancel_subscription(self, reference: str) -> None:
        return None


_live_providers: dict[str, Callable[[], CommerceProvider]] = {}


def register_commerce_provider(name: str, factory: Callable[[], CommerceProvider]) -> None:
    """Code-only registration of a reviewed provider; no dynamic env imports."""
    from booker_api.payment_activation import validate_provider_name
    validate_provider_name(name)
    if not callable(factory) or (name in _live_providers and _live_providers[name] is not factory):
        raise ValueError("Provider registration must be callable and unique")
    _live_providers[name] = factory


def get_provider() -> CommerceProvider:
    if stub_enabled():
        return StubProvider()
    from booker_api.payment_activation import live_configuration_ready
    name = settings.commerce_provider.strip().lower()
    if name in _live_providers and live_configuration_ready(commerce=True):
        try:
            provider = _live_providers[name]()
            if provider.name != name or provider.test_mode:
                raise ValueError("Provider identity mismatch")
            return provider
        except Exception:  # noqa: BLE001 - Never expose provider constructor credentials.
            return DisabledProvider()
    return DisabledProvider()


def signed_test_event(
    order_id: str, reference: str, amount_rub: int, status: str, event_id: str
) -> tuple[bytes, str]:
    if not stub_enabled():
        raise ProviderUnavailable("Тестовая оплата выключена")
    payload = json.dumps(
        {
            "event_id": event_id,
            "order_id": order_id,
            "reference": reference,
            "status": status,
            "amount_rub": amount_rub,
            "currency": "RUB",
        },
        sort_keys=True,
    ).encode()
    signature = hmac.new(
        settings.commerce_webhook_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return payload, signature
