"""Open-data Moscow venues import without invented availability."""

from datetime import timedelta

from booker_api.security import now
from booker_api.seed_venues_moscow import import_moscow_venues


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

    demo = client.get("/catalog/demo/venues", params={"city": "Москва", "limit": 300})
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
        assert result["published"] == 1
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
        venue.availability_mode = "owner"
        venue.verified = True
        venue.partnership_status = "verified"
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
        db.commit()
    finally:
        db.close()

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
