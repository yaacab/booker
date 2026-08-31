from tests.conftest import auth_header, register


def test_create_and_list_service(client):
    user = register(client, "svc@booker.test", "Svc")
    h = auth_header(user["token"])
    org = client.post("/orgs", json={"name": "Сцена", "kind": "artist"}, headers=h).json()
    created = client.post(
        "/services",
        json={
            "organization_id": org["id"],
            "category_code": "dj",
            "title": "DJ на свадьбу",
            "description": "Сет 4 часа",
            "honorarium_rub": 80000,
        },
        headers=h,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["title"] == "DJ на свадьбу"
    assert body["category_code"] == "dj"
    assert body["honorarium_rub"] == 80000
    assert "quote_id" not in body
    listed = client.get(f"/services?organization_id={org['id']}", headers=h)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]
    public = client.get("/services/public?category=dj")
    assert public.status_code == 200
    assert any(i["id"] == body["id"] for i in public.json()["items"])


def test_viewer_cannot_post_service(client):
    owner = register(client, "svcown@booker.test", "Own")
    viewer = register(client, "svcview@booker.test", "View")
    org = client.post(
        "/orgs",
        json={"name": "Сцена", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    add = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer", "can_confirm_offer": False},
        headers=auth_header(owner["token"]),
    )
    assert add.status_code == 200
    denied = client.post(
        "/services",
        json={
            "organization_id": org["id"],
            "category_code": "photo",
            "title": "Фото",
        },
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403
    listed = client.get(
        f"/services?organization_id={org['id']}",
        headers=auth_header(viewer["token"]),
    )
    assert listed.status_code == 200


def test_public_hides_unpublished(client):
    user = register(client, "svcdraft@booker.test", "D")
    h = auth_header(user["token"])
    org = client.post("/orgs", json={"name": "Сцена", "kind": "artist"}, headers=h).json()
    draft = client.post(
        "/services",
        json={
            "organization_id": org["id"],
            "category_code": "host",
            "title": "Черновик",
            "published": False,
        },
        headers=h,
    ).json()
    public = client.get("/services/public?category=host")
    assert public.status_code == 200
    assert all(i["id"] != draft["id"] for i in public.json()["items"])
    internal = client.get(f"/services?organization_id={org['id']}", headers=h).json()["items"]
    assert any(i["id"] == draft["id"] for i in internal)


def test_create_service_writes_audit(client):
    user = register(client, "svcaudit@booker.test", "Audit")
    h = auth_header(user["token"])
    org = client.post("/orgs", json={"name": "Сцена", "kind": "artist"}, headers=h).json()
    created = client.post(
        "/services",
        json={
            "organization_id": org["id"],
            "category_code": "dj",
            "title": "DJ",
        },
        headers=h,
    )
    assert created.status_code == 200
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import AuditLog

        row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "service.created", AuditLog.entity_id == created.json()["id"])
            .one()
        )
        assert row.entity_type == "service"
    finally:
        db.close()
