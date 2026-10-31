from datetime import datetime, timezone

from booker_api.composition import replace_requirements
from booker_api.models import Event, EventTeamRequirement, Organization, Request
from tests.conftest import auth_header, register


def test_replace_requirements_reuses_rows_and_nulls_leftover_fks(SessionLocal):
    db = SessionLocal()
    try:
        org = Organization(name="Заказчик", kind="customer")
        db.add(org)
        db.flush()
        event = Event(
            organization_id=org.id,
            title="Корпоратив",
            event_date=datetime(2026, 9, 1, 18, tzinfo=timezone.utc),
        )
        db.add(event)
        db.flush()

        rows = replace_requirements(db, event, [{"category_code": "dj", "qty": 1}])
        assert len(rows) == 1
        requirement_id = rows[0].id
        req = Request(
            event_id=event.id,
            requirement_id=requirement_id,
            resource_type="artist",
            resource_id="artist-1",
            supplier_org_id=org.id,
        )
        db.add(req)
        db.flush()

        kept = replace_requirements(db, event, [{"category_code": "dj", "qty": 2}])
        assert kept[0].id == requirement_id
        db.refresh(req)
        assert req.requirement_id == requirement_id
        assert db.get(EventTeamRequirement, requirement_id) is not None

        kept_by_id = replace_requirements(
            db, event, [{"id": requirement_id, "category_code": "dj", "qty": 1}]
        )
        assert kept_by_id[0].id == requirement_id
        db.refresh(req)
        assert req.requirement_id == requirement_id

        dropped = replace_requirements(db, event, [{"category_code": "host", "qty": 1}])
        assert dropped[0].id != requirement_id
        db.refresh(req)
        assert req.requirement_id is None
        assert db.get(EventTeamRequirement, requirement_id) is None
        assert db.get(Request, req.id) is not None
    finally:
        db.close()


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

    kept = client.put(
        f"/events/{event['id']}/requirements",
        json={"items": [{"category_code": "dj", "qty": 2, "notes": "сет 2ч"}]},
        headers=ch,
    )
    assert kept.status_code == 200, kept.text
    kept_req = kept.json()["requirements"][0]
    assert kept_req["id"] == requirement_id
    assert kept_req["qty"] == 2
    after_replace = client.get(f"/events/{event['id']}", headers=ch).json()
    live_after_replace = {row["id"] for row in after_replace["requirements"]}
    by_replace = {row["id"]: row for row in after_replace["requests"]}
    assert linked_id in by_replace
    assert by_replace[linked_id]["requirement_id"] == requirement_id
    assert requirement_id in live_after_replace

    kept_by_id = client.put(
        f"/events/{event['id']}/requirements",
        json={"items": [{"id": requirement_id, "category_code": "dj", "qty": 3}]},
        headers=ch,
    )
    assert kept_by_id.status_code == 200, kept_by_id.text
    assert kept_by_id.json()["requirements"][0]["id"] == requirement_id
    after_by_id = client.get(f"/events/{event['id']}", headers=ch).json()
    assert {row["id"]: row for row in after_by_id["requests"]}[linked_id]["requirement_id"] == requirement_id

    dropped = client.put(
        f"/events/{event['id']}/requirements",
        json={"items": [{"category_code": "host", "qty": 1}]},
        headers=ch,
    )
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["requirements"][0]["id"] != requirement_id
    after_drop = client.get(f"/events/{event['id']}", headers=ch).json()
    live_ids = {row["id"] for row in after_drop["requirements"]}
    by_drop = {row["id"]: row for row in after_drop["requests"]}
    assert linked_id in by_drop
    assert by_drop[linked_id]["requirement_id"] is None
    assert requirement_id not in live_ids
    assert by_drop[linked_id]["requirement_id"] not in live_ids


def test_replace_requirements_preserves_then_nulls_request_links(client):
    customer = register(client, "c-repl-req@booker.test", "Клиент")
    owner = register(client, "o-repl-req@booker.test", "Артист")
    ch = auth_header(customer["token"])
    oh = auth_header(owner["token"])
    cust_org = client.post("/orgs", json={"name": "Заказчик", "kind": "customer"}, headers=ch).json()
    artist_org = client.post("/orgs", json={"name": "Шоу", "kind": "artist"}, headers=oh).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Link", "category": "dj"},
        headers=oh,
    ).json()
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Свадьба",
            "event_date": "2026-10-01T18:00:00+00:00",
        },
        headers=ch,
    ).json()

    created = client.put(
        f"/events/{event['id']}/requirements",
        json={"items": [{"category_code": "dj", "qty": 1}]},
        headers=ch,
    )
    assert created.status_code == 200, created.text
    requirement_id = created.json()["requirements"][0]["id"]

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

    same_category = client.put(
        f"/events/{event['id']}/requirements",
        json={"items": [{"category_code": "dj", "qty": 2, "notes": "сет 2ч"}]},
        headers=ch,
    )
    assert same_category.status_code == 200, same_category.text
    live = same_category.json()["requirements"]
    assert len(live) == 1
    assert live[0]["id"] == requirement_id
    got = client.get(f"/events/{event['id']}", headers=ch)
    assert got.status_code == 200
    payload = got.json()
    live_ids = {row["id"] for row in payload["requirements"]}
    by_id = {row["id"]: row for row in payload["requests"]}
    assert linked_id in by_id
    assert by_id[linked_id]["requirement_id"] == requirement_id
    assert requirement_id in live_ids

    same_id = client.put(
        f"/events/{event['id']}/requirements",
        json={"items": [{"id": requirement_id, "category_code": "dj", "qty": 1}]},
        headers=ch,
    )
    assert same_id.status_code == 200, same_id.text
    assert same_id.json()["requirements"][0]["id"] == requirement_id
    after_id = client.get(f"/events/{event['id']}", headers=ch).json()
    assert {row["id"]: row for row in after_id["requests"]}[linked_id]["requirement_id"] == requirement_id

    dropped = client.put(
        f"/events/{event['id']}/requirements",
        json={"items": [{"category_code": "host", "qty": 1}]},
        headers=ch,
    )
    assert dropped.status_code == 200, dropped.text
    leftover = dropped.json()["requirements"]
    assert leftover[0]["id"] != requirement_id
    after_drop = client.get(f"/events/{event['id']}", headers=ch)
    assert after_drop.status_code == 200
    dropped_payload = after_drop.json()
    live_after = {row["id"] for row in dropped_payload["requirements"]}
    by_drop = {row["id"]: row for row in dropped_payload["requests"]}
    assert linked_id in by_drop
    assert by_drop[linked_id]["requirement_id"] is None
    assert requirement_id not in live_after
    unmatched = [
        row
        for row in dropped_payload["requests"]
        if not row["requirement_id"] or row["requirement_id"] not in live_after
    ]
    assert any(row["id"] == linked_id for row in unmatched)
