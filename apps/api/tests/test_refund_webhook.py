"""Signed refund facts must match the saved, independently approved command."""
import hashlib
import hmac
import json

import pytest

from booker_api.config import settings
from booker_api.models import AuditLog, Payment, PaymentRefund, User
from booker_api.payments.adapter import RefundOutcome
from booker_api.payments.stub import StubPaymentAdapter
from tests.test_refunds import approve, request_refund, setup


def prepared(client, SessionLocal, monkeypatch, *, uncertain=False, submit=True):
    ctx, first, second = setup(client)
    row = request_refund(client, ctx, first, amount=1000).json()
    def refund(self, **kw):
        if uncertain:
            raise TimeoutError('private bank response')
        return RefundOutcome(refund_id='provider-refund', amount_rub=kw['amount_rub'], kind='partial', status='pending')
    monkeypatch.setattr(StubPaymentAdapter, 'refund', refund)
    if submit:
        assert approve(client, row['id'], second).json()['status'] == ('uncertain' if uncertain else 'pending')
    with SessionLocal() as db:
        saved = db.get(PaymentRefund, row['id'])
        pay = db.get(Payment, ctx['payment_id'])
        event = {'event_id': 'refund-notice-1', 'payment_id': pay.id, 'request_key': saved.idempotency_key,
            'payment_reference': pay.provider_reference, 'refund_reference': 'provider-refund', 'amount_rub': 1000,
            'currency': 'RUB', 'merchant_id': 'stub-merchant', 'status': 'succeeded'}
    return row, event, first


def post(client, event, *, signature=None, raw=None):
    body = raw if raw is not None else json.dumps(event).encode()
    signed = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post('/payments/refund-provider-webhook', content=body,
        headers={'X-Booker-Signature': signature if signature is not None else signed})


@pytest.mark.parametrize('uncertain', [False, True])
def test_raw_refund_recovers_and_replays_once(client, SessionLocal, monkeypatch, uncertain):
    row, event, first = prepared(client, SessionLocal, monkeypatch, uncertain=uncertain)
    with SessionLocal() as db:
        db.get(User, first['user_id']).is_platform_admin = False
        db.commit()
    response = post(client, event)
    assert response.status_code == 200, response.text
    assert response.json()['payment_status'] == 'partially_refunded'
    assert post(client, event, raw=json.dumps(event, indent=2).encode()).json() == response.json()
    assert post(client, dict(event, event_id='same-result-new-event')).status_code == 200
    assert post(client, dict(event, event_id='late-pending', status='pending')).json()['status'] == 'succeeded'
    assert post(client, dict(event, event_id='contradiction', status='failed')).status_code == 409
    with SessionLocal() as db:
        assert db.get(PaymentRefund, row['id']).provider_reference == event['refund_reference']
        assert db.query(AuditLog).filter_by(action='payment.refunded').count() == 1
        assert db.query(AuditLog).filter_by(action='refund.webhook').count() == 3


@pytest.mark.parametrize(('field', 'value'), [('amount_rub', 1001), ('amount_rub', True),
    ('amount_rub', 1000.0), ('currency', 'USD'), ('merchant_id', 'foreign-merchant'),
    ('payment_id', 'foreign-payment'), ('request_key', 'unknown-key'),
    ('payment_reference', 'foreign-payment-reference'), ('refund_reference', 'foreign-refund'),
    ('status', 'unknown'), ('event_id', ''), ('refund_reference', ['invalid'])])
def test_raw_refund_rejects_foreign_or_malformed_facts(client, SessionLocal, monkeypatch, field, value):
    row, event, _ = prepared(client, SessionLocal, monkeypatch)
    assert post(client, dict(event, **{field: value})).status_code in (400, 409)
    with SessionLocal() as db:
        assert db.get(PaymentRefund, row['id']).status == 'pending'
        assert db.get(Payment, event['payment_id']).status == 'succeeded'
        assert db.query(AuditLog).filter_by(action='payment.refunded').count() == 0


def test_raw_refund_signature_and_size_before_processing(client, SessionLocal, monkeypatch):
    row, event, _ = prepared(client, SessionLocal, monkeypatch)
    assert post(client, event, signature='wrong').status_code == 401
    assert post(client, event, raw=b'{}', signature='wrong').status_code == 401
    assert post(client, event, raw=b'[]').status_code == 401
    assert post(client, event, raw=b'{"event_id":"a","event_id":"b"}').status_code == 401
    assert post(client, event, raw=b'x' * 65537).status_code == 413
    with SessionLocal() as db:
        assert db.get(PaymentRefund, row['id']).status == 'pending'


def test_raw_refund_needs_submitted_independent_approval(client, SessionLocal, monkeypatch):
    row, event, _ = prepared(client, SessionLocal, monkeypatch, submit=False)
    assert post(client, event).status_code == 409
    with SessionLocal() as db:
        assert db.get(PaymentRefund, row['id']).status == 'awaiting_approval'


def test_raw_refund_event_identity_is_immutable(client, SessionLocal, monkeypatch):
    _, event, _ = prepared(client, SessionLocal, monkeypatch)
    assert post(client, dict(event, status='pending')).status_code == 200
    assert post(client, event).status_code == 409
    assert post(client, dict(event, event_id='next-state')).status_code == 200


def test_raw_refund_unsupported_provider_and_production_stub_fail_closed(client, monkeypatch):
    monkeypatch.setattr(settings, 'payment_provider', 'external')
    assert post(client, {}).status_code == 503
    monkeypatch.setattr(settings, 'payment_provider', 'stub')
    monkeypatch.setattr(settings, 'environment', 'production')
    assert post(client, {}).status_code == 503
