from datetime import datetime, timedelta, timezone

from booker_api.config import settings
from tests.conftest import auth_header
from tests.test_offers import ack_both, setup_negotiation


def test_parallel_hold_conflict(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    first = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert first.status_code == 200
    second = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert second.status_code == 409


def test_expired_hold_frees_slot(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    held = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert held.status_code == 200
    SessionLocal = client.app.state.SessionLocal
    db = SessionLocal()
    try:
        from booker_api.models import BookingHold

        hold = db.query(BookingHold).one()
        hold.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()
    expired = client.post(
        "/holds/expire",
        headers={"X-Internal-Token": settings.webhook_secret},
    )
    assert expired.status_code == 200
    assert expired.json()["expired"] == 1
    artist = client.get(f"/artists/{ctx['artist']['id']}").json()
    assert artist["slots"][0]["status"] == "open"
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["status"] == "Cancelled"
    assert any("истекло" in m["body"].lower() for m in room["messages"])
