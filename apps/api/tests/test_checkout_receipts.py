"""Durable checkout identity, retry safety and private redirect receipts."""
from dataclasses import replace

import pytest

from booker_api.models import AuditLog, Booking, Event, Payment, TeamMember
from booker_api.payments.adapter import PaymentSession
from booker_api.payments.stub import StubPaymentAdapter
from tests.conftest import auth_header, register
from tests.test_payments import _awaiting_payment


def fresh(client, SessionLocal):
    ctx = _awaiting_payment(client)
    with SessionLocal() as db:
        db.delete(db.get(Payment, ctx['payment_id']))
        db.commit()
    return ctx


def checkout(client, ctx, key='new-checkout'):
    return client.post(f"/bookings/{ctx['booking_id']}/payments", json={'idempotency_key': key},
        headers=auth_header(ctx['customer']['token']))


def test_timeout_keeps_identity_and_retry_receipt_private(client, SessionLocal, monkeypatch):
    ctx = fresh(client, SessionLocal)
    calls = []
    url = 'https://payments.example.test/session/private-checkout-token'

    def session(self, **kwargs):
        calls.append(kwargs)
        with SessionLocal() as db:
            persisted = db.get(Payment, kwargs['payment_id'])
            assert persisted is not None
            assert persisted.idempotency_key == kwargs['idempotency_key']
        if len(calls) == 1:
            raise TimeoutError('sensitive-provider-body')
        return PaymentSession(provider='stub', payment_id=kwargs['payment_id'], status='pending',
            provider_reference='checkout-reference', checkout_url=url)

    monkeypatch.setattr(StubPaymentAdapter, 'create_session', session)
    first = checkout(client, ctx)
    assert first.status_code == 502 and 'sensitive-provider-body' not in first.text
    with SessionLocal() as db:
        pay = db.query(Payment).filter_by(booking_id=ctx['booking_id']).one()
        assert pay.session_state == 'uncertain' and pay.status == 'pending'
        saved_id = pay.id
    result = checkout(client, ctx, 'another-click')
    assert result.status_code == 200, result.text
    assert result.json()['id'] == saved_id
    assert result.json()['checkout_url'] == url
    assert result.json()['session_state'] == 'ready'
    assert calls[0] == calls[1]
    assert checkout(client, ctx, 'third-click').json() == result.json()
    assert len(calls) == 2
    viewer = register(client, 'checkout-viewer@booker.test')
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx['cust_org']['id'], user_id=viewer['user_id'], role='viewer'))
        assert url not in str([row.payload for row in db.query(AuditLog).all()])
        assert db.get(Payment, saved_id).provider_reference == 'checkout-reference'
        db.commit()
    for actor in (ctx['owner'], viewer):
        room = client.get(f"/deal-room/{ctx['booking_id']}", headers=auth_header(actor['token'])).json()
        assert room['payment']['checkout_url'] is None
        assert not room['payment_capabilities']['can_checkout']
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=auth_header(ctx['customer']['token'])).json()
    assert room['payment']['checkout_url'] == url
    from booker_api.config import settings
    for provider in ('disabled', 'external'):
        monkeypatch.setattr(settings, 'payment_provider', provider)
        hidden = client.get(f"/deal-room/{ctx['booking_id']}", headers=auth_header(ctx['customer']['token'])).json()
        assert hidden['payment']['checkout_url'] is None
        assert not hidden['payment_capabilities']['can_checkout']
    monkeypatch.setattr(settings, 'payment_provider', 'stub')
    with SessionLocal() as db:
        db.get(Event, db.get(Booking, ctx['booking_id']).event_id).status = 'Cancelled'
        db.commit()
    assert checkout(client, ctx).json()['checkout_url'] is None
    assert len(calls) == 2


@pytest.mark.parametrize('change', [
    {'checkout_url': 'javascript:alert(1)'}, {'checkout_url': 'https://user:secret@pay.example.test'},
    {'checkout_url': 'https://[invalid'}, {'status': 'succeeded'}, {'payment_id': 'foreign'},
    {'provider': 'foreign'}, {'provider_reference': None},
])
def test_invalid_provider_session_cannot_expose_redirect_or_capture(client, SessionLocal, monkeypatch, change):
    ctx = fresh(client, SessionLocal)
    def session(self, **kwargs):
        value = PaymentSession(provider='stub', payment_id=kwargs['payment_id'], status='pending',
            checkout_url='https://pay.example.test/session', provider_reference='ref')
        return replace(value, **change)
    monkeypatch.setattr(StubPaymentAdapter, 'create_session', session)
    assert checkout(client, ctx).status_code == 502
    with SessionLocal() as db:
        pay = db.query(Payment).filter_by(booking_id=ctx['booking_id']).one()
        assert pay.status == 'pending' and pay.session_state == 'uncertain'
        assert pay.checkout_url is None
        assert db.get(Booking, ctx['booking_id']).status == 'AwaitingPayment'


def test_legacy_receipt_does_not_create_new_session(client, SessionLocal, monkeypatch):
    ctx = _awaiting_payment(client)
    with SessionLocal() as db:
        pay = db.get(Payment, ctx['payment_id'])
        pay.checkout_url = pay.provider_reference = None
        db.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError('Must not call provider for a saved legacy payment')
    monkeypatch.setattr(StubPaymentAdapter, 'create_session', forbidden)
    result = checkout(client, ctx)
    assert result.status_code == 200
    assert result.json()['id'] == ctx['payment_id']
    assert result.json()['checkout_url'] is None


@pytest.mark.parametrize('problem', ['past_event', 'lost_slot', 'expired_hold'])
def test_saved_url_is_hidden_when_reservation_is_no_longer_payable(client, SessionLocal, problem):
    from datetime import timedelta

    from booker_api.models import AvailabilitySlot, BookingHold
    from booker_api.security import now
    ctx = _awaiting_payment(client)
    with SessionLocal() as db:
        payment = db.get(Payment, ctx['payment_id'])
        payment.checkout_url = 'https://pay.example.test/session'
        booking = db.get(Booking, ctx['booking_id'])
        if problem == 'past_event':
            db.get(Event, booking.event_id).event_date = now() - timedelta(seconds=1)
        elif problem == 'lost_slot':
            db.get(AvailabilitySlot, booking.slot_id).status = 'open'
        else:
            db.query(BookingHold).filter_by(booking_id=booking.id).one().expires_at = now() - timedelta(seconds=1)
        db.commit()
    result = checkout(client, ctx)
    assert result.status_code == 200
    assert result.json()['checkout_url'] is None


def test_checkout_cannot_reuse_another_payment_provider_reference(client, SessionLocal, monkeypatch):
    ctx = fresh(client, SessionLocal)
    with SessionLocal() as db:
        original = db.get(Booking, ctx['booking_id'])
        other_booking = Booking(event_id=original.event_id, offer_id=original.offer_id, slot_id=original.slot_id, status='Cancelled')
        db.add(other_booking); db.flush()
        db.add(Payment(booking_id=other_booking.id, amount_rub=1000, provider='stub',
            status='pending', idempotency_key='existing-foreign-payment', provider_reference='already-owned'))
        db.commit()
    def session(self, **kw):
        return PaymentSession(provider='stub', payment_id=kw['payment_id'], status='pending',
            checkout_url='https://pay.example.test/shared', provider_reference='already-owned')
    monkeypatch.setattr(StubPaymentAdapter, 'create_session', session)
    assert checkout(client, ctx).status_code == 502
    with SessionLocal() as db:
        payment = db.query(Payment).filter_by(booking_id=ctx['booking_id']).one()
        assert payment.status == 'pending' and payment.session_state == 'uncertain'
        assert payment.provider_reference is None and payment.checkout_url is None
