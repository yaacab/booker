from tests.conftest import auth_header, register


def test_active_org_and_performer_alias(client):
    user = register(client, "ws@booker.test", "WS")
    h = auth_header(user["token"])
    org = client.post("/orgs", json={"name": "Сцена", "kind": "performer"}, headers=h).json()
    assert org["kind"] == "artist"
    me = client.get("/me", headers=h).json()
    assert me["active_organization_id"] == org["id"]
    other = client.post("/orgs", json={"name": "Клиент", "kind": "customer"}, headers=h).json()
    switched = client.post("/me/active-org", json={"organization_id": other["id"]}, headers=h)
    assert switched.status_code == 200
    assert switched.json()["active_organization_id"] == other["id"]


def test_viewer_cannot_create_event(client):
    owner = register(client, "own@booker.test", "Own")
    viewer = register(client, "view@booker.test", "View")
    org = client.post(
        "/orgs",
        json={"name": "Клиент", "kind": "customer"},
        headers=auth_header(owner["token"]),
    ).json()
    add = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer", "can_confirm_offer": True},
        headers=auth_header(owner["token"]),
    )
    assert add.status_code == 200
    assert add.json()["can_confirm_offer"] is False
    denied = client.post(
        "/events",
        json={
            "organization_id": org["id"],
            "title": "Вечер",
            "event_date": "2026-09-01T18:00:00+00:00",
        },
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403


def test_composition_from_notes_and_explicit(client):
    user = register(client, "comp@booker.test", "C")
    h = auth_header(user["token"])
    org = client.post("/orgs", json={"name": "Клиент", "kind": "customer"}, headers=h).json()
    created = client.post(
        "/events",
        json={
            "organization_id": org["id"],
            "title": "Свадьба",
            "event_date": "2026-09-01T18:00:00+00:00",
            "notes": "артист:dj;площадка:смотрим:Loft",
        },
        headers=h,
    )
    assert created.status_code == 200
    codes = {r["category_code"] for r in created.json()["requirements"]}
    assert codes == {"dj", "venue"}
    explicit = client.post(
        "/events",
        json={
            "organization_id": org["id"],
            "title": "Корпоратив",
            "event_date": "2026-09-02T18:00:00+00:00",
            "requirements": [{"category_code": "host", "qty": 1}, {"category_code": "photo", "qty": 2}],
        },
        headers=h,
    ).json()
    assert [r["category_code"] for r in explicit["requirements"]] == ["host", "photo"]
    cats = client.get("/categories").json()["items"]
    assert {c["code"] for c in cats} >= {"dj", "host", "venue"}
