"""W3-SHARE / W3-COMPARE / E22: shared shortlist revoke + compare."""

from tests.conftest import auth_header, register


def _seed(client):
    customer = register(client, "share-cust@booker.test", "Заказчик")
    owner = register(client, "share-supply@booker.test", "Снабжение")
    cust_h = auth_header(customer["token"])
    own_h = auth_header(owner["token"])
    cust_org = client.post(
        "/orgs",
        json={"name": "Клиент SHARE", "kind": "customer"},
        headers=cust_h,
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Артисты SHARE", "kind": "artist"},
        headers=own_h,
    ).json()
    artists = []
    for name in ("DJ Alpha", "DJ Beta", "DJ Gamma"):
        artists.append(
            client.post(
                "/artists",
                json={"organization_id": artist_org["id"], "name": name, "category": "dj"},
                headers=own_h,
            ).json()
        )
    fav_ids = []
    for artist in artists[:3]:
        fav = client.post(
            "/favorites",
            json={
                "target_type": "artist",
                "target_id": artist["id"],
                "organization_id": cust_org["id"],
            },
            headers=cust_h,
        )
        assert fav.status_code == 201, fav.text
        fav_ids.append(fav.json()["id"])
    return {
        "cust_h": cust_h,
        "cust_org": cust_org,
        "artists": artists,
        "fav_ids": fav_ids,
        "stranger": auth_header(register(client, "share-other@booker.test", "Другой")["token"]),
    }


def test_create_public_share_and_revoke(client):
    ctx = _seed(client)
    created = client.post(
        "/shortlists",
        json={
            "organization_id": ctx["cust_org"]["id"],
            "target_type": "artist",
            "title": "Кандидаты на пятницу",
            "favorite_ids": ctx["fav_ids"],
        },
        headers=ctx["cust_h"],
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["token"]
    assert body["share_path"].startswith("/s/")
    assert len(body["items"]) == 3
    assert "phone" not in str(body).lower()

    public = client.get(f"/shared/{body['token']}")
    assert public.status_code == 200, public.text
    pub = public.json()
    assert pub["robots"] == "noindex"
    assert len(pub["items"]) == 3
    assert all("name" in it for it in pub["items"])

    revoked = client.post(
        f"/shortlists/{body['id']}/revoke",
        headers=ctx["cust_h"],
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None

    gone = client.get(f"/shared/{body['token']}")
    assert gone.status_code == 404


def test_stranger_cannot_revoke(client):
    ctx = _seed(client)
    created = client.post(
        "/shortlists",
        json={
            "organization_id": ctx["cust_org"]["id"],
            "target_type": "artist",
            "favorite_ids": ctx["fav_ids"][:2],
        },
        headers=ctx["cust_h"],
    ).json()
    denied = client.post(
        f"/shortlists/{created['id']}/revoke",
        headers=ctx["stranger"],
    )
    assert denied.status_code == 404


def test_compare_artists(client):
    ctx = _seed(client)
    ids = ",".join(a["id"] for a in ctx["artists"][:3])
    res = client.get(f"/compare?target_type=artist&ids={ids}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["target_type"] == "artist"
    assert len(data["columns"]) == 3
    assert "неизвестно" in str(data) or all("name" in c for c in data["columns"])
