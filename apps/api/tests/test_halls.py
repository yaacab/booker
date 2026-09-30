from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, grant_team_plan, register


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


def _add_publication_materials(client, venue_id: str, *, with_calendar: bool) -> None:
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import AvailabilitySlot, Venue, VenueHall, VenuePhoto, VenueTariff

        venue = db.get(Venue, venue_id)
        venue.moderation_status = "published"
        venue.availability_mode = "owner"
        venue.partnership_status = "verified"
        venue.is_claimed = True
        venue.verified = True
        hall = db.query(VenueHall).filter(VenueHall.venue_id == venue_id).one()
        db.add(VenueTariff(venue_id=venue_id, title="Серверный тариф", honorarium_rub=50000))
        db.add(
            VenuePhoto(
                venue_id=venue_id,
                photo_url=f"https://venue.example/{venue_id}.jpg",
                photo_source_url="https://venue.example/gallery",
                photo_rights_status="official_permission",
            )
        )
        if with_calendar:
            horizon = datetime.now(timezone.utc) + timedelta(days=31)
            db.add(
                AvailabilitySlot(
                    resource_type="hall",
                    resource_id=hall.id,
                    starts_at=horizon,
                    ends_at=horizon + timedelta(hours=4),
                    status="open",
                )
            )
        db.commit()
    finally:
        db.close()


def test_create_venue_makes_default_hall_and_lists_for_member(client):
    owner, _org, venue = _venue_owner(client)
    listed = client.get(f"/venues/{venue['id']}/halls", headers=auth_header(owner["token"]))
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == venue["hall_id"]
    assert items[0]["name"] == "Основной зал"
    assert items[0]["capacity"] == 120
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import Venue

        assert db.get(Venue, venue["id"]).moderation_status == "needs_review"
    finally:
        db.close()


def test_public_halls_require_catalog_or_member(client):
    owner, _org, venue = _venue_owner(client)
    stranger = register(client, "halls-stranger@booker.test", "Stranger")

    anon = client.get(f"/venues/{venue['id']}/halls")
    assert anon.status_code == 401

    foreign = client.get(f"/venues/{venue['id']}/halls", headers=auth_header(stranger["token"]))
    assert foreign.status_code == 403

    _add_publication_materials(client, venue["id"], with_calendar=False)
    start = datetime.now(timezone.utc) + timedelta(days=31)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "hall",
            "resource_id": venue["hall_id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=4)).isoformat(),
        },
        headers=auth_header(owner["token"]),
    )
    assert slot.status_code == 200, slot.text

    public = client.get(f"/venues/{venue['id']}/halls")
    assert public.status_code == 200, public.text
    assert {h["id"] for h in public.json()["items"]} == {venue["hall_id"]}


def test_post_hall_requires_writer_not_viewer(client):
    owner, org, venue = _venue_owner(client)
    viewer = register(client, "halls-viewer@booker.test", "Viewer")
    grant_team_plan(client, org['id'])
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
    _owner, _org, venue = _venue_owner(client)
    _add_publication_materials(client, venue["id"], with_calendar=True)
    page = client.get(f"/venues/{venue['id']}")
    assert page.status_code == 200
    data = page.json()
    for key in ("id", "name", "city", "capacity", "verified", "facts", "tariffs", "slots", "halls"):
        assert key in data
    assert data["id"] == venue["id"]
    assert data["name"] == "Лофт"
    assert data["city"] == "Москва"
    assert data["capacity"] == 120
    assert len(data["tariffs"]) == 1
    assert len(data["slots"]) == 1
    assert len(data["halls"]) == 1
    assert data["halls"][0] == {
        "id": venue["hall_id"],
        "name": "Основной зал",
        "capacity": 120,
    }


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
