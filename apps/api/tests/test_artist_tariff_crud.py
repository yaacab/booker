"""Artist tariff PATCH/DELETE and honorarium floor for cabinet UI."""

from tests.conftest import auth_header, register


def _artist_owner(client):
    owner = register(client, "tariff-owner@booker.test", "Владелец")
    org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ Nova", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    return owner, artist


def test_create_tariff_rejects_zero_honorarium(client):
    owner, artist = _artist_owner(client)
    res = client.post(
        f"/artists/{artist['id']}/tariffs",
        json={"title": "Сет", "honorarium_rub": 0},
        headers=auth_header(owner["token"]),
    )
    assert res.status_code == 422


def test_patch_and_delete_artist_tariff(client):
    owner, artist = _artist_owner(client)
    created = client.post(
        f"/artists/{artist['id']}/tariffs",
        json={"title": "Сет", "honorarium_rub": 80000, "hours": 2},
        headers=auth_header(owner["token"]),
    )
    assert created.status_code == 200, created.text
    tariff_id = created.json()["id"]

    patched = client.patch(
        f"/artists/{artist['id']}/tariffs/{tariff_id}",
        json={"title": "Сет 3ч", "honorarium_rub": 95000, "hours": 3},
        headers=auth_header(owner["token"]),
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["title"] == "Сет 3ч"
    assert body["honorarium_rub"] == 95000
    assert body["hours"] == 3

    profile = client.get(
        f"/artists/{artist['id']}",
        headers=auth_header(owner["token"]),
    )
    assert profile.status_code == 200
    assert profile.json()["tariffs"] == [
        {"id": tariff_id, "title": "Сет 3ч", "honorarium_rub": 95000}
    ]

    deleted = client.delete(
        f"/artists/{artist['id']}/tariffs/{tariff_id}",
        headers=auth_header(owner["token"]),
    )
    assert deleted.status_code == 204
    after = client.get(
        f"/artists/{artist['id']}",
        headers=auth_header(owner["token"]),
    )
    assert after.json()["tariffs"] == []


def test_patch_tariff_foreign_artist_rejected(client):
    owner, artist = _artist_owner(client)
    other = register(client, "tariff-other@booker.test", "Чужой")
    other_org = client.post(
        "/orgs",
        json={"name": "Другое", "kind": "artist"},
        headers=auth_header(other["token"]),
    ).json()
    other_artist = client.post(
        "/artists",
        json={"organization_id": other_org["id"], "name": "Other", "category": "dj"},
        headers=auth_header(other["token"]),
    ).json()
    tariff_id = client.post(
        f"/artists/{artist['id']}/tariffs",
        json={"title": "Сет", "honorarium_rub": 50000},
        headers=auth_header(owner["token"]),
    ).json()["id"]

    cross = client.patch(
        f"/artists/{other_artist['id']}/tariffs/{tariff_id}",
        json={"honorarium_rub": 1},
        headers=auth_header(other["token"]),
    )
    assert cross.status_code == 404

    stolen = client.patch(
        f"/artists/{artist['id']}/tariffs/{tariff_id}",
        json={"honorarium_rub": 1},
        headers=auth_header(other["token"]),
    )
    assert stolen.status_code in {403, 404}


def test_delete_tariff_idempotent_404(client):
    owner, artist = _artist_owner(client)
    tariff_id = client.post(
        f"/artists/{artist['id']}/tariffs",
        json={"title": "Сет", "honorarium_rub": 40000},
        headers=auth_header(owner["token"]),
    ).json()["id"]
    assert (
        client.delete(
            f"/artists/{artist['id']}/tariffs/{tariff_id}",
            headers=auth_header(owner["token"]),
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/artists/{artist['id']}/tariffs/{tariff_id}",
            headers=auth_header(owner["token"]),
        ).status_code
        == 404
    )
