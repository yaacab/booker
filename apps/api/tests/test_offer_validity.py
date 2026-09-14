from datetime import datetime, timedelta

import pytest

from booker_api.models import Booking, InboxNotification, OfferVersion
from booker_api.notifications.maintenance import run_maintenance
from booker_api.security import aware, now
from tests.test_event_budget import offer_for
from tests.test_hold_authorization import acknowledged
from tests.test_matching import setup_matching


def test_expired_quote_blocks_ack_and_hold_and_revision_recovers(client, SessionLocal):
    ctx = setup_matching(client)
    offer = offer_for(client, SessionLocal, ctx)
    assert now() < aware(datetime.fromisoformat(offer['version']['valid_until'])) <= now()+timedelta(hours=72)
    acknowledged(client, ctx, offer)
    with SessionLocal() as db:
        db.get(OfferVersion, offer['version']['id']).valid_until = now()-timedelta(seconds=1); db.commit()
    assert client.post(f"/offers/{offer['id']}/ack", headers=ctx['headers'], json={'side': 'customer', 'quote_id': offer['version']['id']}).status_code == 409
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=ctx['headers']).status_code == 409
    room = client.get(f"/deal-room/{offer['booking_id']}", headers=ctx['headers']).json()
    assert room['next_step'] == 'Согласовать новую версию условий'
    assert room['quote']['acceptance_expired'] and not room['can_hold'] and not room['can_ack_quote'] and room['can_revise_quote']
    readiness = client.get(f"/events/{ctx['event']['id']}/readiness", headers=ctx['headers'])
    assert readiness.status_code == 200, readiness.text
    participant = next(p for p in readiness.json()['participants'] if p['booking_id'] == offer['booking_id'])
    assert not participant['checks']['offers'] and not participant['checks']['acknowledged']

    with SessionLocal() as db:
        assert run_maintenance(db, limit=1)['offers_expired'] == 1; db.commit()
        assert run_maintenance(db, limit=1)['offers_expired'] == 0
        notes = db.query(InboxNotification).filter_by(template='offer.expired').all()
        assert len(notes) == 1 and notes[0].recipient_user_id == ctx['owner']['user_id']
        assert notes[0].href == f"/deals/{offer['booking_id']}"
    revised = client.post(f"/offers/{offer['id']}/versions", headers=ctx['headers'], json={'honorarium_rub': 99000, 'expected_quote_id': offer['version']['id'], 'valid_for_hours': 24})
    assert revised.status_code == 200, revised.text
    for side in ['customer', 'supplier']:
        assert client.post(f"/offers/{offer['id']}/ack", headers=ctx['headers'], json={'side': side, 'quote_id': revised.json()['id']}).status_code == 200
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=ctx['headers']).status_code == 200
    with SessionLocal() as db:
        assert db.get(OfferVersion, offer['version']['id']).honorarium_rub != 99000
        assert db.get(Booking, offer['booking_id']).status == 'DateHeld'


def test_held_terms_survive_acceptance_deadline_and_historical_quotes_stay_undated(client, SessionLocal):
    ctx = setup_matching(client); offer = offer_for(client, SessionLocal, ctx)
    with SessionLocal() as db:
        db.get(OfferVersion, offer['version']['id']).valid_until = None; db.commit()
    acknowledged(client, ctx, offer)
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=ctx['headers']).status_code == 200
    with SessionLocal() as db:
        db.get(OfferVersion, offer['version']['id']).valid_until = now()-timedelta(seconds=1); db.commit()
        assert run_maintenance(db)['offers_expired'] == 0
        assert db.query(InboxNotification).filter_by(template='offer.expired').count() == 0
    assert client.post(f"/bookings/{offer['booking_id']}/contract", headers=ctx['headers']).status_code == 200
    room = client.get(f"/deal-room/{offer['booking_id']}", headers=ctx['headers']).json()
    assert not room['quote']['acceptance_expired'] and not room['can_ack_quote']


@pytest.mark.parametrize('hours', [0, 721, True, '24', 1.5])
def test_invalid_deadline_is_rejected_without_new_version(client, SessionLocal, hours):
    ctx = setup_matching(client); offer = offer_for(client, SessionLocal, ctx)
    response = client.post(f"/offers/{offer['id']}/versions", headers=ctx['headers'], json={'honorarium_rub': 99000, 'valid_for_hours': hours})
    assert response.status_code == 400
    with SessionLocal() as db:
        assert db.query(OfferVersion).filter_by(offer_id=offer['id']).count() == 1


def test_deadline_is_rechecked_after_waiting_for_calendar(client, SessionLocal, monkeypatch):
    from booker_api import offer_validity
    from booker_api.routers import deals
    ctx = setup_matching(client); offer = offer_for(client, SessionLocal, ctx)
    acknowledged(client, ctx, offer)
    original = deals._lock_and_validate_slot
    later = now()+timedelta(days=4)
    def after_wait(*args, **kwargs):
        slot = original(*args, **kwargs)
        monkeypatch.setattr(offer_validity, 'now', lambda: later)
        return slot
    monkeypatch.setattr(deals, '_lock_and_validate_slot', after_wait)
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=ctx['headers']).status_code == 409
    with SessionLocal() as db:
        assert db.get(Booking, offer['booking_id']).status == 'Negotiation'
