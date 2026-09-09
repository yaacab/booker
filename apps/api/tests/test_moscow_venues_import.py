"""Open-data Moscow venues import with synthetic availability slots."""

from booker_api.seed_venues_moscow import import_moscow_venues


def test_import_moscow_venues_idempotent_and_searchable(client):
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import VenueSource

        first = import_moscow_venues(db)
        assert first["total_in_file"] >= 280
        assert first["created_venues"] >= 280
        assert first["published"] >= 20
        assert first["needs_review"] >= 250
        assert first["slots_created"] > 0
        assert db.query(VenueSource).count() == first["total_in_file"]

        second = import_moscow_venues(db)
        assert second["created_venues"] == 0
        assert second["updated_venues"] >= 280
        assert db.query(VenueSource).count() == first["total_in_file"]
    finally:
        db.close()

    res = client.get("/catalog/search", params={"city": "Москва", "category": "venue"})
    assert res.status_code == 200
    venues = res.json()["venues"]
    assert len(venues) == first["published"]
    open_data = [v for v in venues if v.get("availability_mode") == "synthetic"]
    assert len(open_data) == first["published"]
    sample = open_data[0]
    assert sample.get("address") or sample.get("metro")
    assert sample["public_disclosure"] == "Информация из открытых источников"

    detail = client.get(f"/venues/{sample['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["availability_mode"] == "synthetic"
    note = body["facts"]["note"].lower()
    assert "ориентировочный" in note or "синтетич" in note
    # Bulk open-data rows get 14 synthetic days; curated wave keeps 30.
    assert len(body["slots"]) >= 14


def test_import_keeps_halls_field_sources_and_batch_coverage(client, monkeypatch):
    from booker_api import seed_venues_moscow
    from booker_api.models import VenueHall, VenueImportBatch, VenueSource

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
                "description": "Пространство для частных и корпоративных событий.",
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
    finally:
        db.close()
