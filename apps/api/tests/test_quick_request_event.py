from tests.conftest import auth_header, register


def _setup(client):
    customer = register(client, "qre-c@booker.test", "Клиент")
    owner = register(client, "qre-a@booker.test", "Артист")
    viewer = register(client, "qre-v@booker.test", "Зритель")
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
            "starts_at": "2026-09-10T18:00:00+00:00",
            "ends_at": "2026-09-10T22:00:00+00:00",
        },
        headers=oh,
    ).json()
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Корпоратив",
            "event_date": "2026-09-10T18:00:00+00:00",
        },
        headers=ch,
    ).json()
    other = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Другое",
            "event_date": "2026-09-11T18:00:00+00:00",
        },
        headers=ch,
    ).json()
    return {
        "customer": customer,
        "owner": owner,
        "viewer": viewer,
        "ch": ch,
        "oh": oh,
        "vh": vh,
        "cust_org": cust_org,
        "artist": artist,
        "slot": slot,
        "event": event,
        "other": other,
    }


def test_quick_request_attaches_to_existing_event(client):
    ctx = _setup(client)
    event_id = ctx["event"]["id"]
    before = client.get("/events", headers=ctx["ch"])
    assert before.status_code == 200
    assert len(before.json()["items"]) == 2

    quick = client.post(
        "/quick-request",
        json={
            "artist_id": ctx["artist"]["id"],
            "slot_id": ctx["slot"]["id"],
            "event_id": event_id,
            "title": "не должно создать новое событие",
        },
        headers=ctx["ch"],
    )
    assert quick.status_code == 200, quick.text
    body = quick.json()
    assert body["event_id"] == event_id
    assert body["status"] == "RequestSent"
    assert body["request_id"]

    after = client.get("/events", headers=ctx["ch"]).json()["items"]
    assert len(after) == 2
    assert {row["id"] for row in after} == {event_id, ctx["other"]["id"]}

    got = client.get(f"/events/{event_id}", headers=ctx["ch"])
    assert got.status_code == 200
    payload = got.json()
    assert payload["id"] == event_id
    assert payload["title"] == "Корпоратив"
    assert payload["status"] == "RequestSent"
    assert len(payload["requests"]) == 1
    req = payload["requests"][0]
    assert req["id"] == body["request_id"]
    assert req["status"] == "RequestSent"
    assert req["resource_type"] == "artist"
    assert req["resource_id"] == ctx["artist"]["id"]
    assert req["requirement_id"] is None
    assert "quote_id" not in req


def test_quick_request_without_event_id_creates_event(client):
    ctx = _setup(client)
    extra = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": ctx["artist"]["id"],
            "starts_at": "2026-09-12T18:00:00+00:00",
            "ends_at": "2026-09-12T22:00:00+00:00",
        },
        headers=ctx["oh"],
    ).json()
    quick = client.post(
        "/quick-request",
        json={
            "artist_id": ctx["artist"]["id"],
            "slot_id": extra["id"],
            "title": "День рождения",
        },
        headers=ctx["ch"],
    )
    assert quick.status_code == 200, quick.text
    body = quick.json()
    assert body["status"] == "RequestSent"
    assert body["event_id"] not in {ctx["event"]["id"], ctx["other"]["id"]}
    events = client.get("/events", headers=ctx["ch"]).json()["items"]
    assert len(events) == 3
    created = {row["id"]: row for row in events}[body["event_id"]]
    assert created["title"] == "День рождения"


def test_quick_request_requirement_must_belong_to_event(client):
    ctx = _setup(client)
    replaced = client.put(
        f"/events/{ctx['event']['id']}/requirements",
        json={"items": [{"category_code": "dj", "qty": 1}]},
        headers=ctx["ch"],
    )
    assert replaced.status_code == 200, replaced.text
    requirement_id = replaced.json()["requirements"][0]["id"]
    foreign = client.put(
        f"/events/{ctx['other']['id']}/requirements",
        json={"items": [{"category_code": "host", "qty": 1}]},
        headers=ctx["ch"],
    ).json()["requirements"][0]["id"]

    denied = client.post(
        "/quick-request",
        json={
            "artist_id": ctx["artist"]["id"],
            "slot_id": ctx["slot"]["id"],
            "event_id": ctx["event"]["id"],
            "requirement_id": foreign,
        },
        headers=ctx["ch"],
    )
    assert denied.status_code == 400

    linked = client.post(
        "/quick-request",
        json={
            "artist_id": ctx["artist"]["id"],
            "slot_id": ctx["slot"]["id"],
            "event_id": ctx["event"]["id"],
            "requirement_id": requirement_id,
        },
        headers=ctx["ch"],
    )
    assert linked.status_code == 200, linked.text
    body = linked.json()
    assert body["event_id"] == ctx["event"]["id"]
    got = client.get(f"/events/{ctx['event']['id']}", headers=ctx["ch"]).json()
    by_id = {row["id"]: row for row in got["requests"]}
    assert by_id[body["request_id"]]["requirement_id"] == requirement_id


def test_quick_request_event_writer_and_slot(client):
    ctx = _setup(client)
    missing = client.post(
        "/quick-request",
        json={
            "artist_id": ctx["artist"]["id"],
            "slot_id": ctx["slot"]["id"],
            "event_id": "evt-missing",
        },
        headers=ctx["ch"],
    )
    assert missing.status_code == 404

    viewer = client.post(
        "/quick-request",
        json={
            "artist_id": ctx["artist"]["id"],
            "slot_id": ctx["slot"]["id"],
            "event_id": ctx["event"]["id"],
        },
        headers=ctx["vh"],
    )
    assert viewer.status_code == 403

    stranger = register(client, "qre-x@booker.test", "Чужой")
    stranger_org = client.post(
        "/orgs",
        json={"name": "Другой заказчик", "kind": "customer"},
        headers=auth_header(stranger["token"]),
    )
    assert stranger_org.status_code == 200
    foreign = client.post(
        "/quick-request",
        json={
            "artist_id": ctx["artist"]["id"],
            "slot_id": ctx["slot"]["id"],
            "event_id": ctx["event"]["id"],
        },
        headers=auth_header(stranger["token"]),
    )
    assert foreign.status_code == 403

    busy = client.post(
        "/quick-request",
        json={
            "artist_id": ctx["artist"]["id"],
            "slot_id": "slot-missing",
            "event_id": ctx["event"]["id"],
        },
        headers=ctx["ch"],
    )
    assert busy.status_code == 409
