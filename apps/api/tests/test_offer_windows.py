from datetime import timedelta

import pytest

from booker_api.models import AvailabilitySlot, Booking, BookingHold, Event, Offer
from booker_api.security import aware, now
from tests.test_event_budget import offer_for
from tests.test_hold_authorization import acknowledged
from tests.test_matching import setup_matching


@pytest.mark.parametrize('problem', ['unknown_end', 'past', 'short', 'wrong_day', 'busy', 'setup'])
@pytest.mark.parametrize('stage', ['offer', 'hold'])
def test_direct_commands_reject_invalid_event_windows(client, SessionLocal, problem, stage):
    ctx = setup_matching(client)
    index = 1 if problem == 'setup' else 0
    resource = ctx['artists'][index]['id']
    if stage == 'hold':
        offer = offer_for(client, SessionLocal, ctx, index)
        acknowledged(client, ctx, offer)
        with SessionLocal() as db:
            req_id = db.get(Offer, offer['id']).request_id
    else:
        response = client.post(f"/events/{ctx['event']['id']}/requests", headers=ctx['headers'], json={'resource_type': 'artist', 'resource_id': resource})
        assert response.status_code == 200, response.text
        req_id = response.json()['id']
    with SessionLocal() as db:
        event = db.get(Event, ctx['event']['id'])
        slot = db.query(AvailabilitySlot).filter_by(resource_id=resource).one()
        slot_id = slot.id
        if problem == 'unknown_end':
            event.ends_at = None
        elif problem == 'past':
            event.event_date = now()-timedelta(hours=2); event.ends_at = now()-timedelta(hours=1)
        elif problem == 'short':
            slot.ends_at = aware(event.ends_at)-timedelta(minutes=1)
        elif problem == 'wrong_day':
            slot.starts_at = aware(slot.starts_at)-timedelta(days=1)
            slot.ends_at = aware(slot.ends_at)-timedelta(days=1)
        elif problem == 'busy':
            db.add(AvailabilitySlot(resource_type='artist', resource_id=resource, starts_at=event.event_date, ends_at=event.ends_at, status='busy'))
        elif problem == 'setup':
            slot.starts_at = event.event_date; slot.ends_at = event.ends_at
            slot.buffer_before_min = 0; slot.buffer_after_min = 0
        db.commit()
    response = client.post(f"/requests/{req_id}/offers" if stage == 'offer' else f"/bookings/{offer['booking_id']}/hold", headers=ctx['headers'], json={'honorarium_rub': 70000, 'slot_id': slot_id})
    assert response.status_code == 409, response.text
    with SessionLocal() as db:
        assert db.query(BookingHold).count() == 0
        assert db.get(AvailabilitySlot, slot_id).status == 'open'
        assert db.query(Offer).count() == (1 if stage == 'hold' else 0)
        if stage == 'hold':
            assert db.get(Booking, offer['booking_id']).status == 'Negotiation'


def test_legacy_missing_end_can_be_filled_before_hold(client, SessionLocal):
    ctx = setup_matching(client)
    offer = offer_for(client, SessionLocal, ctx)
    acknowledged(client, ctx, offer)
    with SessionLocal() as db:
        db.get(Event, ctx['event']['id']).ends_at = None; db.commit()
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=ctx['headers']).status_code == 409
    current = client.get(ctx['path'], headers=ctx['headers']).json()
    response = client.patch(f"/events/{ctx['event']['id']}/planning-context", headers=ctx['headers'], json={'expected_context': current['context_token'], 'ends_at': ctx['end'].isoformat()})
    assert response.status_code == 200, response.text
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=ctx['headers']).status_code == 200


def test_atomic_hold_rejects_short_hall_window_without_partial_reserve(client, SessionLocal):
    from tests.test_event_readiness import venue_offer

    ctx = setup_matching(client)
    offers = [offer_for(client, SessionLocal, ctx), venue_offer(client, SessionLocal, ctx)]
    for offer in offers:
        acknowledged(client, ctx, offer)
    with SessionLocal() as db:
        booking = db.get(Booking, offers[1]['booking_id'])
        db.get(AvailabilitySlot, booking.slot_id).ends_at = ctx['end']-timedelta(minutes=1)
        db.commit()
    response = client.post(f"/events/{ctx['event']['id']}/holds/atomic", headers=ctx['headers'], json={'booking_ids': [o['booking_id'] for o in offers]})
    assert response.status_code == 409, response.text
    with SessionLocal() as db:
        assert db.query(BookingHold).count() == 0
        for offer in offers:
            booking = db.get(Booking, offer['booking_id'])
            assert booking.status == 'Negotiation'
            assert db.get(AvailabilitySlot, booking.slot_id).status == 'open'
