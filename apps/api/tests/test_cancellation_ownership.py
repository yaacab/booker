import pytest

from booker_api.models import AvailabilitySlot, Booking, BookingHold
from tests.conftest import auth_header
from tests.test_hold_race import setup_same_slot_negotiations


@pytest.mark.parametrize('reservation', ['held', 'confirmed'])
def test_cancelling_unreserved_alternative_keeps_other_booking(client, SessionLocal, reservation):
    ctx = setup_same_slot_negotiations(client, reservation)
    held = client.post(f"/bookings/{ctx['booking_id']}/hold", headers=auth_header(ctx['customer']['token']))
    assert held.status_code == 200, held.text
    if reservation == 'confirmed':
        with SessionLocal() as db:
            db.get(Booking, ctx['booking_id']).status = 'Confirmed'
            db.get(AvailabilitySlot, ctx['slot']['id']).status = 'confirmed'
            db.query(BookingHold).filter_by(booking_id=ctx['booking_id']).one().status = 'consumed'
            db.commit()
    response = client.post(f"/bookings/{ctx['booking_id_2']}/cancel", headers=auth_header(ctx['customer2']['token']))
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.get(AvailabilitySlot, ctx['slot']['id']).status == reservation
        assert db.get(Booking, ctx['booking_id']).status == ('DateHeld' if reservation == 'held' else 'Confirmed')
        assert db.query(BookingHold).filter_by(booking_id=ctx['booking_id']).one().status == ('active' if reservation == 'held' else 'consumed')
        assert db.get(Booking, ctx['booking_id_2']).status == 'Cancelled'
    own_cancel = client.post(f"/bookings/{ctx['booking_id']}/cancel", headers=auth_header(ctx['customer']['token']))
    assert own_cancel.status_code == 200, own_cancel.text
    with SessionLocal() as db:
        assert db.get(AvailabilitySlot, ctx['slot']['id']).status == 'open'
