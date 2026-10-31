from booker_api.models import Booking
from tests.test_offers import setup_negotiation


def test_profile_completed_count_excludes_unfinished_bookings(client, SessionLocal):
    ctx = setup_negotiation(client)
    with SessionLocal() as db:
        booking = db.get(Booking, ctx["booking_id"])
        booking.status = "Confirmed"
        db.commit()
    assert client.get(f"/artists/{ctx['artist']['id']}").json()["facts"]["deals"] == 0
    with SessionLocal() as db:
        db.get(Booking, ctx["booking_id"]).status = "Completed"
        db.commit()
    assert client.get(f"/artists/{ctx['artist']['id']}").json()["facts"]["deals"] == 1
