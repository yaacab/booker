from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from tests.conftest import auth_header, publish_artist, publish_venue, register


def setup_negotiation(client, offer_overrides=None):
    customer = register(client, "c-off@booker.test", "Клиент")
    owner = register(client, "o-off@booker.test", "Артист")
    cust_org = client.post(
        "/orgs",
        json={"name": "Заказчик", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Nova", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    starts_at = datetime.now(timezone.utc) + timedelta(days=10)
    starts_at = starts_at.replace(hour=18, minute=0, second=0, microsecond=0)
    ends_at = starts_at + timedelta(hours=4)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
        headers=auth_header(owner["token"]),
    ).json()
    publish_artist(client, owner, artist["id"])
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Корпоратив",
            "event_date": starts_at.isoformat(),
            "guest_count": 80,
            "budget_rub": 200000,
            "requirements": [{"category_code": "dj", "qty": 1, "required": True}],
        },
        headers=auth_header(customer["token"]),
    ).json()
    requirement_id = event["requirements"][0]["id"]
    req = client.post(
        f"/events/{event['id']}/requests",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "requirement_id": requirement_id,
        },
        headers=auth_header(customer["token"]),
    ).json()
    offer_body = {"honorarium_rub": 100000, "slot_id": slot["id"], "terms": "2 часа сет"}
    offer_body.update(offer_overrides or {})
    if "payment_terms" not in offer_body:
        explicit_terms = {}
        advance = int(offer_body.get("advance_rub") or offer_body["honorarium_rub"])
        if advance < int(offer_body["honorarium_rub"]):
            explicit_terms["balance"] = {
                "due_at": (starts_at - timedelta(days=2)).isoformat(),
                "grace_until": (starts_at - timedelta(days=1)).isoformat(),
                "required_before_check_in": True,
            }
        if int(offer_body.get("security_deposit_rub") or 0) > 0:
            explicit_terms["security_deposit"] = {
                "due_at": (starts_at - timedelta(days=2)).isoformat(),
                "grace_until": (starts_at - timedelta(days=1)).isoformat(),
                "required_before_check_in": True,
            }
        if explicit_terms:
            offer_body["payment_terms"] = explicit_terms
    offer = client.post(
        f"/requests/{req['id']}/offers",
        json=offer_body,
        headers=auth_header(owner["token"]),
    )
    assert offer.status_code == 200, offer.text
    data = offer.json()
    return {
        "customer": customer,
        "owner": owner,
        "slot": slot,
        "offer": data,
        "booking_id": data["booking_id"],
        "artist": artist,
        "cust_org": cust_org,
        "artist_org": artist_org,
        "event": event,
        "request": req,
    }


def ack_both(client, ctx):
    offer_id = ctx["offer"]["id"]
    booking_id = ctx.get("booking_id") or ctx["offer"]["booking_id"]
    room = client.get(
        f"/deal-room/{booking_id}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    quote_id = room["quote"]["quote_id"]
    client.post(
        f"/offers/{offer_id}/ack",
        json={"side": "supplier", "quote_id": quote_id},
        headers=auth_header(ctx["owner"]["token"]),
    )
    res = client.post(
        f"/offers/{offer_id}/ack",
        json={"side": "customer", "quote_id": quote_id},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert res.status_code == 200
    return res.json()


def test_price_only_from_server(client):
    ctx = setup_negotiation(client)
    version = ctx["offer"]["version"]
    assert version["honorarium_rub"] == 100000
    assert version["commission_rate"] == 0.0
    assert version["commission_rub"] == 0
    assert version["total_rub"] == 100000
    assert version["quote_id"] == version["id"]
    assert version["advance_rub"] == 100000
    assert version["balance_rub"] == 0
    assert version["security_deposit_rub"] == 0


def test_server_validates_and_snapshots_payment_schedule(client):
    ctx = setup_negotiation(
        client,
        {"advance_rub": 40000, "security_deposit_rub": 15000},
    )
    version = ctx["offer"]["version"]
    assert version["advance_rub"] == 40000
    assert version["balance_rub"] == 60000
    assert version["security_deposit_rub"] == 15000
    assert version["payment_terms"]["balance"]["required_before_check_in"] is True
    assert version["payment_terms"]["security_deposit"]["required_before_check_in"] is True
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    obligations = {row["kind"]: row for row in room["payment_obligations"]}
    assert {kind: (row["amount_rub"], row["status"]) for kind, row in obligations.items()} == {
        "advance": (40000, "pending"),
        "balance": (60000, "pending"),
        "security_deposit": (15000, "pending"),
    }
    assert obligations["balance"]["due_at"] is not None
    assert obligations["balance"]["grace_until"] is not None
    assert obligations["balance"]["effective_state"] == "pending"
    assert obligations["balance"]["required_before_check_in"] is True

    invalid = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 100000, "advance_rub": 100001},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert invalid.status_code == 400


def test_payment_schedule_snapshot_and_deadlines_are_database_immutable(client):
    ctx = setup_negotiation(client, {"advance_rub": 40000})
    version_id = ctx["offer"]["version"]["id"]
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    balance = next(row for row in room["payment_obligations"] if row["kind"] == "balance")

    with client.app.state.SessionLocal() as db:
        with pytest.raises(DatabaseError):
            db.execute(
                text("UPDATE offer_versions SET payment_terms_json = '{}' WHERE id = :id"),
                {"id": version_id},
            )
            db.commit()
        db.rollback()
        with pytest.raises(DatabaseError):
            db.execute(
                text("UPDATE payment_obligations SET grace_until = NULL WHERE id = :id"),
                {"id": balance["id"]},
            )
            db.commit()


def test_new_version_not_active_until_ack(client):
    ctx = setup_negotiation(client)
    first = ack_both(client, ctx)
    assert first["active"] is True
    updated = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 120000, "terms": "новая смета"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["honorarium_rub"] == 120000
    assert body["active"] is False
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["quote"]["honorarium_rub"] == 120000
    assert room["quote"]["customer_ack"] is False
    assert room["quote"]["supplier_ack"] is False
    assert room["quote"]["commission_rub"] == 0


def test_new_price_rejected_after_contract_was_issued(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    held = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert held.status_code == 200
    contract = client.post(
        f"/bookings/{ctx['booking_id']}/contract",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert contract.status_code == 200
    changed = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 120000, "terms": "Новая цена после договора"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert changed.status_code == 409
    assert contract.json()["body"].find(ctx["offer"]["version"]["quote_id"]) >= 0


def test_second_booking_gets_commission(client):
    ctx = setup_negotiation(client)
    slot2 = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": ctx["artist"]["id"],
            "starts_at": "2026-09-08T18:00:00+00:00",
            "ends_at": "2026-09-08T22:00:00+00:00",
        },
        headers=auth_header(ctx["owner"]["token"]),
    ).json()
    event2 = client.post(
        "/events",
        json={
            "organization_id": ctx["cust_org"]["id"],
            "title": "Ещё вечер",
            "event_date": "2026-09-08T18:00:00+00:00",
            "guest_count": 40,
        },
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    req2 = client.post(
        f"/events/{event2['id']}/requests",
        json={"resource_type": "artist", "resource_id": ctx["artist"]["id"]},
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    offer2 = client.post(
        f"/requests/{req2['id']}/offers",
        json={"honorarium_rub": 100000, "slot_id": slot2["id"]},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert offer2.status_code == 200, offer2.text
    version = offer2.json()["version"]
    assert version["commission_rate"] == 0.10
    assert version["commission_rub"] == 10000
    assert version["total_rub"] == 110000


def test_viewer_cannot_post_offer_or_ack(client):
    ctx = setup_negotiation(client)
    viewer = register(client, "view-off@booker.test", "View")
    client.post(
        f"/orgs/{ctx['artist_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    cust_viewer = register(client, "view-cust@booker.test", "CustView")
    client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": cust_viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    denied_offer = client.post(
        f"/requests/{client.get('/requests', headers=auth_header(ctx['owner']['token'])).json()['items'][0]['id']}/offers",
        json={"honorarium_rub": 90000, "slot_id": ctx["slot"]["id"]},
        headers=auth_header(viewer["token"]),
    )
    assert denied_offer.status_code == 403
    denied_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": "customer", "quote_id": ctx["offer"]["version"]["quote_id"]},
        headers=auth_header(cust_viewer["token"]),
    )
    assert denied_ack.status_code == 403
    denied_version = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 80000},
        headers=auth_header(viewer["token"]),
    )
    assert denied_version.status_code == 403


def test_venue_offer_accepts_hall_slot_of_same_venue(client):
    """Venue requests are resource_type=venue; open slots live on halls — must still match."""
    customer = register(client, "c-venue-off@booker.test", "Клиент")
    owner = register(client, "o-venue-off@booker.test", "Площадка")
    cust_org = client.post(
        "/orgs",
        json={"name": "Заказчик V", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    venue_org = client.post(
        "/orgs",
        json={"name": "Площадка V", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": venue_org["id"], "name": "Зал Оффер", "city": "Москва", "capacity": 100},
        headers=auth_header(owner["token"]),
    ).json()
    hall_id = venue.get("hall_id")
    if not hall_id:
        halls = client.get(f"/venues/{venue['id']}/halls", headers=auth_header(owner["token"])).json()["items"]
        hall_id = halls[0]["id"]
    starts = (datetime.now(timezone.utc) + timedelta(days=45)).replace(microsecond=0)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "hall",
            "resource_id": hall_id,
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=5)).isoformat(),
        },
        headers=auth_header(owner["token"]),
    ).json()
    publish_venue(client, owner, venue["id"])
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Вечер на площадке",
            "event_date": starts.isoformat(),
            "guest_count": 60,
            "budget_rub": 300000,
        },
        headers=auth_header(customer["token"]),
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "venue", "resource_id": venue["id"]},
        headers=auth_header(customer["token"]),
    ).json()
    listed = client.get("/requests", headers=auth_header(owner["token"])).json()["items"]
    match = next(i for i in listed if i["id"] == req["id"])
    assert match["slot_id"] == slot["id"]
    offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 150000, "slot_id": slot["id"]},
        headers=auth_header(owner["token"]),
    )
    assert offer.status_code == 200, offer.text
    assert offer.json()["booking_id"]
