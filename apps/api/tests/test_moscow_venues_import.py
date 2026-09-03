"""Open-data Moscow venues import with synthetic 30-day slots."""

from booker_api.seed_venues_moscow import import_moscow_venues


def test_import_moscow_venues_idempotent_and_searchable(client):
    db = client.app.state.SessionLocal()
    try:
        first = import_moscow_venues(db)
        assert first["created_venues"] >= 20
        assert first["slots_created"] > 0

        second = import_moscow_venues(db)
        assert second["created_venues"] == 0
        assert second["updated_venues"] >= 20
    finally:
        db.close()

    res = client.get("/catalog/search", params={"city": "Москва", "category": "venue"})
    assert res.status_code == 200
    venues = res.json()["venues"]
    assert len(venues) >= 20
    open_data = [v for v in venues if v.get("availability_mode") == "synthetic"]
    assert len(open_data) >= 20
    sample = open_data[0]
    assert sample.get("address") or sample.get("metro")

    detail = client.get(f"/venues/{sample['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["availability_mode"] == "synthetic"
    note = body["facts"]["note"].lower()
    assert "ориентировочный" in note or "синтетич" in note
    assert len(body["slots"]) >= 20
