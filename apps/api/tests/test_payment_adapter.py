import hashlib
import hmac
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from booker_api.config import settings
from booker_api.payments.adapter import (
    PaymentAdapterError,
    PaymentAdapterUnavailable,
    get_payment_adapter,
    payment_live_enabled,
)
from booker_api.payments.stub import StubPaymentAdapter


def _sign(event_id: str, payment_id: str, status: str) -> str:
    payload = f"{event_id}:{payment_id}:{status}"
    return hmac.new(settings.webhook_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def test_stub_is_default_adapter():
    adapter = get_payment_adapter()
    assert isinstance(adapter, StubPaymentAdapter)
    assert adapter.name == "stub"


def test_payment_live_disabled_without_merchant(monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "yookassa")
    monkeypatch.setattr(settings, "payment_merchant_id", "")
    assert payment_live_enabled() is False


def test_payment_live_enabled_with_partner_and_merchant(monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "yookassa")
    monkeypatch.setattr(settings, "payment_merchant_id", "merchant-123")
    assert payment_live_enabled() is True


def test_get_payment_adapter_fail_closed_without_merchant(monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "yookassa")
    monkeypatch.setattr(settings, "payment_merchant_id", "")
    with pytest.raises(HTTPException) as exc:
        get_payment_adapter()
    assert exc.value.status_code == 501


def test_create_session_and_ledger_hook():
    ledger = MagicMock()
    adapter = StubPaymentAdapter(ledger=ledger)
    session = adapter.create_session(
        payment_id="pay-1",
        amount_rub=10_000,
        idempotency_key="idem-1",
        booking_id="book-1",
    )
    assert session.provider == "stub"
    assert session.status == "pending"
    assert session.payment_id == "pay-1"
    ledger.on_session_created.assert_called_once_with("pay-1", 10_000)


def test_idempotency_key_validation():
    adapter = StubPaymentAdapter()
    assert adapter.normalize_idempotency_key("  key-1  ") == "key-1"
    with pytest.raises(PaymentAdapterError):
        adapter.normalize_idempotency_key("")
    with pytest.raises(PaymentAdapterError):
        adapter.normalize_idempotency_key("x" * 65)


def test_verify_webhook_valid_and_invalid():
    adapter = StubPaymentAdapter()
    event = adapter.verify_webhook(
        event_id="evt-1",
        payment_id="pay-1",
        status="succeeded",
        signature=_sign("evt-1", "pay-1", "succeeded"),
    )
    assert event.event_id == "evt-1"
    assert event.status == "succeeded"
    with pytest.raises(PaymentAdapterError, match="подпись"):
        adapter.verify_webhook(
            event_id="evt-1",
            payment_id="pay-1",
            status="succeeded",
            signature="bad",
        )
    with pytest.raises(PaymentAdapterError, match="status"):
        adapter.verify_webhook(
            event_id="evt-1",
            payment_id="pay-1",
            status="unknown",
            signature=_sign("evt-1", "pay-1", "unknown"),
        )


def test_refund_full_and_partial():
    ledger = MagicMock()
    adapter = StubPaymentAdapter(ledger=ledger)
    full = adapter.refund(
        payment_id="pay-1",
        amount_rub=5_000,
        total_rub=5_000,
        idempotency_key="ref-1",
    )
    assert full.kind == "full"
    assert full.status == "succeeded"
    partial = adapter.refund(payment_id="pay-1", amount_rub=2_000, total_rub=5_000)
    assert partial.kind == "partial"
    assert ledger.on_refund.call_count == 2


def test_refund_rejects_invalid_amount():
    adapter = StubPaymentAdapter()
    with pytest.raises(PaymentAdapterError):
        adapter.refund(payment_id="pay-1", amount_rub=0, total_rub=5_000)
    with pytest.raises(PaymentAdapterError):
        adapter.refund(payment_id="pay-1", amount_rub=6_000, total_rub=5_000)


def test_live_adapter_is_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "yookassa")
    monkeypatch.setattr(settings, "payment_merchant_id", "merchant-123")
    adapter = get_payment_adapter()
    with pytest.raises(PaymentAdapterUnavailable):
        adapter.create_session(
            payment_id="pay-1",
            amount_rub=1_000,
            idempotency_key="idem-1",
            booking_id="book-1",
        )


def test_health_payment_flags(client):
    res = client.get("/health")
    assert res.status_code == 200
    flags = res.json()["flags"]
    assert flags["payment_provider"] == "stub"
    assert flags["payment_live_enabled"] is False
