"""Service PATCH/DELETE, publish toggle, and tariff sync for V2."""

from tests.conftest import auth_header, register


def _owner_with_artist(client, email="svc-crud@booker.test"):
    owner = register(client, email, "Owner")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Сцена", "kind": "artist"}, headers=headers
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ", "category": "dj"},
        headers=headers,
    ).json()
    return owner, headers, org, artist


def test_patch_publish_and_delete_service(client):
    _owner, headers, org, artist = _owner_with_artist(client)
    created = client.post(
        "/services",
        json={
            "organization_id": org["id"],
            "category_code": "dj",
            "title": "Сет",
            "honorarium_rub": 50000,
            "resource_type": "artist",
            "resource_id": artist["id"],
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    service_id = created.json()["id"]

    patched = client.patch(
        f"/services/{service_id}",
        json={"title": "Сет плюс", "published": False, "honorarium_rub": 55000},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "Сет плюс"
    assert patched.json()["published"] is False
    assert patched.json()["honorarium_rub"] == 55000

    listed = client.get(f"/services?organization_id={org['id']}", headers=headers).json()
    assert listed["items"][0]["published"] is False
    public = client.get("/services/public?category=dj").json()["items"]
    assert all(item["id"] != service_id for item in public)

    deleted = client.delete(f"/services/{service_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/services?organization_id={org['id']}", headers=headers).json()["items"] == []


def test_sync_service_creates_catalog_tariff(client):
    _owner, headers, org, artist = _owner_with_artist(client, "svc-sync@booker.test")
    service = client.post(
        "/services",
        json={
            "organization_id": org["id"],
            "category_code": "dj",
            "title": "Свадебный сет",
            "honorarium_rub": 90000,
            "resource_type": "artist",
            "resource_id": artist["id"],
        },
        headers=headers,
    ).json()
    synced = client.post(f"/services/{service['id']}/sync-tariff", headers=headers)
    assert synced.status_code == 200, synced.text
    assert synced.json()["created"] is True
    profile = client.get(f"/artists/{artist['id']}", headers=headers).json()
    assert any(
        t["title"] == "Свадебный сет" and t["honorarium_rub"] == 90000
        for t in profile["tariffs"]
    )
    again = client.post(f"/services/{service['id']}/sync-tariff", headers=headers)
    assert again.status_code == 200
    assert again.json()["created"] is False


def test_foreign_cannot_patch_service(client):
    _owner, headers, org, artist = _owner_with_artist(client, "svc-owner2@booker.test")
    service = client.post(
        "/services",
        json={
            "organization_id": org["id"],
            "category_code": "dj",
            "title": "Private",
            "resource_type": "artist",
            "resource_id": artist["id"],
            "honorarium_rub": 10000,
        },
        headers=headers,
    ).json()
    foreign = register(client, "svc-foreign@booker.test", "Foreign")
    stolen = client.patch(
        f"/services/{service['id']}",
        json={"published": False},
        headers=auth_header(foreign["token"]),
    )
    assert stolen.status_code in {403, 404}
