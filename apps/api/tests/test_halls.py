from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, publish_venue, register


def _venue_owner(client):
    owner = register(client, "halls-owner@booker.test", "Owner")
    org = client.post(
        "/orgs",
        json={"name": "Площадка", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Лофт", "city": "Москва", "capacity": 120},
        headers=auth_header(owner["token"]),
    ).json()
    return owner, org, venue


def test_create_venue_makes_default_hall_and_lists_for_member(client):
    owner, _org, venue = _venue_owner(client)
    listed = client.get(f"/venues/{venue['id']}/halls", headers=auth_header(owner["token"]))
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == venue["hall_id"]
    assert items[0]["name"] == "Основной зал"
    assert items[0]["capacity"] == 120


def test_public_halls_require_catalog_or_member(client):
    owner, _org, venue = _venue_owner(client)
    stranger = register(client, "halls-stranger@booker.test", "Stranger")

    anon = client.get(f"/venues/{venue['id']}/halls")
    assert anon.status_code == 401

    foreign = client.get(f"/venues/{venue['id']}/halls", headers=auth_header(stranger["token"]))
    assert foreign.status_code == 403

    starts = datetime.now(timezone.utc) + timedelta(days=14)
    ends = starts + timedelta(hours=4)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "hall",
            "resource_id": venue["hall_id"],
            "starts_at": starts.isoformat(),
            "ends_at": ends.isoformat(),
        },
        headers=auth_header(owner["token"]),
    )
    assert slot.status_code == 200, slot.text
    publish_venue(client, owner, venue["id"])

    public = client.get(f"/venues/{venue['id']}/halls")
    assert public.status_code == 200, public.text
    assert {h["id"] for h in public.json()["items"]} == {venue["hall_id"]}


def test_post_hall_requires_writer_not_viewer(client):
    owner, org, venue = _venue_owner(client)
    viewer = register(client, "halls-viewer@booker.test", "Viewer")
    add = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(owner["token"]),
    )
    assert add.status_code == 200

    denied = client.post(
        f"/venues/{venue['id']}/halls",
        json={"name": "Каминный", "capacity": 40},
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403

    created = client.post(
        f"/venues/{venue['id']}/halls",
        json={"name": "Каминный", "capacity": 40},
        headers=auth_header(owner["token"]),
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "Каминный"
    assert body["capacity"] == 40
    assert body["id"]

    listed = client.get(f"/venues/{venue['id']}/halls", headers=auth_header(viewer["token"]))
    assert listed.status_code == 200
    names = {h["name"] for h in listed.json()["items"]}
    assert names == {"Основной зал", "Каминный"}


def test_get_venue_includes_halls_without_dropping_fields(client):
    owner, _org, venue = _venue_owner(client)
    page = client.get(f"/venues/{venue['id']}", headers=auth_header(owner["token"]))
    assert page.status_code == 200
    data = page.json()
    for key in (
        "id",
        "name",
        "city",
        "capacity",
        "verified",
        "facts",
        "tariffs",
        "slots",
        "halls",
        "publication_enabled",
        "publication_state_version",
        "publication_eligible",
        "publication_reason_codes",
        "photos",
    ):
        assert key in data
    assert data["id"] == venue["id"]
    assert data["name"] == "Лофт"
    assert data["city"] == "Москва"
    assert data["capacity"] == 120
    assert data["tariffs"] == []
    assert data["slots"] == []
    assert data["publication_enabled"] is False
    assert isinstance(data["publication_reason_codes"], list)
    assert len(data["halls"]) == 1
    assert data["halls"][0] == {
        "id": venue["hall_id"],
        "name": "Основной зал",
        "capacity": 120,
    }


def test_venue_owner_can_record_photo_and_calendar_evidence(client):
    owner, _org, venue = _venue_owner(client)
    headers = auth_header(owner["token"])
    photo = client.put(
        f"/venues/{venue['id']}/photos",
        json={
            "photo_url": "/design/puzzle-venue.png",
            "photo_source_url": "/design/puzzle-venue.png",
            "photo_rights_status": "owned",
            "rights_attested": True,
        },
        headers=headers,
    )
    assert photo.status_code == 200, photo.text
    evidence = client.put(
        f"/venues/{venue['id']}/publication-evidence",
        json={
            "calendar_confirmed_through": (
                datetime.now(timezone.utc) + timedelta(days=60)
            ).isoformat()
        },
        headers=headers,
    )
    assert evidence.status_code == 200, evidence.text
    page = client.get(f"/venues/{venue['id']}", headers=headers).json()
    assert page["photos"]
    assert page["calendar_confirmed_through"] is not None
    assert "media" not in page["publication_reason_codes"] or page["publication_eligible"] is False



def test_create_hall_writes_audit(client):
    owner, _org, venue = _venue_owner(client)
    created = client.post(
        f"/venues/{venue['id']}/halls",
        json={"name": "Терраса", "capacity": 30},
        headers=auth_header(owner["token"]),
    )
    assert created.status_code == 200
    hall_id = created.json()["id"]
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import AuditLog

        row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "hall.created", AuditLog.entity_id == hall_id)
            .one()
        )
        assert row.entity_type == "hall"
    finally:
        db.close()
