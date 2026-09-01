"""Concurrent hold on the same slot — only one booking must win."""

import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from booker_api.db import get_db
from booker_api.main import app
from tests.conftest import auth_header, register
from tests.test_offers import ack_both, setup_negotiation


def setup_same_slot_negotiations(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)

    customer2 = register(client, "c-race2@booker.test", "Клиент2")
    client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": customer2["user_id"], "role": "manager"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    event2 = client.post(
        "/events",
        json={
            "organization_id": ctx["cust_org"]["id"],
            "title": "Другой корпоратив",
            "event_date": "2026-09-01T18:00:00+00:00",
            "guest_count": 60,
            "budget_rub": 150000,
        },
        headers=auth_header(customer2["token"]),
    ).json()
    req2 = client.post(
        f"/events/{event2['id']}/requests",
        json={"resource_type": "artist", "resource_id": ctx["artist"]["id"]},
        headers=auth_header(customer2["token"]),
    ).json()
    offer2 = client.post(
        f"/requests/{req2['id']}/offers",
        json={"honorarium_rub": 95000, "slot_id": ctx["slot"]["id"], "terms": "race"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert offer2.status_code == 200, offer2.text
    data = offer2.json()
    client.post(
        f"/offers/{data['id']}/ack",
        json={"side": "supplier"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    ack = client.post(
        f"/offers/{data['id']}/ack",
        json={"side": "customer"},
        headers=auth_header(customer2["token"]),
    )
    assert ack.status_code == 200
    return {**ctx, "customer2": customer2, "booking_id_2": data["booking_id"]}


def test_concurrent_hold_same_slot_only_one_succeeds(client):
    ctx = setup_same_slot_negotiations(client)
    SessionLocal = client.app.state.SessionLocal

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override

    barrier = threading.Barrier(2)
    results: list[int] = []
    lock = threading.Lock()

    def hold(booking_id: str, token: str) -> None:
        tc = TestClient(app)
        barrier.wait(timeout=5)
        res = tc.post(
            f"/bookings/{booking_id}/hold",
            headers=auth_header(token),
        )
        with lock:
            results.append(res.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(hold, ctx["booking_id"], ctx["customer"]["token"])
        pool.submit(hold, ctx["booking_id_2"], ctx["customer2"]["token"])
        pool.shutdown(wait=True)

    assert sorted(results) == [200, 409], f"unexpected status codes: {results}"

    db = SessionLocal()
    try:
        from booker_api.models import BookingHold

        active = db.query(BookingHold).filter(BookingHold.status == "active").all()
        assert len(active) == 1
    finally:
        db.close()
