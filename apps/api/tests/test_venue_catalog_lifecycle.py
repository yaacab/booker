from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, register


def _admin(client) -> dict:
    user = register(client, "venue-catalog-admin@booker.test", "Catalog Admin")
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import User

        row = db.get(User, user["user_id"])
        row.is_platform_admin = True
        db.commit()
    finally:
        db.close()
    return user


def _open_data_venue(client) -> dict:
    owner = register(client, "venue-catalog-owner@booker.test", "Venue Owner")
    org = client.post(
        "/orgs",
        json={"name": "Тестовая площадка", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={
            "organization_id": org["id"],
            "name": "Площадка из открытых данных",
            "city": "Москва",
            "capacity": 120,
        },
        headers=auth_header(owner["token"]),
    ).json()
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import Venue

        row = db.get(Venue, venue["id"])
        row.address = "Москва, Тестовая улица, 1"
        row.listing_origin = "open_data"
        row.source_type = "automated_import"
        row.partnership_status = "unverified_listing"
        row.is_claimed = False
        row.moderation_status = "published"
        row.completeness_score = 70
        row.last_crawled_at = datetime.now(timezone.utc)
        row.data_freshness_status = "fresh"
        db.commit()
    finally:
        db.close()
    return venue


def _add_publication_materials(client, venue_id: str) -> None:
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import AvailabilitySlot, Venue, VenueHall, VenuePhoto, VenueTariff

        venue = db.get(Venue, venue_id)
        venue.availability_mode = "owner"
        hall = db.query(VenueHall).filter(VenueHall.venue_id == venue_id).one()
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
        db.add(VenueTariff(venue_id=venue_id, title="Серверный тариф", honorarium_rub=100000))
        db.add(
            VenuePhoto(
                venue_id=venue_id,
                photo_url="https://venue.example/approved.jpg",
                photo_source_url="https://venue.example/gallery",
                photo_rights_status="official_permission",
            )
        )
        db.commit()
    finally:
        db.close()


def test_admin_status_change_preserves_origin_and_updates_public_disclosure(client):
    venue = _open_data_venue(client)
    _add_publication_materials(client, venue["id"])
    admin = _admin(client)

    before = client.get(f"/venues/{venue['id']}")
    assert before.status_code == 404

    changed = client.post(
        f"/admin/venue-catalog/venues/{venue['id']}/status",
        json={
            "partnership_status": "verified",
            "comment": "Представитель подтвердил данные",
        },
        headers=auth_header(admin["token"]),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["source_type"] == "automated_import"
    assert changed.json()["partnership_status"] == "verified"
    assert changed.json()["is_claimed"] is True

    after = client.get(f"/venues/{venue['id']}")
    assert after.status_code == 200
    assert after.json()["source_type"] == "automated_import"
    assert after.json()["public_disclosure"] is None

    history = client.get(
        f"/admin/venue-catalog/venues/{venue['id']}/history",
        headers=auth_header(admin["token"]),
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["new_status"] == "verified"


def test_moderation_hides_venue_and_freshness_marks_old_data(client):
    venue = _open_data_venue(client)
    _add_publication_materials(client, venue["id"])
    admin = _admin(client)
    verified = client.post(
        f"/admin/venue-catalog/venues/{venue['id']}/status",
        json={"partnership_status": "verified", "comment": "Проверено"},
        headers=auth_header(admin["token"]),
    )
    assert verified.status_code == 200
    assert client.get(f"/venues/{venue['id']}").status_code == 200
    hidden = client.post(
        f"/admin/venue-catalog/venues/{venue['id']}/moderation",
        json={"moderation_status": "needs_review", "comment": "Недостаточно данных"},
        headers=auth_header(admin["token"]),
    )
    assert hidden.status_code == 200
    assert client.get(f"/venues/{venue['id']}").status_code == 404

    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import Venue

        row = db.get(Venue, venue["id"])
        row.moderation_status = "published"
        row.last_crawled_at = datetime.now(timezone.utc) - timedelta(days=181)
        row.last_verified_at = datetime.now(timezone.utc) - timedelta(days=181)
        db.commit()
    finally:
        db.close()
    refreshed = client.post(
        "/admin/venue-catalog/freshness/recalculate",
        headers=auth_header(admin["token"]),
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["stale"] == 1


def test_manual_publication_requires_contract_gate(client):
    venue = _open_data_venue(client)
    admin = _admin(client)
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import Venue

        row = db.get(Venue, venue["id"])
        row.moderation_status = "needs_review"
        row.availability_mode = "research"
        db.commit()
    finally:
        db.close()

    blocked = client.post(
        f"/admin/venue-catalog/venues/{venue['id']}/moderation",
        json={"moderation_status": "published", "comment": "Проверка гейта"},
        headers=auth_header(admin["token"]),
    )
    assert blocked.status_code == 409
    assert set(blocked.json()["detail"]["blockers"]) == {
        "representative",
        "verification",
        "owner_calendar",
        "calendar_30_days",
        "price",
        "media",
    }

    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import (
            AvailabilitySlot,
            Venue,
            VenueHall,
            VenuePhoto,
            VenueTariff,
        )

        row = db.get(Venue, venue["id"])
        row.availability_mode = "owner"
        row.partnership_status = "verified"
        row.is_claimed = True
        row.verified = True
        hall = db.query(VenueHall).filter(VenueHall.venue_id == row.id).one()
        near = datetime.now(timezone.utc) + timedelta(days=1)
        db.add(
            AvailabilitySlot(
                resource_type="hall",
                resource_id=hall.id,
                starts_at=near,
                ends_at=near + timedelta(hours=4),
                status="open",
            )
        )
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
        db.add(VenueTariff(venue_id=row.id, title="Серверный тариф", honorarium_rub=100000))
        db.add(
            VenuePhoto(
                venue_id=row.id,
                photo_url="https://venue.example/approved.jpg",
                photo_source_url="https://venue.example/gallery",
                photo_rights_status="official_permission",
            )
        )
        db.commit()
    finally:
        db.close()

    published = client.post(
        f"/admin/venue-catalog/venues/{venue['id']}/moderation",
        json={"moderation_status": "published", "comment": "Все условия выполнены"},
        headers=auth_header(admin["token"]),
    )
    assert published.status_code == 200, published.text
    assert published.json()["moderation_status"] == "published"
    assert client.get(f"/venues/{venue['id']}").status_code == 200
    visible = client.get("/catalog/search", params={"city": "Москва", "kind": "venue"})
    assert venue["id"] in {item["id"] for item in visible.json()["venues"]}

    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import VenueTariff

        db.query(VenueTariff).filter(VenueTariff.venue_id == venue["id"]).delete()
        db.commit()
    finally:
        db.close()
    assert client.get(f"/venues/{venue['id']}").status_code == 404
    hidden = client.get("/catalog/search", params={"city": "Москва", "kind": "venue"})
    assert venue["id"] not in {item["id"] for item in hidden.json()["venues"]}
