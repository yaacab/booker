"""E10: atomic multi-hall (multi-booking) hold — no partial capture."""

from tests.conftest import auth_header, register
from tests.test_offers import ack_both


def _setup_two_hall_package(client):
    customer = register(client, "c-mh@booker.test", "Клиент")
    owner = register(client, "o-mh@booker.test", "Площадка")
    cust_org = client.post(
        "/orgs",
        json={"name": "Заказчик MH", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    venue_org = client.post(
        "/orgs",
        json={"name": "Площадка MH", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": venue_org["id"], "name": "Два зала", "city": "Москва", "capacity": 200},
        headers=auth_header(owner["token"]),
    ).json()
    hall_a = venue["hall_id"]
    hall_b = client.post(
        f"/venues/{venue['id']}/halls",
        json={"name": "Зал B", "capacity": 80},
        headers=auth_header(owner["token"]),
    ).json()["id"]

    slots = []
    for hall_id in (hall_a, hall_b):
        slot = client.post(
            "/slots",
            json={
                "resource_type": "hall",
                "resource_id": hall_id,
                "starts_at": "2026-12-01T18:00:00+00:00",
                "ends_at": "2026-12-01T22:00:00+00:00",
            },
            headers=auth_header(owner["token"]),
        ).json()
        slots.append(slot)

    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Два зала обязательны",
            "event_date": "2026-12-01T18:00:00+00:00",
            "guest_count": 150,
            "budget_rub": 400000,
        },
        headers=auth_header(customer["token"]),
    ).json()

    booking_ids = []
    offers = []
    for hall_id, slot in zip((hall_a, hall_b), slots, strict=True):
        req_res = client.post(
            f"/events/{event['id']}/requests",
            json={"resource_type": "hall", "resource_id": hall_id},
            headers=auth_header(customer["token"]),
        )
        assert req_res.status_code == 200, req_res.text
        req = req_res.json()
        offer = client.post(
            f"/requests/{req['id']}/offers",
            json={"honorarium_rub": 50000, "slot_id": slot["id"], "terms": "зал"},
            headers=auth_header(owner["token"]),
        )
        assert offer.status_code == 200, offer.text
        data = offer.json()
        offers.append(data)
        booking_ids.append(data["booking_id"])
        ack_both(
            client,
            {
                "offer": data,
                "owner": owner,
                "customer": customer,
            },
        )

    return {
        "customer": customer,
        "owner": owner,
        "event": event,
        "slots": slots,
        "booking_ids": booking_ids,
        "offers": offers,
        "hall_a": hall_a,
        "hall_b": hall_b,
    }


def test_atomic_multi_hall_hold_succeeds(client):
    ctx = _setup_two_hall_package(client)
    res = client.post(
        f"/events/{ctx['event']['id']}/holds/atomic",
        json={"booking_ids": ctx["booking_ids"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert len(body["holds"]) == 2
    for slot in ctx["slots"]:
        # re-fetch via deal room / slot status through public hall is heavy; check booking status
        pass
    for bid in ctx["booking_ids"]:
        room = client.get(
            f"/deal-room/{bid}",
            headers=auth_header(ctx["customer"]["token"]),
        ).json()
        assert room["status"] == "DateHeld"


def test_atomic_multi_hall_no_partial_on_conflict(client):
    """E10: if one hall slot in the set is busy, none of the package is captured."""
    ctx = _setup_two_hall_package(client)
    SessionLocal = client.app.state.SessionLocal
    db = SessionLocal()
    try:
        from booker_api.models import AvailabilitySlot

        slot_b = db.get(AvailabilitySlot, ctx["slots"][1]["id"])
        assert slot_b is not None
        slot_b.status = "held"
        db.commit()
    finally:
        db.close()

    conflict = client.post(
        f"/events/{ctx['event']['id']}/holds/atomic",
        json={"booking_ids": ctx["booking_ids"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert conflict.status_code == 409, conflict.text

    for bid in ctx["booking_ids"]:
        room = client.get(
            f"/deal-room/{bid}",
            headers=auth_header(ctx["customer"]["token"]),
        ).json()
        assert room["status"] == "Negotiation"

    db = SessionLocal()
    try:
        from booker_api.models import AvailabilitySlot

        slot_a = db.get(AvailabilitySlot, ctx["slots"][0]["id"])
        assert slot_a is not None
        assert slot_a.status == "open"
    finally:
        db.close()
