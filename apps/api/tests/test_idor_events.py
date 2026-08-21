from tests.conftest import auth_header, register


def test_foreign_user_cannot_read_or_mutate_event(client):
    owner = register(client, "idor-a@booker.test", "A")
    stranger = register(client, "idor-b@booker.test", "B")
    ah = auth_header(owner["token"])
    bh = auth_header(stranger["token"])
    org = client.post("/orgs", json={"name": "Клиент A", "kind": "customer"}, headers=ah).json()
    event = client.post(
        "/events",
        json={
            "organization_id": org["id"],
            "title": "Закрыто",
            "event_date": "2026-09-01T18:00:00+00:00",
        },
        headers=ah,
    ).json()
    event_id = event["id"]

    assert client.get(f"/events/{event_id}", headers=bh).status_code == 403
    assert (
        client.put(
            f"/events/{event_id}/requirements",
            json={"items": [{"category_code": "dj", "qty": 1}]},
            headers=bh,
        ).status_code
        == 403
    )
    artist_org = client.post("/orgs", json={"name": "Шоу", "kind": "artist"}, headers=ah).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ", "category": "dj"},
        headers=ah,
    ).json()
    assert (
        client.post(
            f"/events/{event_id}/requests",
            json={"resource_type": "artist", "resource_id": artist["id"]},
            headers=bh,
        ).status_code
        == 403
    )
