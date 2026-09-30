"""Operator lookup reads a provider payment and never creates another checkout."""
from datetime import timedelta

import pytest

from booker_api.models import AuditLog, Booking, BookingHold, Payment, PaymentWebhookEvent
from booker_api.payments.adapter import VerifiedPaymentEvent
from booker_api.payments.stub import StubPaymentAdapter
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_payments import _awaiting_payment
from tests.test_provider_webhook import event_for, send_raw
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def reconcile(client, ctx, admin, code=None):
    return client.post(f"/admin/payments/{ctx['payment_id']}/reconcile", headers=auth_header(admin['token']),
        json={'totp': code if code is not None else totp_code()})


def operator(client):
    return _promote_admin(client, 'payment-reconciler@booker.test', totp=TEST_TOTP_SECRET)


def forbid_checkout(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('A status read must never create checkout')
    monkeypatch.setattr(StubPaymentAdapter, 'create_session', forbidden)


def test_expired_uncertain_checkout_reconciles_money_without_new_checkout(client, SessionLocal, monkeypatch):
    ctx = _awaiting_payment(client)
    admin = operator(client)
    provider_event = event_for(ctx, SessionLocal)
    with SessionLocal() as db:
        payment = db.get(Payment, ctx['payment_id'])
        key = payment.idempotency_key
        payment.provider_reference = None; payment.session_state = 'uncertain'
        db.query(BookingHold).filter_by(booking_id=ctx['booking_id']).one().expires_at = now() - timedelta(seconds=1)
        db.commit()
    calls = []
    def status(self, **kw):
        calls.append(kw)
        assert kw == {'payment_id': ctx['payment_id'], 'provider_reference': None, 'idempotency_key': key}
        return VerifiedPaymentEvent(**provider_event)
    monkeypatch.setattr(StubPaymentAdapter, 'get_payment_status', status)
    forbid_checkout(monkeypatch)
    result = reconcile(client, ctx, admin)
    assert result.status_code == 200, result.text
    assert result.json()['payment_status'] == 'succeeded'
    assert result.json()['booking_status'] == 'AwaitingPayment'
    assert result.json()['requires_operator']
    assert len(calls) == 1
    with SessionLocal() as db:
        assert db.query(Payment).count() == 1
        assert db.get(Payment, ctx['payment_id']).provider_reference == provider_event['provider_reference']
        assert db.query(AuditLog).filter_by(action='payment.reconciled', actor_user_id=admin['user_id']).count() == 1
        assert db.query(AuditLog).filter_by(action='payment.reservation_conflict').count() == 1


def test_repeated_lookup_returns_current_domain_state_not_old_receipt(client, SessionLocal, monkeypatch):
    ctx = _awaiting_payment(client)
    admin = operator(client)
    pending = event_for(ctx, SessionLocal, status='pending')
    monkeypatch.setattr(StubPaymentAdapter, 'get_payment_status', lambda self, **kw: VerifiedPaymentEvent(**pending))
    forbid_checkout(monkeypatch)
    first = reconcile(client, ctx, admin).json()
    assert first['payment_status'] == 'pending' and not first['requires_operator']
    assert send_raw(client, {**pending, 'event_id': 'capture-after-read', 'status': 'succeeded'}).status_code == 200
    second = reconcile(client, ctx, admin).json()
    assert second['provider_status'] == 'pending'
    assert second['payment_status'] == 'succeeded' and second['requires_operator']
    assert second['booking_status'] == 'Confirmed'
    with SessionLocal() as db:
        assert db.query(PaymentWebhookEvent).count() == 2  # lookup receipt + capture webhook
        assert db.query(AuditLog).filter_by(action='payment.reconciled').count() == 1
        assert db.query(AuditLog).filter_by(action='payment.reconciliation_requested').count() == 2


@pytest.mark.parametrize('change', [
    {'payment_id': 'another-payment'}, {'amount_rub': 1}, {'currency': 'USD'},
    {'merchant_id': 'another-merchant'}, {'provider_reference': 'another-reference'},
])
def test_mismatched_lookup_never_changes_payment(client, SessionLocal, monkeypatch, change):
    ctx = _awaiting_payment(client)
    admin = operator(client)
    event = event_for(ctx, SessionLocal, **change)
    monkeypatch.setattr(StubPaymentAdapter, 'get_payment_status', lambda self, **kw: VerifiedPaymentEvent(**event))
    forbid_checkout(monkeypatch)
    assert reconcile(client, ctx, admin).status_code == 409
    with SessionLocal() as db:
        assert db.get(Payment, ctx['payment_id']).status == 'pending'
        assert db.query(PaymentWebhookEvent).count() == 0


def test_lookup_auth_totp_and_unavailable_provider(client, SessionLocal, monkeypatch):
    ctx = _awaiting_payment(client)
    admin = operator(client)
    outsider = register(client, 'reconcile-outsider@booker.test')
    no_totp = _promote_admin(client, 'reconcile-no-totp@booker.test')
    forbid_checkout(monkeypatch)
    assert reconcile(client, ctx, outsider).status_code == 403
    assert reconcile(client, ctx, no_totp).status_code == 403
    assert reconcile(client, ctx, admin, '000000').status_code == 403
    # Local stub must not invent a successful bank status.
    assert reconcile(client, ctx, admin).status_code == 503
    def timeout(self, **kw):
        raise TimeoutError('secret body from the partner')
    monkeypatch.setattr(StubPaymentAdapter, 'get_payment_status', timeout)
    result = reconcile(client, ctx, admin)
    assert result.status_code == 502 and 'secret body' not in result.text
    with SessionLocal() as db:
        assert db.get(Payment, ctx['payment_id']).status == 'pending'


def test_capture_lookup_does_not_reverse_refund_or_recreate_cancelled_booking(client, SessionLocal, monkeypatch):
    ctx = _awaiting_payment(client)
    admin = operator(client)
    event = event_for(ctx, SessionLocal)
    assert send_raw(client, event).status_code == 200
    with SessionLocal() as db:
        db.get(Payment, ctx['payment_id']).status = 'partially_refunded'
        db.get(Booking, ctx['booking_id']).status = 'Cancelled'
        db.commit()
    monkeypatch.setattr(StubPaymentAdapter, 'get_payment_status', lambda self, **kw: VerifiedPaymentEvent(**event))
    result = reconcile(client, ctx, admin).json()
    assert result['payment_status'] == 'partially_refunded'
    assert result['booking_status'] == 'Cancelled'
