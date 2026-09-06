"""W4-MSG-HUB: message inbox across deal rooms."""

from datetime import timedelta

from booker_api.security import now
from tests.conftest import auth_header, register


def _deal_ctx(client):
    customer = register(client, "msg-cust@booker.test", "Клиент")
    owner = register(client, "msg-owner@booker.test", "Артист")
    ch = auth_header(customer["token"])
    oh = auth_header(owner["token"])
    cust_org = client.post("/orgs", json={"name": "Клиент MSG", "kind": "customer"}, headers=ch).json()
    artist_org = client.post("/orgs", json={"name": "Шоу MSG", "kind": "artist"}, headers=oh).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Msg", "category": "dj"},
        headers=oh,
    ).json()
    day = (now() + timedelta(days=10)).astimezone().replace(hour=18, minute=0, second=0, microsecond=0)
    starts = day.isoformat()
    ends = (day + timedelta(hours=3)).isoformat()
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts,
            "ends_at": ends,
        },
        headers=oh,
    ).json()
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Вечер MSG",
            "event_date": starts,
            "requirements": [{"category_code": "dj", "qty": 1}],
        },
        headers=ch,
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "requirement_id": event["requirements"][0]["id"],
        },
        headers=ch,
    ).json()
    offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 50000, "slot_id": slot["id"]},
        headers=oh,
    ).json()
    return {
        "ch": ch,
        "oh": oh,
        "booking_id": offer["booking_id"],
        "stranger": auth_header(register(client, "msg-x@booker.test", "Чужой")["token"]),
    }


def test_messages_inbox_lists_accessible_threads(client):
    ctx = _deal_ctx(client)
    posted = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Привет из deal room"},
        headers=ctx["ch"],
    )
    assert posted.status_code == 200, posted.text

    inbox = client.get("/messages/inbox", headers=ctx["ch"])
    assert inbox.status_code == 200, inbox.text
    items = inbox.json()["items"]
    assert any(i["booking_id"] == ctx["booking_id"] for i in items)
    hit = next(i for i in items if i["booking_id"] == ctx["booking_id"])
    assert hit["deal_path"] == f"/deals/{ctx['booking_id']}"
    assert hit["last_message"]["body"].startswith("Привет")

    supply = client.get("/messages/inbox", headers=ctx["oh"])
    assert supply.status_code == 200
    assert any(i["booking_id"] == ctx["booking_id"] for i in supply.json()["items"])

    empty = client.get("/messages/inbox", headers=ctx["stranger"])
    assert empty.status_code == 200
    assert empty.json()["items"] == []
