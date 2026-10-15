"""Deepened acceptance gaps C04 (messaging) and C08 (hold exclusivity under threads).

LOCAL level only — does not close staging T12/P06.
"""

from __future__ import annotations

import concurrent.futures
import time

from tests.conftest import auth_header
from tests.test_hold_race import setup_same_slot_negotiations
from tests.test_messages_inbox import _deal_ctx


def test_c04_deal_message_create_peer_sees_reload_stranger_denied(client):
    """Create → peer deal-room reload → customer reload → stranger denied."""
    ctx = _deal_ctx(client)
    booking_id = ctx["booking_id"]
    body = f"c04-roundtrip-{time.time_ns()}"

    posted = client.post(
        f"/deal-room/{booking_id}/messages",
        json={"body": body, "idempotency_key": f"c04-{time.time_ns()}"},
        headers=ctx["ch"],
    )
    assert posted.status_code == 200, posted.text
    message_id = posted.json()["id"]

    peer_room = client.get(f"/deal-room/{booking_id}", headers=ctx["oh"])
    assert peer_room.status_code == 200, peer_room.text
    peer_bodies = [m["body"] for m in peer_room.json()["messages"]]
    assert body in peer_bodies
    assert any(m["id"] == message_id for m in peer_room.json()["messages"])

    reload_room = client.get(f"/deal-room/{booking_id}", headers=ctx["ch"])
    assert reload_room.status_code == 200
    assert any(
        m["id"] == message_id and m["body"] == body
        for m in reload_room.json()["messages"]
    )

    stranger_room = client.get(f"/deal-room/{booking_id}", headers=ctx["stranger"])
    assert stranger_room.status_code == 403

    stranger_post = client.post(
        f"/deal-room/{booking_id}/messages",
        json={"body": "intrusion", "idempotency_key": f"c04-bad-{time.time_ns()}"},
        headers=ctx["stranger"],
    )
    assert stranger_post.status_code in (403, 404)


def test_c08_threaded_hold_exclusivity_same_slot(client):
    """Fire two holds concurrently via threads; still exactly one active hold.

    SQLite + TestClient is not a production race harness; this only stresses
    exclusivity under overlapping requests. Postgres staging race remains open.
    """
    suffix = str(time.time_ns())
    ctx = setup_same_slot_negotiations(client, suffix)
    results: list[int] = []

    def _hold(booking_id: str, token: str) -> int:
        response = client.post(
            f"/bookings/{booking_id}/hold",
            headers=auth_header(token),
        )
        return response.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_hold, ctx["booking_id"], ctx["customer"]["token"]),
            pool.submit(_hold, ctx["booking_id_2"], ctx["customer2"]["token"]),
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert sorted(results) == [200, 409], results

    from booker_api.models import BookingHold

    db = client.app.state.SessionLocal()
    try:
        active = db.query(BookingHold).filter(BookingHold.status == "active").all()
        assert len(active) == 1
    finally:
        db.close()
