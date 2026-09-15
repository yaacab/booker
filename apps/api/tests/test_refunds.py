"""Refunds reserve amounts, require two actual actors, and await real outcomes."""
import pytest

from booker_api.models import AuditLog, Payment, PaymentRefund
from booker_api.payments.adapter import RefundOutcome
from booker_api.payments.stub import StubPaymentAdapter
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_payments import _awaiting_payment, _sign
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def setup(client):
    ctx = _awaiting_payment(client)
    response = client.post('/payments/webhook', json={'payment_id': ctx['payment_id'], 'event_id': 'refund-capture',
        'status': 'succeeded', 'signature': _sign('refund-capture', ctx['payment_id'], 'succeeded')})
    assert response.status_code == 200
    first = _promote_admin(client, 'refund-first@booker.test', totp=TEST_TOTP_SECRET)
    second = _promote_admin(client, 'refund-second@booker.test', totp=TEST_TOTP_SECRET)
    return ctx, first, second


def request_refund(client, ctx, actor, amount=None, key='refund-request-key'):
    return client.post('/admin/refunds', json={'payment_id': ctx['payment_id'], 'amount_rub': amount,
        'reason': 'Согласованный возврат', 'idempotency_key': key, 'totp': totp_code()}, headers=auth_header(actor['token']))


def approve(client, refund_id, actor):
    return client.post(f'/admin/refunds/{refund_id}/approve', json={'totp': totp_code()}, headers=auth_header(actor['token']))


def action(client, row, actor, verb):
    return client.post(f"/admin/refunds/{row['id']}/{verb}", json={'totp': totp_code()}, headers=auth_header(actor['token']))


def test_partial_then_remaining_refund_and_idempotence(client, SessionLocal):
    ctx, first, second = setup(client)
    row = request_refund(client, ctx, first, amount=1000).json()
    assert request_refund(client, ctx, first, amount=1000).json()['id'] == row['id']
    done = approve(client, row['id'], second)
    assert done.json()['payment_status'] == 'partially_refunded'
    assert approve(client, row['id'], second).json() == done.json()
    assert action(client, row, first, 'retry').json()['status'] == 'succeeded'
    with SessionLocal() as db:
        total = db.get(Payment, ctx['payment_id']).amount_rub
        assert db.query(AuditLog).filter_by(action='payment.refunded').count() == 1
    assert request_refund(client, ctx, first, amount=total, key='over-total-key').status_code == 409
    remaining = request_refund(client, ctx, first, key='remaining-key').json()
    assert remaining['amount_rub'] == total - 1000
    assert approve(client, remaining['id'], second).json()['payment_status'] == 'refunded'
    assert request_refund(client, ctx, first, key='after-full-key').status_code == 409
    with SessionLocal() as db:
        assert sum(r.amount_rub for r in db.query(PaymentRefund).filter_by(status='succeeded')) == total
        assert db.query(AuditLog).filter_by(action='refund.approved').count() == 2


@pytest.mark.parametrize('outcome_status', ['pending', 'failed'])
def test_provider_acceptance_or_failure_is_not_money_returned(client, SessionLocal, monkeypatch, outcome_status):
    ctx, first, second = setup(client)
    row = request_refund(client, ctx, first).json()
    def refund(self, **kw):
        return RefundOutcome(refund_id='provider-ref', amount_rub=kw['amount_rub'], kind='full', status=outcome_status)
    monkeypatch.setattr(StubPaymentAdapter, 'refund', refund)
    result = approve(client, row['id'], second)
    assert result.json()['status'] == outcome_status
    assert result.json()['payment_status'] == 'succeeded'
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action='payment.refunded').count() == 0
    if outcome_status == 'pending':
        assert request_refund(client, ctx, first, key='must-not-overlap').status_code == 409
        def status(self, **kw):
            return RefundOutcome(refund_id=kw['refund_id'], amount_rub=kw['amount_rub'], kind='full', status='succeeded')
        monkeypatch.setattr(StubPaymentAdapter, 'get_refund_status', status)
        assert action(client, row, first, 'refresh').json()['payment_status'] == 'refunded'
        assert action(client, row, first, 'refresh').json()['status'] == 'succeeded'


def test_timeout_preserves_approval_key_and_amount(client, SessionLocal, monkeypatch):
    ctx, first, second = setup(client)
    row = request_refund(client, ctx, first).json()
    calls = []
    def refund(self, **kw):
        calls.append(kw)
        with SessionLocal() as db:
            stored = db.get(PaymentRefund, row['id'])
            assert stored.approved_by == second['user_id'] and stored.status == 'submitting'
        if len(calls) == 1:
            raise TimeoutError('private partner response')
        return RefundOutcome(refund_id='recovered-ref', amount_rub=kw['amount_rub'], kind='full', status='succeeded')
    monkeypatch.setattr(StubPaymentAdapter, 'refund', refund)
    response = approve(client, row['id'], second)
    assert response.json()['status'] == 'uncertain'
    assert 'private partner' not in response.text
    assert response.json()['payment_status'] == 'succeeded'
    assert action(client, row, first, 'retry').json()['status'] == 'succeeded'
    assert calls[0] == calls[1]
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action='refund.approved').count() == 1
        assert db.query(AuditLog).filter_by(action='payment.refunded').count() == 1


def test_refund_auth_2fa_approval_and_rejection(client, SessionLocal):
    ctx, first, second = setup(client)
    outsider = register(client, 'refund-outsider@booker.test')
    no_totp = _promote_admin(client, 'refund-no-totp@booker.test')
    assert request_refund(client, ctx, outsider).status_code == 403
    assert request_refund(client, ctx, no_totp).status_code == 403
    assert client.get('/admin/refunds', headers=auth_header(outsider['token'])).status_code == 403
    row = request_refund(client, ctx, first).json()
    assert approve(client, row['id'], outsider).status_code == 403
    assert approve(client, row['id'], no_totp).status_code == 403
    assert approve(client, row['id'], first).status_code == 403
    assert client.post(f"/admin/refunds/{row['id']}/approve", headers=auth_header(second['token']), json={'totp': '000000'}).status_code == 403
    assert action(client, row, first, 'reject').json()['status'] == 'rejected'
    assert approve(client, row['id'], second).json()['status'] == 'rejected'
    with SessionLocal() as db:
        assert db.get(Payment, ctx['payment_id']).status == 'succeeded'
        assert db.get(PaymentRefund, row['id']).approved_by is None


def test_external_refund_needs_explicit_transfer_confirmation(client, SessionLocal, monkeypatch):
    from booker_api.config import settings
    ctx, first, second = setup(client)
    with SessionLocal() as db:
        db.get(Payment, ctx['payment_id']).provider = 'external'; db.commit()
    monkeypatch.setattr(settings, 'payment_provider', 'external')
    row = request_refund(client, ctx, first).json()
    pending = approve(client, row['id'], second).json()
    assert pending['status'] == 'pending' and pending['payment_status'] == 'succeeded'
    url = f"/admin/refunds/{row['id']}/confirm-external"
    done = client.post(url, json={'totp': totp_code(), 'transfer_reference': 'operator-verified-transfer'}, headers=auth_header(second['token']))
    assert done.json()['status'] == 'succeeded'
    assert done.json()['payment_status'] == 'refunded'


@pytest.mark.parametrize('problem', ['amount', 'kind', 'status', 'reference'])
def test_invalid_refund_outcome_keeps_money_and_reserves_request(client, monkeypatch, problem):
    ctx, first, second = setup(client)
    row = request_refund(client, ctx, first).json()
    def refund(self, **kw):
        return RefundOutcome(refund_id='' if problem == 'reference' else 'ref',
            amount_rub=kw['amount_rub'] + (1 if problem == 'amount' else 0),
            kind='partial' if problem == 'kind' else 'full', status='unknown' if problem == 'status' else 'succeeded')
    monkeypatch.setattr(StubPaymentAdapter, 'refund', refund)
    result = approve(client, row['id'], second).json()
    assert result['status'] == 'uncertain' and result['payment_status'] == 'succeeded'
    assert request_refund(client, ctx, first, key='cannot-duplicate').status_code == 409


def test_refund_request_conflicts_cannot_change_approved_amount(client):
    ctx, first, second = setup(client)
    row = request_refund(client, ctx, first, amount=1000).json()
    assert request_refund(client, ctx, first, amount=1001).status_code == 409
    assert request_refund(client, ctx, second, key='another-request').status_code == 409
    assert action(client, row, first, 'retry').status_code == 409


def test_revoked_requester_cannot_authorize_provider_refund(client, SessionLocal):
    from booker_api.models import User
    ctx, first, second = setup(client)
    row = request_refund(client, ctx, first).json()
    with SessionLocal() as db:
        db.get(User, first['user_id']).is_platform_admin = False
        db.commit()
    assert approve(client, row['id'], second).status_code == 409
    with SessionLocal() as db:
        saved = db.get(PaymentRefund, row['id'])
        assert saved.status == 'awaiting_approval' and saved.approved_by is None
        assert db.get(Payment, ctx['payment_id']).status == 'succeeded'


def test_disabled_partner_preserves_independent_approval_for_later_retry(client, SessionLocal, monkeypatch):
    from booker_api.config import settings
    ctx, first, second = setup(client)
    row = request_refund(client, ctx, first).json()
    monkeypatch.setattr(settings, 'payment_provider', 'disabled')
    assert approve(client, row['id'], second).status_code == 503
    with SessionLocal() as db:
        saved = db.get(PaymentRefund, row['id'])
        assert saved.status == 'approved' and saved.approved_by == second['user_id']
        assert db.get(Payment, ctx['payment_id']).status == 'succeeded'
    monkeypatch.setattr(settings, 'payment_provider', 'stub')
    assert action(client, row, first, 'retry').json()['status'] == 'succeeded'


def test_same_provider_reference_cannot_count_as_two_refunds(client, SessionLocal, monkeypatch):
    ctx, first, second = setup(client)
    def provider(self, **kw):
        return RefundOutcome(refund_id='one-provider-transfer', amount_rub=kw['amount_rub'], kind='partial', status='succeeded')
    monkeypatch.setattr(StubPaymentAdapter, 'refund', provider)
    one = request_refund(client, ctx, first, amount=1000).json()
    assert approve(client, one['id'], second).json()['status'] == 'succeeded'
    two = request_refund(client, ctx, first, amount=1000, key='second-refund').json()
    assert approve(client, two['id'], second).json()['status'] == 'uncertain'
    with SessionLocal() as db:
        assert db.get(PaymentRefund, two['id']).provider_reference is None
        assert db.query(PaymentRefund).filter_by(status='succeeded').count() == 1
        assert db.query(AuditLog).filter_by(action='payment.refunded').count() == 1
        assert db.get(Payment, ctx['payment_id']).status == 'partially_refunded'
