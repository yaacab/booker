from datetime import timedelta

from booker_api.models import AuditLog, BillingOrder, Subscription
from booker_api.security import now
from tests.test_commerce import org_user, platform_admin


def test_admin_grant_revoke_is_audited_and_preserves_money(client, SessionLocal):
    _user, headers, org = org_user(client)
    admin = platform_admin(client, SessionLocal)
    assert client.get('/admin/commerce/organizations', headers=headers).status_code == 403
    assert client.get('/admin/commerce/organizations').status_code == 401
    initial = client.get('/admin/commerce/organizations', headers=admin, params={'q': org}).json()
    assert initial['total'] == 1 and initial['items'][0]['subscription'] is None
    grant = {'plan_code': 'artist_pro', 'days': 7, 'status': 'trial', 'reason': 'Support trial', 'expected_updated_at': ''}
    response = client.post(f'/admin/commerce/organizations/{org}/grant', headers=admin, json=grant)
    assert response.status_code == 200, response.text
    token = response.json()['updated_at']
    assert client.post(f'/admin/commerce/organizations/{org}/grant', headers=admin, json=grant).status_code == 409
    with SessionLocal() as db:
        order = BillingOrder(organization_id=org, product_kind='subscription', product_code='artist_pro', amount_rub=1990, status='paid', provider='stub', idempotency_key='historic-payment')
        db.add(order); db.commit(); order_id = order.id
    revoke = {'expected_updated_at': token, 'reason': 'Trial completed'}
    assert client.post(f'/admin/commerce/organizations/{org}/revoke', headers=headers, json=revoke).status_code == 403
    assert client.post(f'/admin/commerce/organizations/{org}/revoke', headers=admin, json={**revoke, 'reason': '   '}).status_code == 422
    response = client.post(f'/admin/commerce/organizations/{org}/revoke', headers=admin, json=revoke)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'cancelled'
    with SessionLocal() as db:
        from booker_api.commerce.entitlements import get_entitlements
        assert get_entitlements(db, org)['plan']['code'] == 'artist_free'
        assert db.get(BillingOrder, order_id).status == 'paid'
        assert db.get(BillingOrder, order_id).amount_rub == 1990
        assert db.query(AuditLog).filter_by(action='subscription.admin_revoke').count() == 1
    assert client.post(f'/admin/commerce/organizations/{org}/revoke', headers=admin, json={**revoke, 'expected_updated_at': response.json()['updated_at']}).status_code == 200
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action='subscription.admin_revoke').count() == 1


def test_admin_listing_is_bounded_and_provider_subscription_requires_handoff(client, SessionLocal):
    _user, _headers, org = org_user(client)
    admin = platform_admin(client, SessionLocal)
    with SessionLocal() as db:
        db.add(Subscription(organization_id=org, plan_code='artist_pro', status='active', billing_period='monthly', starts_at=now()-timedelta(days=40), current_period_end=now()-timedelta(days=1), provider='external', provider_subscription_id='external-recurring'))
        db.commit()
    result = client.get('/admin/commerce/organizations', headers=admin, params={'q': org, 'limit': 1}).json()
    row = result['items'][0]
    assert row['effective_status'] == 'expired' and row['subscription']['status'] == 'active'
    body = {'reason': 'Operator request', 'expected_updated_at': row['subscription']['updated_at']}
    assert client.post(f'/admin/commerce/organizations/{org}/revoke', headers=admin, json=body).status_code == 409
    assert client.get('/admin/commerce/organizations', headers=admin, params={'limit': 101}).status_code == 422
    assert client.get('/admin/commerce/organizations', headers=admin, params={'q': '%'}).json()['total'] == 0
    with SessionLocal() as db:
        assert db.query(Subscription).filter_by(organization_id=org).one().status == 'active'
        assert db.query(AuditLog).filter_by(action='subscription.admin_revoke').count() == 0
