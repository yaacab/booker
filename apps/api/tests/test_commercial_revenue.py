from datetime import datetime, timedelta, timezone

from booker_api.models import BillingOrder, Booking, BookingHold, Offer, OfferVersion, Payment
from booker_api.security import now
from tests.test_commerce import platform_admin
from tests.test_event_budget import offer_for
from tests.test_matching import setup_matching


def test_revenue_separates_money_quotes_tests_and_unknown_fees(client, SessionLocal):
    ctx = setup_matching(client); offer = offer_for(client, SessionLocal, ctx)
    admin = platform_admin(client, SessionLocal)
    moment = datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc)  # 15 September in Moscow
    with SessionLocal() as db:
        booking = db.get(Booking, offer['booking_id']); booking.status = 'Confirmed'; booking.created_at = moment
        version = OfferVersion(offer_id=offer['id'], honorarium_rub=offer['version']['honorarium_rub'], commission_rate=0, commission_rub=0, total_rub=offer['version']['honorarium_rub'])
        db.add(version); db.flush(); db.get(Offer, offer['id']).active_version_id = version.id
        for provider, status, amount in [('external', 'succeeded', 100), ('stub', 'succeeded', 900), ('external', 'pending', 50), ('unknown', 'succeeded', 700), ('external', 'refunded', 20)]:
            db.add(Payment(booking_id=booking.id, provider=provider, status=status, amount_rub=amount, idempotency_key=f'{provider}-{status}', created_at=moment))
        db.add(BillingOrder(organization_id=ctx['customer']['id'], product_kind='subscription', product_code='customer_business', amount_rub=4990, status='paid', provider='stub', idempotency_key='sub', created_at=moment))
        db.add(BillingOrder(organization_id=ctx['customer']['id'], product_kind='promotion', product_code='BOOST_24H', amount_rub=300, status='refunded', provider='external', idempotency_key='promo', created_at=moment))
        db.commit()
    params = {'date_from': '2026-09-15', 'date_to': '2026-09-15'}
    assert client.get('/admin/commerce/revenue', headers=ctx['headers'], params=params).status_code == 403
    response = client.get('/admin/commerce/revenue', headers=admin, params=params)
    assert response.status_code == 200, response.text
    data = response.json()
    recorded = [r for r in data['payments'] if r['source'] == 'recorded' and r['status'] == 'succeeded']
    assert recorded[0]['amount_rub'] == 100 and recorded[0]['count'] == 1
    assert sum(r['amount_rub'] for r in data['payments'] if r['source'] == 'test') == 900
    assert data['booking_values'][0]['source'] == 'mixed'
    assert data['booking_values'][0]['bookings'] == 1  # multiple payment attempts never multiply GMV
    assert data['booking_values'][0]['gmv_known_rub'] == offer['version']['honorarium_rub']
    assert data['booking_values'][0]['missing_fee_snapshots'] == 1
    assert {r['product_kind'] for r in data['orders']} == {'subscription', 'promotion'}
    before = client.get('/admin/commerce/revenue', headers=admin, params={'date_from': '2026-09-14', 'date_to': '2026-09-14'}).json()
    assert before['payments'] == [] and before['orders'] == []
    assert client.get('/admin/commerce/revenue', headers=admin, params={'date_from': '2020-01-01', 'date_to': '2026-09-15'}).status_code == 422

    with SessionLocal() as db:
        booking = db.get(Booking, offer['booking_id']); booking.status = 'AwaitingPayment'; db.commit()
    no_hold = client.get('/admin/commerce/revenue', headers=admin, params=params).json()
    assert all(r['bookings'] == 0 for r in no_hold['booking_values'])
    with SessionLocal() as db:
        booking = db.get(Booking, offer['booking_id'])
        db.add(BookingHold(booking_id=booking.id, slot_id=booking.slot_id, status='active', expires_at=now()+timedelta(hours=1))); db.commit()
    reserved = client.get('/admin/commerce/revenue', headers=admin, params=params).json()
    assert reserved['booking_values'][1]['bookings'] == 1


def test_campaign_listing_shows_expired_and_payment_review_without_mutation(client, SessionLocal):
    from booker_api.models import PromotionCampaign
    ctx = setup_matching(client); admin = platform_admin(client, SessionLocal)
    with SessionLocal() as db:
        order = BillingOrder(organization_id=ctx['supply']['id'], product_kind='promotion', product_code='BOOST_24H', amount_rub=300, status='paid', provider='stub', idempotency_key='rejected-paid')
        db.add(order); db.flush()
        rejected = PromotionCampaign(organization_id=ctx['supply']['id'], target_type='artist', target_id=ctx['artists'][0]['id'], product_code='BOOST_24H', status='rejected', starts_at=now(), ends_at=now()+timedelta(days=1), billing_order_id=order.id)
        stale = PromotionCampaign(organization_id=ctx['supply']['id'], target_type='artist', target_id=ctx['artists'][0]['id'], product_code='BOOST_24H', status='active', starts_at=now()-timedelta(days=2), ends_at=now()-timedelta(days=1))
        db.add_all([rejected, stale]); db.commit(); stale_id = stale.id
    assert client.get('/admin/commerce/campaigns', headers=ctx['headers']).status_code == 403
    rejected = client.get('/admin/commerce/campaigns', headers=admin, params={'state': 'rejected'}).json()
    assert rejected['total'] == 1 and rejected['items'][0]['requires_payment_review']
    expired = client.get('/admin/commerce/campaigns', headers=admin, params={'state': 'expired', 'limit': 1}).json()
    assert expired['total'] == 1 and expired['items'][0]['status'] == 'expired'
    assert not expired['items'][0]['included_credit']
    assert client.get('/admin/commerce/campaigns', headers=admin, params={'state': 'active'}).json()['total'] == 0
    with SessionLocal() as db:
        assert db.get(PromotionCampaign, stale_id).status == 'active'
    assert client.get('/admin/commerce/campaigns', headers=admin, params={'limit': 101}).status_code == 422
