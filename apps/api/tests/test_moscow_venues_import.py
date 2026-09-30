"""Open-data Moscow venues import without invented availability."""

from datetime import timedelta

from booker_api.security import now
from booker_api.seed_venues_moscow import import_moscow_venues
from tests.conftest import auth_header, register


def _admin(client) -> dict:
    user = register(client, "moscow-import-admin@booker.test", "Import Admin")
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import User

        row = db.get(User, user["user_id"])
        row.is_platform_admin = True
        db.commit()
    finally:
        db.close()
    return user


def test_import_moscow_venues_idempotent_and_searchable(client):
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import VenueSource

        first = import_moscow_venues(db)
        assert first["total_in_file"] >= 280
        assert first["created_venues"] >= 280
        assert first["published"] == 0
        assert first["needs_review"] == first["total_in_file"]
        assert first["slots_created"] == 0
        first_source_count = db.query(VenueSource).count()
        assert first_source_count >= first["total_in_file"]
        assert first["with_contacts"] == 300
        assert first["with_prices"] == 300
        assert first["with_photos"] == 0

        second = import_moscow_venues(db)
        assert second["created_venues"] == 0
        assert second["updated_venues"] >= 280
        assert db.query(VenueSource).count() == first_source_count
    finally:
        db.close()

    res = client.get("/catalog/search", params={"city": "Москва", "category": "venue"})
    assert res.status_code == 200
    assert res.json()["venues"] == []

    demo_without_auth = client.get(
        "/catalog/demo/venues", params={"city": "Москва", "limit": 300}
    )
    assert demo_without_auth.status_code == 401

    non_admin = register(client, "moscow-import-viewer@booker.test", "Import Viewer")
    demo_as_non_admin = client.get(
        "/catalog/demo/venues",
        params={"city": "Москва", "limit": 300},
        headers=auth_header(non_admin["token"]),
    )
    assert demo_as_non_admin.status_code == 403

    admin = _admin(client)
    demo = client.get(
        "/catalog/demo/venues",
        params={"city": "Москва", "limit": 300},
        headers=auth_header(admin["token"]),
    )
    assert demo.status_code == 200
    body = demo.json()
    assert body["mode"] == "investor_demo_research"
    assert body["count"] == 300
    assert len(body["items"]) == 300
    assert all(item["tariff_from_rub"] > 0 for item in body["items"])
    assert all(item["cover_photo"]["url"].startswith("https://") for item in body["items"])
    assert all(item["cover_photo"]["rights_status"] == "unknown" for item in body["items"])


def test_import_keeps_halls_field_sources_and_batch_coverage(client, monkeypatch):
    from booker_api import seed_venues_moscow
    from booker_api.models import (
        AvailabilitySlot,
        Venue,
        VenueHall,
        VenueImportBatch,
        VenuePhoto,
        VenueSource,
        VenueTariff,
    )

    payload = {
        "version": 91,
        "batch_id": "moscow-loft-cao-91",
        "city": "Москва",
        "batch": {"category": "loft", "administrative_district": "ЦАО"},
        "venues": [
            {
                "name": "Тестовый лофт с залами",
                "venue_type": "loft",
                "address": "Москва, Тестовый переулок, 7",
                "capacity": 120,
                "description": (
                    "Лофт с двумя изолированными залами для частных и корпоративных событий, "
                    "сценой, зоной приёма гостей и отдельным входом."
                ),
                "source_url": "https://venue.example/about",
                "attribution": "official_site",
                "official_website": "https://venue.example",
                "phone": "+7 999 123-45-67",
                "tariff_from_rub": 90000,
                "halls": [
                    {"name": "Белый зал", "capacity": 80},
                    {"name": "Малый зал", "capacity": 40},
                ],
                "sources": [
                    {
                        "field_name": "price",
                        "source_url": "https://venue.example/prices",
                        "source_kind": "official_site",
                    }
                ],
                "photos": [
                    {
                        "photo_url": "https://venue.example/photo.jpg",
                        "photo_source_url": "https://venue.example/gallery",
                        "photo_rights_status": "official_permission",
                    },
                    {
                        "photo_url": "https://venue.example/unlicensed.jpg",
                        "photo_source_url": "https://venue.example/gallery",
                        "photo_rights_status": "unknown",
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(seed_venues_moscow, "_load_payload", lambda: payload)
    db = client.app.state.SessionLocal()
    try:
        result = seed_venues_moscow.import_moscow_venues(db)
        batch = db.get(VenueImportBatch, "moscow-loft-cao-91")
        assert result["published"] == 0
        assert result["needs_review"] == 1
        assert result["with_contacts"] == 1
        assert result["with_prices"] == 1
        assert result["with_photos"] == 1
        assert result["with_official_website"] == 1
        assert batch.category == "loft"
        assert batch.administrative_district == "ЦАО"
        assert batch.with_contacts_count == 1
        assert db.query(VenueHall).count() == 2
        assert {row.name for row in db.query(VenueHall).all()} == {"Белый зал", "Малый зал"}
        assert db.query(VenueSource).count() == 2
        assert db.query(VenueTariff).count() == 1
        venue = db.query(Venue).filter(Venue.name == "Тестовый лофт с залами").one()
        venue.listing_origin = "owner"
        venue.availability_mode = "owner"
        venue.verified = True
        venue.partnership_status = "verified"
        venue.is_claimed = True
        hall = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).first()
        start = now() + timedelta(days=1)
        db.add(
            AvailabilitySlot(
                resource_type="hall",
                resource_id=hall.id,
                starts_at=start,
                ends_at=start + timedelta(hours=4),
                status="open",
            )
        )
        horizon_start = now() + timedelta(days=31)
        db.add(
            AvailabilitySlot(
                resource_type="hall",
                resource_id=hall.id,
                starts_at=horizon_start,
                ends_at=horizon_start + timedelta(hours=4),
                status="open",
            )
        )
        db.commit()
        venue_id = venue.id
    finally:
        db.close()

    admin = _admin(client)
    published = client.post(
        f"/admin/venue-catalog/venues/{venue_id}/moderation",
        json={"moderation_status": "published", "comment": "Гейт подтверждён"},
        headers=auth_header(admin["token"]),
    )
    assert published.status_code == 200, published.text

    search = client.get("/catalog/search", params={"city": "Москва", "category": "venue"})
    assert search.status_code == 200
    item = next(row for row in search.json()["venues"] if row["name"] == "Тестовый лофт с залами")
    assert item["cover_photo"] == {
        "url": "https://venue.example/photo.jpg",
        "source_url": "https://venue.example/gallery",
        "rights_status": "official_permission",
    }

    detail = client.get(f"/venues/{item['id']}")
    assert detail.status_code == 200
    assert detail.json()["photos"] == [item["cover_photo"]]
    assert all(photo["rights_status"] != "unknown" for photo in detail.json()["photos"])

    payload["venues"][0].update(
        {
            "address": "Москва, Чужой переулок, 99",
            "description": "Исследовательский текст не должен заменить данные представителя.",
            "capacity": 999,
            "phone": "+7 000 000-00-00",
            "official_website": "https://research.example",
            "tariff_from_rub": 1,
            "halls": [{"name": "Исследовательский зал", "capacity": 999}],
            "photos": [
                {
                    "photo_url": "https://research.example/unknown.jpg",
                    "photo_source_url": "https://research.example/source",
                    "photo_rights_status": "unknown",
                }
            ],
        }
    )
    db = client.app.state.SessionLocal()
    try:
        refreshed = seed_venues_moscow.import_moscow_venues(db)
        venue = db.get(Venue, venue_id)
        halls = db.query(VenueHall).filter(VenueHall.venue_id == venue_id).all()
        tariffs = db.query(VenueTariff).filter(VenueTariff.venue_id == venue_id).all()
        photos = db.query(VenuePhoto).filter(VenuePhoto.venue_id == venue_id).all()
        assert refreshed["preserved_venues"] == 1
        assert venue.listing_origin == "owner"
        assert venue.availability_mode == "owner"
        assert venue.partnership_status == "verified"
        assert venue.is_claimed is True
        assert venue.address == "Москва, Тестовый переулок, 7"
        assert venue.capacity == 120
        assert venue.phone == "+7 999 123-45-67"
        assert venue.official_website == "https://venue.example"
        assert {row.name: row.capacity for row in halls} == {"Белый зал": 80, "Малый зал": 40}
        assert [row.honorarium_rub for row in tariffs] == [90000]
        assert {row.photo_url for row in photos} == {
            "https://venue.example/photo.jpg",
            "https://venue.example/unlicensed.jpg",
        }
    finally:
        db.close()


def test_reimport_deletes_only_open_synthetic_slots(client, monkeypatch):
    from booker_api import seed_venues_moscow
    from booker_api.models import (
        AvailabilitySlot,
        Booking,
        BookingHold,
        Event,
        Offer,
        Request,
        Venue,
        VenueHall,
    )

    payload = {
        "version": 92,
        "batch_id": "moscow-slot-cleanup-92",
        "city": "Москва",
        "venues": [
            {
                "name": "Тестовая research-площадка",
                "address": "Москва, Проверочная улица, 1",
                "capacity": 50,
                "description": "Research-карточка без выдуманной доступности и без публичной публикации.",
                "source_url": "https://research.example/venue",
                "attribution": "research",
            }
        ],
    }
    monkeypatch.setattr(seed_venues_moscow, "_load_payload", lambda: payload)
    db = client.app.state.SessionLocal()
    try:
        seed_venues_moscow.import_moscow_venues(db)
        venue = db.query(Venue).filter(Venue.name == "Тестовая research-площадка").one()
        hall = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).one()
        start = now() + timedelta(days=2)
        slots = {}
        for index, status in enumerate(("open", "held", "confirmed")):
            slot = AvailabilitySlot(
                resource_type="hall",
                resource_id=hall.id,
                starts_at=start + timedelta(days=index),
                ends_at=start + timedelta(days=index, hours=4),
                status=status,
                external_uid=f"synthetic:open:{status}",
            )
            db.add(slot)
            slots[status] = slot
        referenced_open = AvailabilitySlot(
            resource_type="hall",
            resource_id=hall.id,
            starts_at=start + timedelta(days=4),
            ends_at=start + timedelta(days=4, hours=4),
            status="open",
            external_uid="synthetic:open:expired-hold",
        )
        db.add(referenced_open)
        db.flush()
        event = Event(
            organization_id=venue.organization_id,
            title="Истёкший hold",
            city="Москва",
            event_date=referenced_open.starts_at,
            guest_count=20,
        )
        db.add(event)
        db.flush()
        request = Request(
            event_id=event.id,
            resource_type="hall",
            resource_id=hall.id,
            supplier_org_id=venue.organization_id,
        )
        db.add(request)
        db.flush()
        offer = Offer(request_id=request.id)
        db.add(offer)
        db.flush()
        booking = Booking(
            event_id=event.id,
            offer_id=offer.id,
            slot_id=referenced_open.id,
            status="Cancelled",
        )
        db.add(booking)
        db.flush()
        db.add(
            BookingHold(
                booking_id=booking.id,
                slot_id=referenced_open.id,
                expires_at=now() - timedelta(minutes=5),
                status="expired",
            )
        )
        db.commit()

        seed_venues_moscow.import_moscow_venues(db)
        remaining = {
            row.external_uid: row.status
            for row in db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.resource_id == hall.id)
            .all()
        }
        assert "synthetic:open:open" not in remaining
        assert remaining == {
            "synthetic:open:held": "held",
            "synthetic:open:confirmed": "confirmed",
            "synthetic:open:expired-hold": "open",
        }
        assert db.get(Booking, booking.id).slot_id == referenced_open.id
        assert db.query(BookingHold).filter(BookingHold.slot_id == referenced_open.id).count() == 1
    finally:
        db.close()
