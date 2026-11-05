"""V3: delete open slots; refuse offers/requests on busy-masked slots."""

from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, publish_artist, register
from tests.test_offers import ack_both, setup_negotiation


def _artist_with_open_slot(client, email="slot-v3@booker.test"):
    owner = register(client, email, "Owner")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "DJ Org", "kind": "artist"}, headers=headers
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ", "category": "dj"},
        headers=headers,
    ).json()
    starts = datetime.now(timezone.utc) + timedelta(days=12)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=3)).isoformat(),
        },
        headers=headers,
    )
    assert slot.status_code == 200, slot.text
    return owner, headers, org, artist, slot.json()


def test_delete_open_slot(client):
    _owner, headers, _org, artist, slot = _artist_with_open_slot(client)
    deleted = client.delete(f"/slots/{slot['id']}", headers=headers)
    assert deleted.status_code == 204
    page = client.get(f"/artists/{artist['id']}", headers=headers).json()
    assert all(item["id"] != slot["id"] for item in page["slots"])


def test_delete_held_slot_rejected(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    held = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert held.status_code == 200, held.text
    blocked = client.delete(
        f"/slots/{ctx['slot']['id']}",
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert blocked.status_code == 409


def test_offer_rejects_vacation_masked_slot(client):
    owner, headers, org, artist, slot = _artist_with_open_slot(
        client, "slot-busy-offer@booker.test"
    )
    publish_artist(client, owner, artist["id"])
    vacation = client.post(
        "/calendar/vacation",
        json={
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
            "ends_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
        },
        headers=headers,
    )
    assert vacation.status_code == 200, vacation.text

    customer = register(client, "slot-busy-cust@booker.test", "Customer")
    cust_headers = auth_header(customer["token"])
    cust_org = client.post(
        "/orgs", json={"name": "Cust", "kind": "customer"}, headers=cust_headers
    ).json()
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Corp",
            "event_date": (datetime.now(timezone.utc) + timedelta(days=12)).isoformat(),
            "guest_count": 40,
            "budget_rub": 120000,
        },
        headers=cust_headers,
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=cust_headers,
    )
    assert req.status_code == 200, req.text
    offer = client.post(
        f"/requests/{req.json()['id']}/offers",
        json={"honorarium_rub": 80000, "slot_id": slot["id"], "terms": "busy"},
        headers=headers,
    )
    assert offer.status_code == 409


def test_quick_request_rejects_vacation_masked_slot(client):
    owner, headers, org, artist, slot = _artist_with_open_slot(
        client, "slot-busy-quick@booker.test"
    )
    publish_artist(client, owner, artist["id"])
    assert (
        client.post(
            "/calendar/vacation",
            json={
                "organization_id": org["id"],
                "resource_type": "artist",
                "resource_id": artist["id"],
                "starts_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
                "ends_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
            },
            headers=headers,
        ).status_code
        == 200
    )
    customer = register(client, "slot-busy-quick-c@booker.test", "Customer")
    client.post(
        "/orgs",
        json={"name": "Cust2", "kind": "customer"},
        headers=auth_header(customer["token"]),
    )
    quick = client.post(
        "/quick-request",
        json={"artist_id": artist["id"], "slot_id": slot["id"], "title": "Party"},
        headers=auth_header(customer["token"]),
    )
    assert quick.status_code == 409
