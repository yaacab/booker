from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, publish_artist, publish_venue, register


def _future_day(offset: int = 7):
    return (datetime.now(timezone.utc) + timedelta(days=offset)).date()


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
    day = _future_day()
    first = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": f"{day.isoformat()}T18:00:00+00:00",
            "ends_at": f"{day.isoformat()}T22:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    assert first.status_code == 200
    clash = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": f"{day.isoformat()}T20:00:00+00:00",
            "ends_at": f"{day.isoformat()}T23:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    assert clash.status_code == 409


def test_search_hides_busy_and_no_calendar(client):
    owner, artist = _owner_artist(client)
    empty = client.get("/catalog/search", params={"city": "Москва", "category": "cover"})
    assert empty.json()["items"] == []

    day = _future_day()
    following_day = day + timedelta(days=1)

    client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": f"{day.isoformat()}T18:00:00+00:00",
            "ends_at": f"{day.isoformat()}T21:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    publish_artist(client, owner, artist["id"])
    found = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "cover", "date": f"{day.isoformat()}T12:00:00+00:00"},
    )
    assert len(found.json()["items"]) == 1

    missing_day = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "cover", "date": f"{following_day.isoformat()}T12:00:00+00:00"},
    )
    assert missing_day.json()["items"] == []


def test_search_date_is_moscow_calendar_day(client):
    owner, artist = _owner_artist(client)
    starts_at = (datetime.now(timezone.utc) + timedelta(days=7)).replace(
        hour=22, minute=0, second=0, microsecond=0,
    )
    ends_at = starts_at + timedelta(hours=3)
    previous_moscow_day = starts_at.date().isoformat()
    slot_moscow_day = ends_at.date().isoformat()
    created = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
        headers=auth_header(owner["token"]),
    )
    assert created.status_code == 200, created.text
    publish_artist(client, owner, artist["id"])
    previous = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "cover",
                "date": f"{previous_moscow_day}T00:00:00+03:00"},
    )
    current = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "cover",
                "date": f"{slot_moscow_day}T00:00:00+03:00"},
    )
    assert previous.json()["items"] == []
    assert len(current.json()["items"]) == 1


def test_search_includes_venues_with_calendar(client):
    owner = register(client, "venue@booker.test", "Hall")
    day = _future_day(10)
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
            "starts_at": f"{day.isoformat()}T19:00:00+00:00",
            "ends_at": f"{day.isoformat()}T23:00:00+00:00",
        },
        headers=auth_header(owner["token"]),
    )
    publish_venue(client, owner, venue["id"])
    found = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "venue", "date": f"{day.isoformat()}T12:00:00+00:00"},
    )
    assert len(found.json()["venues"]) == 1
    page = client.get(f"/venues/{venue['id']}")
    assert page.status_code == 200
    assert page.json()["name"] == "Клуб Тест"
