from datetime import timedelta

from booker_api.models import (
    AvailabilitySlot,
    Booking,
    BookingHold,
    InboxNotification,
    Payment,
    PromotionCampaign,
    Subscription,
)
from booker_api.notifications.maintenance import run_maintenance
from booker_api.routers.deals import expire_holds
from booker_api.security import now
from tests.conftest import contract_otps
from tests.test_commerce import org_user
from tests.test_event_budget import offer_for
from tests.test_event_readiness import hold
from tests.test_matching import setup_matching


def notices(db, template):
    return db.query(InboxNotification).filter_by(template=template).all()


def test_bounded_commercial_expiry_recipient_and_period_dedupe(client, SessionLocal):
    user, _h, org = org_user(client)
    other, _oh, foreign = org_user(client, suffix='foreign')
    with SessionLocal() as db:
        for org_id, days in [(org, 2), (foreign, 1)]:
            db.add(Subscription(organization_id=org_id, plan_code='artist_pro', billing_period='monthly', status='active', starts_at=now()-timedelta(days=40), current_period_end=now()-timedelta(days=days)))
        db.add(PromotionCampaign(organization_id=org, target_type='artist', target_id='old-profile', product_code='BOOST_24H', starts_at=now()-timedelta(days=3), ends_at=now()-timedelta(days=2), status='active'))
        db.commit()
        result = run_maintenance(db, limit=1); db.commit()
        assert result == {'subscriptions_expired': 1, 'promotions_expired': 1, 'holds_expired': 0}
        rows = notices(db, 'subscription.expired')
        assert len(rows) == 1 and rows[0].recipient_user_id == user['user_id'] and f'organization={org}' in rows[0].href
        assert len(notices(db, 'promotion.expired')) == 1
        run_maintenance(db, limit=1); db.commit()
        assert {r.recipient_user_id for r in notices(db, 'subscription.expired')} == {user['user_id'], other['user_id']}
        assert run_maintenance(db, limit=1)['subscriptions_expired'] == 0
        sub = db.query(Subscription).filter_by(organization_id=org).one()
        sub.status = 'active'; sub.current_period_end = now()-timedelta(seconds=1); db.commit()
        run_maintenance(db); db.commit()
        assert len(notices(db, 'subscription.expired')) == 3


def test_hold_expiry_once_and_newer_hold_is_not_released(client, SessionLocal):
    ctx = setup_matching(client); offer = offer_for(client, SessionLocal, ctx)
    hold(client, ctx, offer)
    with SessionLocal() as db:
        old = db.query(BookingHold).filter_by(booking_id=offer['booking_id']).one()
        old.expires_at = now()-timedelta(seconds=1)
        newer = BookingHold(booking_id=old.booking_id, slot_id=old.slot_id, status='active', expires_at=now()+timedelta(hours=1))
        db.add(newer); db.commit()
        assert expire_holds(db, limit=1) == 1; db.commit()
        assert db.get(AvailabilitySlot, old.slot_id).status == 'held'
        assert db.get(Booking, offer['booking_id']).status == 'DateHeld'
        assert notices(db, 'hold.expired') == []
        newer.expires_at = now()-timedelta(seconds=1); db.commit()
        assert expire_holds(db) == 1; db.commit()
        assert db.get(AvailabilitySlot, old.slot_id).status == 'open'
        assert db.get(Booking, offer['booking_id']).status == 'Cancelled'
        assert len(notices(db, 'hold.expired')) == 1
        assert expire_holds(db) == 0


def test_payment_required_is_not_payment_and_cancel_links_replacement(client, SessionLocal):
    ctx = setup_matching(client); offer = offer_for(client, SessionLocal, ctx)
    hold(client, ctx, offer)
    contract = client.post(f"/bookings/{offer['booking_id']}/contract", headers=ctx['headers']).json()
    otps = contract_otps(SessionLocal, contract['id'])
    for side in ['customer', 'supplier', 'supplier']:
        response = client.post(f"/contracts/{contract['id']}/sign", headers=ctx['headers'], json={'side': side, 'otp': otps[f'otp_{side}']})
        assert response.status_code == 200, response.text
    with SessionLocal() as db:
        rows = notices(db, 'payment.required'); assert len(rows) == 1
        assert rows[0].href == f"/deals/{offer['booking_id']}"
        assert db.query(Payment).count() == 0
    response = client.post(f"/bookings/{offer['booking_id']}/cancel", headers=ctx['headers'])
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert len(notices(db, 'booking.cancelled')) == 1
        replacement = notices(db, 'replacement.required'); assert len(replacement) == 1
        assert replacement[0].href == f"/events/{ctx['event']['id']}#event-roles"
