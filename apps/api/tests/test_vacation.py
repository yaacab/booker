from tests.conftest import auth_header, register


def _artist_ctx(client):
    owner = register(client, "vacation@booker.test", "Vacation")
    org = client.post(
        "/orgs",
        json={"name": "DJ Org", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ Away", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    return owner, org, artist


def test_vacation_status_empty(client):
    owner, org, artist = _artist_ctx(client)
    res = client.get(
        f"/organizations/{org['id']}/vacation",
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["resource_id"] == artist["id"]
    assert items[0]["active"] is False


def test_vacation_creates_busy_and_hides_from_search(client):
    owner, org, artist = _artist_ctx(client)
    headers = auth_header(owner["token"])
    open_slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-11-10T18:00:00+00:00",
            "ends_at": "2026-11-10T22:00:00+00:00",
        },
        headers=headers,
    )
    assert open_slot.status_code == 200

    res = client.post(
        "/calendar/vacation",
        json={
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-11-10T00:00:00+00:00",
            "ends_at": "2026-11-20T00:00:00+00:00",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["removed_open"] >= 1

    page = client.get(f"/artists/{artist['id']}").json()
    vacation_slots = [s for s in page["slots"] if s.get("busy_source") == "vacation"]
    assert len(vacation_slots) == 1
    assert vacation_slots[0]["status"] == "busy"

    missing = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "dj", "date": "2026-11-10T12:00:00+00:00"},
    )
    assert missing.json()["items"] == []

    status = client.get(f"/organizations/{org['id']}/vacation", headers=headers).json()
    assert status["items"][0]["active"] is True


def test_vacation_clear(client):
    owner, org, artist = _artist_ctx(client)
    headers = auth_header(owner["token"])
    payload = {
        "organization_id": org["id"],
        "resource_type": "artist",
        "resource_id": artist["id"],
        "starts_at": "2026-12-01T00:00:00+00:00",
        "ends_at": "2026-12-15T00:00:00+00:00",
    }
    created = client.post("/calendar/vacation", json=payload, headers=headers)
    assert created.status_code == 200

    cleared = client.request(
        "DELETE",
        "/calendar/vacation",
        json={
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
        },
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["cleared"] is True

    page = client.get(f"/artists/{artist['id']}").json()
    assert not any(s.get("busy_source") == "vacation" for s in page["slots"])

    status = client.get(f"/organizations/{org['id']}/vacation", headers=headers).json()
    assert status["items"][0]["active"] is False


def test_vacation_requires_writer(client):
    owner, org, artist = _artist_ctx(client)
    viewer = register(client, "vacation-viewer@booker.test", "Viewer")
    client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(owner["token"]),
    )
    res = client.post(
        "/calendar/vacation",
        json={
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-12-01T00:00:00+00:00",
            "ends_at": "2026-12-15T00:00:00+00:00",
        },
        headers=auth_header(viewer["token"]),
    )
    assert res.status_code == 403


def test_vacation_rejects_past_end(client):
    owner, org, artist = _artist_ctx(client)
    res = client.post(
        "/calendar/vacation",
        json={
            "organization_id": org["id"],
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2020-01-01T00:00:00+00:00",
            "ends_at": "2020-01-10T00:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 400
