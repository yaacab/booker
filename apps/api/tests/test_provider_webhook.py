"""Original-byte verification and immutable provider/domain payment binding."""
import hashlib
import hmac
import json
from datetime import timedelta

import pytest

from booker_api.config import settings
from booker_api.models import Booking, BookingHold, Payment, PaymentWebhookEvent
from booker_api.security import now
from tests.test_payments import _awaiting_payment


def event_for(ctx, SessionLocal, **changes):
    with SessionLocal() as db:
        payment = db.get(Payment, ctx['payment_id'])
        result = {'event_id': 'raw-event', 'payment_id': payment.id, 'status': 'succeeded',
            'amount_rub': payment.amount_rub, 'currency': 'RUB', 'merchant_id': 'stub-merchant',
            'provider_reference': payment.provider_reference}
    return {**result, **changes}


def send_raw(client, body, *, invalid_signature=False):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    signature = hmac.new(settings.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post('/payments/provider-webhook', content=raw,
        headers={'content-type': 'application/json', 'x-booker-signature': 'wrong' if invalid_signature else signature})


def test_signed_original_bytes_capture_and_dedupe_normalized_event(client, SessionLocal):
    ctx = _awaiting_payment(client)
    event = event_for(ctx, SessionLocal)
    assert send_raw(client, event, invalid_signature=True).status_code == 401
    pending = send_raw(client, {**event, 'event_id': 'pending-event', 'status': 'pending'})
    assert pending.json()['payment_status'] == 'pending'
    assert pending.json()['booking_status'] == 'AwaitingPayment'
    result = send_raw(client, event)
    assert result.status_code == 200, result.text
    assert result.json()['booking_status'] == 'Confirmed'
    assert send_raw(client, json.dumps(event, indent=2).encode()).json() == result.json()
    assert send_raw(client, {**event, 'status': 'failed'}).status_code == 409
    late = send_raw(client, {**event, 'status': 'failed', 'event_id': 'late-failed'})
    assert late.json()['payment_status'] == 'succeeded'
    with SessionLocal() as db:
        rows = db.query(PaymentWebhookEvent).filter_by(payment_id=ctx['payment_id']).all()
        assert len(rows) == 3
        assert all(row.event_fingerprint and len(row.event_id) == 64 for row in rows)


@pytest.mark.parametrize('change', [
    {'amount_rub': 1}, {'amount_rub': True}, {'amount_rub': 106000.0}, {'amount_rub': '106000'},
    {'currency': 'USD'}, {'merchant_id': 'another-merchant'}, {'provider_reference': 'another-payment'},
    {'event_id': ''}, {'event_id': 'x' * 256}, {'status': 'refunded'}, {'merchant_id': None},
])
def test_signed_mismatches_never_change_payment(client, SessionLocal, change):
    ctx = _awaiting_payment(client)
    result = send_raw(client, event_for(ctx, SessionLocal, **change))
    assert result.status_code in (400, 409), result.text
    with SessionLocal() as db:
        assert db.get(Payment, ctx['payment_id']).status == 'pending'
        assert db.get(Booking, ctx['booking_id']).status == 'AwaitingPayment'
        assert db.query(PaymentWebhookEvent).count() == 0


def test_raw_body_limit_malformed_payload_and_default_secret_gate(client, SessionLocal, monkeypatch):
    assert send_raw(client, b'x' * 65537).status_code == 413
    assert send_raw(client, b'{"event_id":"one","event_id":"two"}').status_code == 401
    assert send_raw(client, b'not-json').status_code == 401
    ctx = _awaiting_payment(client)
    monkeypatch.setattr(settings, 'webhook_secret', 'dev-webhook-secret')
    monkeypatch.setattr(settings, 'allow_default_webhook_secret', False)
    assert send_raw(client, event_for(ctx, SessionLocal)).status_code == 503


def test_verified_late_capture_binds_reference_but_does_not_resurrect_hold(client, SessionLocal):
    ctx = _awaiting_payment(client)
    event = event_for(ctx, SessionLocal)
    with SessionLocal() as db:
        payment = db.get(Payment, ctx['payment_id'])
        payment.provider_reference = None
        payment.session_state = 'uncertain'
        db.query(BookingHold).filter_by(booking_id=ctx['booking_id']).one().expires_at = now() - timedelta(seconds=1)
        db.commit()
    result = send_raw(client, event)
    assert result.status_code == 200
    assert result.json()['payment_status'] == 'succeeded'
    assert result.json()['booking_status'] == 'AwaitingPayment'
    with SessionLocal() as db:
        assert db.get(Payment, ctx['payment_id']).provider_reference == event['provider_reference']


def test_reference_and_event_id_cannot_pay_two_bookings(client, SessionLocal):
    # Separate contexts need unique registration identifiers; clone a payment target
    # on the same real booking to exercise receiver binding, not availability setup.
    ctx = _awaiting_payment(client)
    event = event_for(ctx, SessionLocal)
    with SessionLocal() as db:
        original = db.get(Payment, ctx['payment_id'])
        other = Payment(booking_id=original.booking_id, amount_rub=original.amount_rub, provider='stub',
            status='pending', idempotency_key='another-payment', provider_reference=None)
        db.add(other); db.commit(); other_id = other.id
    assert send_raw(client, {**event, 'payment_id': other_id}).status_code == 409
    assert send_raw(client, event).status_code == 200
    result = send_raw(client, {**event, 'payment_id': other_id, 'provider_reference': 'unique-other'})
    assert result.status_code == 409
    with SessionLocal() as db:
        other = db.get(Payment, other_id)
        assert other.status == 'pending' and other.provider_reference is None


def test_stub_raw_receiver_disabled_in_production(client, SessionLocal, monkeypatch):
    ctx = _awaiting_payment(client)
    monkeypatch.setattr(settings, 'environment', 'production')
    assert send_raw(client, event_for(ctx, SessionLocal)).status_code == 503


def test_non_stub_adapter_cannot_use_unbound_legacy_json(client, monkeypatch):
    from booker_api.payments.stub import StubPaymentAdapter
    from booker_api.routers import payments
    class BoundaryFixture(StubPaymentAdapter):
        name = 'provider-fixture'
        def verify_webhook(self, **kwargs):
            raise AssertionError('Legacy unbound verification must not run')
    monkeypatch.setattr(payments, 'get_payment_adapter', lambda: BoundaryFixture())
    response = client.post('/payments/webhook', json={'event_id': 'id', 'payment_id': 'id', 'status': 'succeeded', 'signature': 'signed'})
    assert response.status_code == 400
