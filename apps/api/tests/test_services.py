from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, publish_artist, register


def test_create_and_list_service(client):
    user = register(client, "svc@booker.test", "Svc")
    h = auth_header(user["token"])
    org = client.post("/orgs", json={"name": "Сцена", "kind": "artist"}, headers=h).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ услуги", "category": "dj"},
        headers=h,
    ).json()
    start = datetime.now(timezone.utc) + timedelta(days=10)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=4)).isoformat(),
        },
        headers=h,
    )
    assert slot.status_code == 200, slot.text
    publish_artist(client, user, artist["id"])
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


def test_public_service_must_bind_to_its_own_eligible_profile(client):
    owner = register(client, "service-binding@booker.test", "Owner")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Multi Artist", "kind": "artist"}, headers=headers
    ).json()
    verified = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "Verified DJ", "category": "dj"},
        headers=headers,
    ).json()
    unverified = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "Unverified DJ", "category": "dj"},
        headers=headers,
    ).json()
    starts = datetime.now(timezone.utc) + timedelta(days=40)
    assert client.post(
        "/slots",
        json={
            "resource_type": "artist", "resource_id": verified["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
        },
        headers=headers,
    ).status_code == 200
    publish_artist(client, owner, verified["id"])
    service = client.post(
        "/services",
        json={
            "organization_id": org["id"], "category_code": "dj",
            "title": "Непроверенная услуга", "resource_type": "artist",
            "resource_id": unverified["id"],
        },
        headers=headers,
    )
    assert service.status_code == 200, service.text
    public_ids = {item["id"] for item in client.get("/services/public").json()["items"]}
    assert service.json()["id"] not in public_ids
    assert service.json()["resource_id"] == unverified["id"]

    ambiguous = client.post(
        "/services",
        json={"organization_id": org["id"], "category_code": "dj", "title": "Без профиля"},
        headers=headers,
    )
    assert ambiguous.status_code == 200
    assert ambiguous.json()["resource_id"] is None
    assert ambiguous.json()["published"] is True
    assert ambiguous.json()["id"] not in {
        item["id"] for item in client.get("/services/public").json()["items"]
    }

    foreign_owner = register(client, "service-foreign@booker.test", "Foreign")
    foreign_headers = auth_header(foreign_owner["token"])
    foreign_org = client.post(
        "/orgs", json={"name": "Foreign Supply", "kind": "artist"},
        headers=foreign_headers,
    ).json()
    foreign_artist = client.post(
        "/artists",
        json={"organization_id": foreign_org["id"], "name": "Foreign DJ", "category": "dj"},
        headers=foreign_headers,
    ).json()
    cross_org = client.post(
        "/services",
        json={
            "organization_id": org["id"], "category_code": "dj", "title": "Чужой DJ",
            "resource_type": "artist", "resource_id": foreign_artist["id"],
        },
        headers=headers,
    )
    assert cross_org.status_code == 404
    assert client.get(
        f"/services?organization_id={org['id']}", headers=foreign_headers
    ).status_code == 403

    eligible = client.post(
        "/services",
        json={
            "organization_id": org["id"], "category_code": "dj", "title": "Проверенный DJ",
            "resource_type": "artist", "resource_id": verified["id"],
        },
        headers=headers,
    )
    assert eligible.status_code == 200
    assert eligible.json()["id"] in {
        item["id"] for item in client.get("/services/public").json()["items"]
    }
    disabled = client.put(
        f"/artists/{verified['id']}/publication",
        json={"enabled": False, "state_version": 1}, headers=headers,
    )
    assert disabled.status_code == 200
    assert eligible.json()["id"] not in {
        item["id"] for item in client.get("/services/public").json()["items"]
    }


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


def test_service_created_before_single_profile_retains_publication_intent(client):
    owner = register(client, "service-before-profile@booker.test", "Owner")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Early Service", "kind": "artist"}, headers=headers
    ).json()
    service = client.post(
        "/services",
        json={"organization_id": org["id"], "category_code": "dj", "title": "DJ рано"},
        headers=headers,
    )
    assert service.status_code == 200
    assert service.json()["published"] is True
    assert service.json()["resource_id"] is None
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ рано", "category": "dj"},
        headers=headers,
    ).json()
    starts = datetime.now(timezone.utc) + timedelta(days=40)
    assert client.post(
        "/slots",
        json={
            "resource_type": "artist", "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
        },
        headers=headers,
    ).status_code == 200
    publish_artist(client, owner, artist["id"])
    assert service.json()["id"] in {
        item["id"] for item in client.get("/services/public").json()["items"]
    }


def test_sqlite_schema_backfills_only_unambiguous_legacy_service_bindings(
    client, engine, SessionLocal
):
    from booker_api.db import ensure_sqlite_columns
    from booker_api.models import Service

    owner = register(client, "legacy-service@booker.test", "Owner")
    headers = auth_header(owner["token"])
    sole_org = client.post(
        "/orgs", json={"name": "Sole Profile", "kind": "artist"}, headers=headers
    ).json()
    sole_artist = client.post(
        "/artists",
        json={"organization_id": sole_org["id"], "name": "Sole DJ", "category": "dj"},
        headers=headers,
    ).json()
    sole_service = client.post(
        "/services",
        json={"organization_id": sole_org["id"], "category_code": "dj", "title": "Sole"},
        headers=headers,
    ).json()
    multi_org = client.post(
        "/orgs",
        json={"name": "Multiple Profiles", "kind": "artist", "confirm_another_workspace": True},
        headers=headers,
    ).json()
    for name in ("DJ One", "DJ Two"):
        assert client.post(
            "/artists",
            json={"organization_id": multi_org["id"], "name": name, "category": "dj"},
            headers=headers,
        ).status_code == 200
    multi_service = client.post(
        "/services",
        json={"organization_id": multi_org["id"], "category_code": "dj", "title": "Ambiguous"},
        headers=headers,
    ).json()
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE services DROP COLUMN resource_id")
        conn.exec_driver_sql("ALTER TABLE services DROP COLUMN resource_type")
    ensure_sqlite_columns(engine)
    with SessionLocal() as db:
        sole = db.get(Service, sole_service["id"])
        ambiguous = db.get(Service, multi_service["id"])
        assert (sole.resource_type, sole.resource_id) == ("artist", sole_artist["id"])
        assert (ambiguous.resource_type, ambiguous.resource_id) == (None, None)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE services SET resource_type = NULL, resource_id = NULL WHERE id = ?",
            (sole_service["id"],),
        )
    ensure_sqlite_columns(engine)
    with SessionLocal() as db:
        assert db.get(Service, sole_service["id"]).resource_id == sole_artist["id"]


def test_ambiguous_service_requires_writer_to_bind_profile(client):
    owner = register(client, "service-rebind@booker.test", "Owner")
    viewer = register(client, "service-rebind-viewer@booker.test", "Viewer")
    headers = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Two DJs", "kind": "artist"}, headers=headers).json()
    artists = [
        client.post("/artists", json={"organization_id": org["id"], "name": name, "category": "dj"}, headers=headers).json()
        for name in ("One", "Two")
    ]
    service = client.post("/services", json={"organization_id": org["id"], "category_code": "dj", "title": "Set"}, headers=headers).json()
    assert service["resource_id"] is None
    assert client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer", "can_confirm_offer": False},
        headers=headers,
    ).status_code == 200
    path = f"/services/{service['id']}/profile"
    body = {"resource_type": "artist", "resource_id": artists[0]["id"]}
    assert client.put(path, json=body, headers=auth_header(viewer["token"])).status_code == 403
    assert client.put(path, json=body, headers=headers).json()["resource_id"] == artists[0]["id"]
    foreign = register(client, "service-rebind-foreign@booker.test", "Foreign")
    fh = auth_header(foreign["token"])
    foreign_org = client.post("/orgs", json={"name": "Foreign DJ", "kind": "artist"}, headers=fh).json()
    foreign_artist = client.post("/artists", json={"organization_id": foreign_org["id"], "name": "Foreign", "category": "dj"}, headers=fh).json()
    assert client.put(path, json={"resource_type": "artist", "resource_id": foreign_artist["id"]}, headers=headers).status_code == 404


def test_venue_service_cannot_bind_artist_profile(client):
    owner = register(client, "venue-service-artist@booker.test", "Owner")
    headers = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Mixed", "kind": "artist"}, headers=headers).json()
    artist = client.post("/artists", json={"organization_id": org["id"], "name": "DJ", "category": "dj"}, headers=headers).json()
    response = client.post("/services", json={"organization_id": org["id"], "category_code": "venue", "title": "Hall", "resource_type": "artist", "resource_id": artist["id"]}, headers=headers)
    assert response.status_code == 400
    assert client.post("/services", json={"organization_id": org["id"], "category_code": "photo", "title": "Photo", "resource_type": "artist", "resource_id": artist["id"]}, headers=headers).status_code == 400
    venue = client.post("/venues", json={"organization_id": org["id"], "name": "Hall"}, headers=headers)
    assert venue.status_code == 200, venue.text
    assert client.post("/services", json={"organization_id": org["id"], "category_code": "dj", "title": "DJ at venue", "resource_type": "venue", "resource_id": venue.json()["id"]}, headers=headers).status_code == 400


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
