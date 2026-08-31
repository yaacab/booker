from tests.conftest import auth_header, register


def setup_negotiation(client):
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
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-09-01T18:00:00+00:00",
            "ends_at": "2026-09-01T22:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    ).json()
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Корпоратив",
            "event_date": "2026-09-01T18:00:00+00:00",
            "guest_count": 80,
            "budget_rub": 200000,
        },
        headers=auth_header(customer["token"]),
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=auth_header(customer["token"]),
    ).json()
    offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 100000, "slot_id": slot["id"], "terms": "2 часа сет"},
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
    }


def ack_both(client, ctx):
    offer_id = ctx["offer"]["id"]
    client.post(
        f"/offers/{offer_id}/ack",
        json={"side": "supplier"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    res = client.post(
        f"/offers/{offer_id}/ack",
        json={"side": "customer"},
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
        json={"side": "customer"},
        headers=auth_header(cust_viewer["token"]),
    )
    assert denied_ack.status_code == 403
    denied_version = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 80000},
        headers=auth_header(viewer["token"]),
    )
    assert denied_version.status_code == 403
