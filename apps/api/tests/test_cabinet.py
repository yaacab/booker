from tests.conftest import auth_header, register


def test_quick_request_and_inbox(client):
    customer = register(client, "qc@booker.test", "Клиент")
    owner = register(client, "qa@booker.test", "Артист")
    cust_org = client.post(
        "/orgs",
        json={"name": "Клиент", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    client.post(
        f"/artists/{artist['id']}/tariffs",
        json={"title": "Сет", "honorarium_rub": 80000},
        headers=auth_header(owner["token"]),
    )
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-09-10T18:00:00+00:00",
            "ends_at": "2026-09-10T22:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    ).json()
    quick = client.post(
        "/quick-request",
        json={"artist_id": artist["id"], "slot_id": slot["id"], "title": "День рождения"},
        headers=auth_header(customer["token"]),
    )
    assert quick.status_code == 200, quick.text
    inbox = client.get("/requests", headers=auth_header(owner["token"]))
    assert inbox.status_code == 200
    assert len(inbox.json()["items"]) == 1
    assert inbox.json()["items"][0]["honorarium_rub"] == 80000
    events = client.get("/events", headers=auth_header(customer["token"]))
    assert len(events.json()["items"]) == 1
    foreign = client.get("/events", headers=auth_header(owner["token"]))
    assert foreign.json()["items"] == []
    me = client.get("/me", headers=auth_header(customer["token"])).json()
    assert me["organizations"][0]["kind"] == "customer"
    assert cust_org["id"] == me["organizations"][0]["id"]
