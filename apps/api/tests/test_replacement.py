from tests.conftest import auth_header, register


def _setup_event_with_requirement(client):
    customer = register(client, "c-repl@booker.test", "Клиент")
    owner = register(client, "o-repl@booker.test", "Артист")
    ch = auth_header(customer["token"])
    oh = auth_header(owner["token"])
    cust_org = client.post("/orgs", json={"name": "Заказчик", "kind": "customer"}, headers=ch).json()
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
            "title": "Свадьба",
            "event_date": "2026-09-01T18:00:00+00:00",
            "requirements": [{"category_code": "dj", "qty": 1}],
        },
        headers=ch,
    ).json()
    requirement_id = event["requirements"][0]["id"]
    req = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"], "requirement_id": requirement_id},
        headers=ch,
    ).json()
    offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 100000, "slot_id": slot["id"]},
        headers=oh,
    ).json()
    return {
        "customer": customer,
        "owner": owner,
        "ch": ch,
        "oh": oh,
        "event": event,
        "requirement_id": requirement_id,
        "artist": artist,
        "slot": slot,
        "request_id": req["id"],
        "booking_id": offer["booking_id"],
    }


def test_cancel_booking_opens_replacement(client):
    ctx = _setup_event_with_requirement(client)
    cancelled = client.post(
        f"/bookings/{ctx['booking_id']}/cancel",
        json={"reason": "не смог"},
        headers=ctx["ch"],
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "Cancelled"
    assert body["request_status"] == "Cancelled"
    artist = client.get(f"/artists/{ctx['artist']['id']}").json()
    assert artist["slots"][0]["status"] == "open"


def test_replacement_plan_after_cancel(client):
    ctx = _setup_event_with_requirement(client)
    client.post(f"/bookings/{ctx['booking_id']}/cancel", headers=ctx["ch"])
    plan = client.get(
        f"/events/{ctx['event']['id']}/requirements/{ctx['requirement_id']}/replacement",
        headers=ctx["ch"],
    )
    assert plan.status_code == 200, plan.text
    data = plan.json()
    assert data["needs_replacement"] is True
    assert data["open_slots"] == 1
    assert len(data["cancelled_requests"]) == 1
    assert ctx["artist"]["id"] in data["exclude_resource_ids"]
    assert data["search"]["requirement_id"] == ctx["requirement_id"]
    assert ctx["artist"]["id"] in data["search"]["exclude"]


def test_catalog_search_excludes_failed_artist(client):
    ctx = _setup_event_with_requirement(client)
    before = client.get("/catalog/search?city=Москва&category=dj").json()
    assert any(item["id"] == ctx["artist"]["id"] for item in before["items"])
    after = client.get(f"/catalog/search?city=Москва&category=dj&exclude={ctx['artist']['id']}").json()
    assert not any(item["id"] == ctx["artist"]["id"] for item in after["items"])
