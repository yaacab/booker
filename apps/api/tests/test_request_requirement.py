from tests.conftest import auth_header, register


def test_request_requirement_id_and_event_requests(client):
    customer = register(client, "c-rreq@booker.test", "Клиент")
    owner = register(client, "o-rreq@booker.test", "Артист")
    viewer = register(client, "v-rreq@booker.test", "Зритель")
    ch = auth_header(customer["token"])
    oh = auth_header(owner["token"])
    vh = auth_header(viewer["token"])

    cust_org = client.post("/orgs", json={"name": "Заказчик", "kind": "customer"}, headers=ch).json()
    added = client.post(
        f"/orgs/{cust_org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=ch,
    )
    assert added.status_code == 200
    artist_org = client.post("/orgs", json={"name": "Шоу", "kind": "artist"}, headers=oh).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Nova", "category": "dj"},
        headers=oh,
    ).json()
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-09-01T18:00:00+00:00",
            "ends_at": "2026-09-01T22:00:00+00:00",
        },
        headers=oh,
    ).json()

    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Корпоратив",
            "event_date": "2026-09-01T18:00:00+00:00",
        },
        headers=ch,
    ).json()
    other = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Другое",
            "event_date": "2026-09-02T18:00:00+00:00",
        },
        headers=ch,
    ).json()

    replaced = client.put(
        f"/events/{event['id']}/requirements",
        json={"items": [{"category_code": "dj", "qty": 1}]},
        headers=ch,
    )
    assert replaced.status_code == 200, replaced.text
    requirement_id = replaced.json()["requirements"][0]["id"]
    foreign = client.put(
        f"/events/{other['id']}/requirements",
        json={"items": [{"category_code": "host", "qty": 1}]},
        headers=ch,
    ).json()["requirements"][0]["id"]

    plain = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=ch,
    )
    assert plain.status_code == 200, plain.text
    plain_id = plain.json()["id"]

    denied_foreign = client.post(
        f"/events/{event['id']}/requests",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "requirement_id": foreign,
        },
        headers=ch,
    )
    assert denied_foreign.status_code == 400

    linked = client.post(
        f"/events/{event['id']}/requests",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "requirement_id": requirement_id,
        },
        headers=ch,
    )
    assert linked.status_code == 200, linked.text
    linked_id = linked.json()["id"]

    denied_viewer = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=vh,
    )
    assert denied_viewer.status_code == 403

    got = client.get(f"/events/{event['id']}", headers=ch)
    assert got.status_code == 200
    by_id = {row["id"]: row for row in got.json()["requests"]}
    assert set(by_id) >= {plain_id, linked_id}
    assert by_id[plain_id]["requirement_id"] is None
    assert by_id[plain_id]["booking_id"] is None
    assert "quote_id" not in by_id[plain_id]
    item = by_id[linked_id]
    assert item["status"] == "RequestSent"
    assert item["resource_type"] == "artist"
    assert item["resource_id"] == artist["id"]
    assert item["requirement_id"] == requirement_id
    assert item["booking_id"] is None
    assert "quote_id" not in item

    offer = client.post(
        f"/requests/{linked_id}/offers",
        json={"honorarium_rub": 100000, "slot_id": slot["id"], "terms": "2 часа сет"},
        headers=oh,
    )
    assert offer.status_code == 200, offer.text
    quote_id = offer.json()["version"]["quote_id"]
    booking_id = offer.json()["booking_id"]

    after = client.get(f"/events/{event['id']}", headers=ch).json()
    linked_row = {row["id"]: row for row in after["requests"]}[linked_id]
    assert linked_row["booking_id"] == booking_id
    assert linked_row["quote_id"] == quote_id
    assert linked_row["requirement_id"] == requirement_id
