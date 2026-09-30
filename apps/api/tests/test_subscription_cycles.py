"""Calendar periods are paid facts; delivery time cannot create extra access."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from booker_api.commerce import entitlements, orders, renewals, service
from booker_api.commerce.renewals import cycle_boundary
from booker_api.config import settings
from booker_api.models import AuditLog, BillingOrder, CommercialPlan, Subscription
from booker_api.security import aware, now
from tests.test_commerce import buy, complete, org_user, state
from tests.test_commerce import stub as _stub

stub = _stub


@pytest.fixture()
def clock(monkeypatch):
    value = {'now': now()}
    for module in (entitlements, orders, renewals, service):
        monkeypatch.setattr(module, 'now', lambda: value['now'])
    return value


def setup(client, SessionLocal):
    _, headers, org = org_user(client)
    original = buy(client, headers, org).json()
    complete(client, headers, original)
    with SessionLocal() as db:
        row = db.get(BillingOrder, original['id'])
        anchor = aware(row.period_start)
        reference = json.loads(row.metadata_json)['subscription_reference']
    return headers, org, original, anchor, reference


def event(original, anchor, reference, cycle=1, status='paid'):
    start = cycle_boundary(anchor, 'monthly', cycle)
    end = cycle_boundary(anchor, 'monthly', cycle + 1)
    return {'event_id': f'cycle-{cycle}-{status}', 'initial_order_id': original['id'],
        'subscription_reference': reference, 'reference': f'payment-cycle-{cycle}',
        'cycle_number': cycle, 'period_start': start.isoformat(), 'period_end': end.isoformat(),
        'occurred_at': (start + timedelta(minutes=1)).isoformat(), 'status': status,
        'amount_rub': original['amount_rub'], 'currency': 'RUB'}


def send(client, body, signature=None):
    raw = json.dumps(body).encode()
    sig = hmac.new(settings.commerce_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post('/commerce/renewal-webhook', content=raw, headers={'X-Commerce-Signature': signature or sig})


def test_calendar_cycles_keep_original_anniversary():
    anchor = datetime(2028, 1, 31, tzinfo=timezone.utc)
    assert cycle_boundary(anchor, 'monthly', 1).day == 29
    assert cycle_boundary(anchor, 'monthly', 2).day == 31
    assert cycle_boundary(datetime(2028, 2, 29, tzinfo=timezone.utc), 'annual', 4).day == 29


def test_renewal_snapshot_duplicate_and_late_previous_cycle(client, SessionLocal, stub, clock):
    headers, org, original, anchor, reference = setup(client, SessionLocal)
    clock['now'] = cycle_boundary(anchor, 'monthly', 2) + timedelta(days=2)
    with SessionLocal() as db:
        db.query(CommercialPlan).filter_by(code='artist_pro', active=True).one().monthly_price_rub += 1000
        db.commit()
    body = event(original, anchor, reference, 2)
    response = send(client, body)
    assert response.status_code == 200, response.text
    assert send(client, body).json() == response.json()
    older = send(client, event(original, anchor, reference, 1))
    assert older.status_code == 200, older.text
    result = state(client, headers, org)
    assert result['plan']['code'] == 'artist_pro'
    assert datetime.fromisoformat(result['subscription']['current_period_end']) == cycle_boundary(anchor, 'monthly', 3)
    with SessionLocal() as db:
        rows = db.query(BillingOrder).filter(BillingOrder.subscription_parent_id == original['id']).all()
        assert len(rows) == 2 and all(row.amount_rub == original['amount_rub'] for row in rows)
        assert db.query(Subscription).one().last_billing_order_id == response.json()['order_id']
        assert db.query(AuditLog).filter_by(action='subscription.renewal_received').count() == 2


def test_future_paid_period_opens_only_at_boundary_and_not_in_gap(client, SessionLocal, stub, clock):
    headers, org, original, anchor, reference = setup(client, SessionLocal)
    body = event(original, anchor, reference, 2)
    body['occurred_at'] = clock['now'].isoformat()
    assert send(client, body).status_code == 200
    with SessionLocal() as db:
        assert db.query(Subscription).one().last_billing_order_id == original['id']
    clock['now'] = cycle_boundary(anchor, 'monthly', 1) + timedelta(days=1)
    assert state(client, headers, org)['plan']['code'] == 'artist_free'
    clock['now'] = cycle_boundary(anchor, 'monthly', 2)
    assert state(client, headers, org)['plan']['code'] == 'artist_pro'
    clock['now'] = cycle_boundary(anchor, 'monthly', 3)
    assert state(client, headers, org)['plan']['code'] == 'artist_free'


def test_failed_cycle_can_recover_but_cannot_reverse_paid(client, SessionLocal, stub, clock):
    headers, org, original, anchor, reference = setup(client, SessionLocal)
    clock['now'] = cycle_boundary(anchor, 'monthly', 1) + timedelta(days=1)
    failed = event(original, anchor, reference, status='failed')
    response = send(client, failed)
    assert response.status_code == 200, response.text
    result = state(client, headers, org)
    assert result['plan']['code'] == 'artist_free' and result['subscription']['status'] == 'past_due'
    paid = event(original, anchor, reference)
    assert send(client, paid).json()['order_id'] == response.json()['order_id']
    assert state(client, headers, org)['plan']['code'] == 'artist_pro'
    failed['event_id'] = 'delayed-failure'
    assert send(client, failed).json()['status'] == 'paid'
    assert state(client, headers, org)['plan']['code'] == 'artist_pro'


def test_cancelled_renewal_records_money_for_operator_without_new_access(client, SessionLocal, stub, clock):
    headers, org, original, anchor, reference = setup(client, SessionLocal)
    assert client.post(f'/commerce/organizations/{org}/subscription/cancel', headers=headers).status_code == 200
    clock['now'] = cycle_boundary(anchor, 'monthly', 1) + timedelta(days=1)
    response = send(client, event(original, anchor, reference))
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'paid' and response.json()['requires_operator']
    assert state(client, headers, org)['plan']['code'] == 'artist_free'


@pytest.mark.parametrize(('field', 'value'), [('amount_rub', 1), ('amount_rub', True),
    ('subscription_reference', 'foreign'), ('currency', 'USD'), ('cycle_number', 0),
    ('period_end', '2099-01-01T00:00:00Z')])
def test_invalid_cycle_never_changes_money_or_access(client, SessionLocal, stub, clock, field, value):
    _, _, original, anchor, reference = setup(client, SessionLocal)
    clock['now'] = cycle_boundary(anchor, 'monthly', 1) + timedelta(days=1)
    body = event(original, anchor, reference)
    body[field] = value
    assert send(client, body).status_code in (400, 409)
    with SessionLocal() as db:
        assert db.query(BillingOrder).count() == 1


def test_cycle_event_and_provider_payment_cannot_be_reassigned(client, SessionLocal, stub, clock):
    _, _, original, anchor, reference = setup(client, SessionLocal)
    clock['now'] = cycle_boundary(anchor, 'monthly', 1) + timedelta(days=1)
    body = event(original, anchor, reference)
    assert send(client, body, signature='wrong').status_code == 400
    with SessionLocal() as db:
        body['reference'] = db.get(BillingOrder, original['id']).provider_reference
    assert send(client, body).status_code == 409
    body['reference'] = 'legitimate-new-reference'
    assert send(client, body).status_code == 200
    body['status'] = 'failed'
    assert send(client, body).status_code == 409


def test_old_agreement_after_upgrade_cannot_replace_new_plan(client, SessionLocal, stub, clock, monkeypatch):
    from booker_api.commerce.provider import StubProvider
    headers, org, original, anchor, reference = setup(client, SessionLocal)
    cancellations = []
    monkeypatch.setattr(StubProvider, 'cancel_subscription', lambda self, ref: cancellations.append(ref))
    premium = buy(client, headers, org, code='artist_premium', key='upgrade').json()
    complete(client, headers, premium)
    assert cancellations == [reference]
    body = event(original, anchor, reference)
    body['occurred_at'] = clock['now'].isoformat()
    response = send(client, body)
    assert response.status_code == 200 and response.json()['requires_operator']
    assert state(client, headers, org)['plan']['code'] == 'artist_premium'


def test_late_first_capture_does_not_start_a_new_month_on_delivery(client, SessionLocal, stub, clock):
    _, headers, org = org_user(client)
    original = buy(client, headers, org).json()
    captured = clock['now'] - timedelta(days=70)
    with SessionLocal() as db:
        row = db.get(BillingOrder, original['id'])
        row.created_at = captured - timedelta(minutes=1)
        reference = row.provider_reference
        db.commit()
    body = {'event_id': 'late-initial', 'order_id': original['id'], 'reference': reference,
        'status': 'paid', 'amount_rub': original['amount_rub'], 'currency': 'RUB', 'paid_at': captured.isoformat()}
    raw = json.dumps(body).encode()
    sig = hmac.new(settings.commerce_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post('/commerce/webhook', content=raw, headers={'X-Commerce-Signature': sig})
    assert response.status_code == 200, response.text
    assert state(client, headers, org)['plan']['code'] == 'artist_free'
    with SessionLocal() as db:
        row = db.get(BillingOrder, original['id'])
        assert row.status == 'paid' and aware(row.period_start) == captured
        assert aware(row.period_end) == cycle_boundary(captured, 'monthly', 1)


def test_past_due_can_cancel_future_attempts(client, SessionLocal, stub, clock):
    headers, org, original, anchor, reference = setup(client, SessionLocal)
    clock['now'] = cycle_boundary(anchor, 'monthly', 1) + timedelta(days=1)
    assert send(client, event(original, anchor, reference, status='failed')).status_code == 200
    url = f'/commerce/organizations/{org}/subscription/cancel'
    assert client.post(url, headers=headers).status_code == 200
    assert client.post(url, headers=headers).status_code == 200
    assert send(client, event(original, anchor, reference)).json()['requires_operator']
