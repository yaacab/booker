"""Artist profile PATCH and owner-facing publication fields."""

from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, publish_artist, register


def _owner_artist(client):
    owner = register(client, "patch-artist@booker.test", "Артист")
    org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ Base", "category": "dj", "city": "Москва"},
        headers=auth_header(owner["token"]),
    ).json()
    return owner, org, artist


def test_patch_artist_name_city_rider(client):
    owner, _org, artist = _owner_artist(client)
    patched = client.patch(
        f"/artists/{artist['id']}",
        json={
            "name": "DJ Nova",
            "city": "Санкт-Петербург",
            "category": "live",
            "rider_json": '{"format":"live","travel":"yes"}',
        },
        headers=auth_header(owner["token"]),
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["name"] == "DJ Nova"
    assert body["city"] == "Санкт-Петербург"
    assert body["category"] == "live"

    page = client.get(
        f"/artists/{artist['id']}",
        headers=auth_header(owner["token"]),
    ).json()
    assert page["name"] == "DJ Nova"
    assert page["rider"]["format"] == "live"
    assert page["publication_enabled"] is False
    assert "publication_reason_codes" in page


def test_catalog_search_includes_artist_media_url(client):
    owner, _org, artist = _owner_artist(client)
    client.post(
        f"/artists/{artist['id']}/tariffs",
        json={"title": "Сет", "honorarium_rub": 70000},
        headers=auth_header(owner["token"]),
    )
    starts = datetime.now(timezone.utc) + timedelta(days=5)
    client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=3)).isoformat(),
        },
        headers=auth_header(owner["token"]),
    )
    publish_artist(client, owner, artist["id"], add_tariff=False)
    # Evidence sets media; confirm search payload carries it.
    search = client.get("/catalog/search", params={"city": "Москва", "kind": "artist"})
    assert search.status_code == 200
    items = search.json()["items"]
    hit = next(item for item in items if item["id"] == artist["id"])
    assert hit.get("media_url")
