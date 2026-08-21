from tests.conftest import auth_header, register


def _owner_artist(client):
    owner = register(client, "cal@booker.test", "Cal")
    org = client.post(
        "/orgs",
        json={"name": "Календарь", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "Кавер", "category": "cover"},
        headers=auth_header(owner["token"]),
    ).json()
    return owner, artist


def test_overlapping_slots_rejected(client):
    owner, artist = _owner_artist(client)
    first = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-10-01T18:00:00+00:00",
            "ends_at": "2026-10-01T22:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    assert first.status_code == 200
    clash = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-10-01T20:00:00+00:00",
            "ends_at": "2026-10-01T23:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    assert clash.status_code == 409


def test_search_hides_busy_and_no_calendar(client):
    owner, artist = _owner_artist(client)
    empty = client.get("/catalog/search", params={"city": "Москва", "category": "cover"})
    assert empty.json()["items"] == []

    client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-10-02T18:00:00+00:00",
            "ends_at": "2026-10-02T21:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    found = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "cover", "date": "2026-10-02T12:00:00+00:00"},
    )
    assert len(found.json()["items"]) == 1

    missing_day = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "cover", "date": "2026-10-03T12:00:00+00:00"},
    )
    assert missing_day.json()["items"] == []


def test_search_date_is_moscow_calendar_day(client):
    owner, artist = _owner_artist(client)
    client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-10-02T22:00:00+00:00",
            "ends_at": "2026-10-03T01:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    oct2 = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "cover", "date": "2026-10-02T00:00:00+03:00"},
    )
    oct3 = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "cover", "date": "2026-10-03T00:00:00+03:00"},
    )
    assert oct2.json()["items"] == []
    assert len(oct3.json()["items"]) == 1


def test_search_includes_venues_with_calendar(client):
    owner = register(client, "venue@booker.test", "Hall")
    org = client.post(
        "/orgs",
        json={"name": "Зал", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Клуб Тест", "city": "Москва", "capacity": 100},
        headers=auth_header(owner["token"]),
    ).json()
    hidden = client.get("/catalog/search", params={"city": "Москва", "category": "venue"})
    assert hidden.json()["venues"] == []
    client.post(
        "/slots",
        json={
            "resource_type": "hall",
            "resource_id": venue["hall_id"],
            "starts_at": "2026-10-12T19:00:00+00:00",
            "ends_at": "2026-10-12T23:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    found = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "venue", "date": "2026-10-12T12:00:00+00:00"},
    )
    assert len(found.json()["venues"]) == 1
    page = client.get(f"/venues/{venue['id']}")
    assert page.status_code == 200
    assert page.json()["name"] == "Клуб Тест"
