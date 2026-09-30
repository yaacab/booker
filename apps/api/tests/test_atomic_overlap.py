from booker_api.models import AvailabilitySlot, Booking, BookingHold
from tests.test_event_budget import offer_for
from tests.test_hold_authorization import acknowledged
from tests.test_matching import setup_matching


def test_atomic_rejects_legacy_overlapping_slots(client, SessionLocal):
    ctx = setup_matching(client)
    first = offer_for(client, SessionLocal, ctx)
    with SessionLocal() as db:
        booking = db.get(Booking, first['booking_id'])
        original = db.get(AvailabilitySlot, booking.slot_id)
        duplicate = AvailabilitySlot(resource_type=original.resource_type, resource_id=original.resource_id, starts_at=original.starts_at, ends_at=original.ends_at, status='open')
        db.add(duplicate); db.commit(); second_slot_id = duplicate.id
    req = client.post(f"/events/{ctx['event']['id']}/requests", headers=ctx['headers'], json={'resource_type': 'artist', 'resource_id': ctx['artists'][0]['id']}).json()
    response = client.post(f"/requests/{req['id']}/offers", headers=ctx['headers'], json={'slot_id': second_slot_id, 'honorarium_rub': 70000})
    assert response.status_code == 200, response.text
    second = response.json()
    for offer in [first, second]:
        acknowledged(client, ctx, offer)
    response = client.post(f"/events/{ctx['event']['id']}/holds/atomic", headers=ctx['headers'], json={'booking_ids': [first['booking_id'], second['booking_id']]})
    assert response.status_code == 409, response.text
    with SessionLocal() as db:
        assert db.query(BookingHold).filter_by(status='active').count() == 0
        for offer in [first, second]:
            booking = db.get(Booking, offer['booking_id'])
            assert booking.status == 'Negotiation'
            assert db.get(AvailabilitySlot, booking.slot_id).status == 'open'
