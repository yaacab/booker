from uuid import uuid4

from booker_api.models import ArtistTariff, AuditLog, Booking, Offer, Venue, VenueTariff
from tests.conftest import activate_venue, auth_header, register


def fixtures(client):
    user = register(client, "planning-owner@booker.test")
    headers = auth_header(user["token"])
    org = client.post("/orgs", headers=headers, json={"name": "Участники", "kind": "artist"}).json()
    artist = client.post("/artists", headers=headers, json={"organization_id": org["id"], "name": "DJ"}).json()
    venue_org = client.post("/orgs", headers=headers, json={"name": "Залы", "kind": "venue"}).json()
    venue = client.post("/venues", headers=headers, json={"organization_id": venue_org["id"], "name": "Зал", "capacity": 100}).json()
    return headers, artist["id"], venue["id"]


def query(artist_id, venue_id):
    return {"selections": [{"resource_type": "artist", "resource_id": artist_id}, {"resource_type": "venue", "resource_id": venue_id}]}


def test_estimate_uses_exact_public_ranges_without_fees_or_invented_markup(client, SessionLocal):
    _, artist, venue = fixtures(client)
    with SessionLocal() as db:
        db.add_all([ArtistTariff(artist_id=artist, title="2 часа", hours=2, honorarium_rub=60000), ArtistTariff(artist_id=artist, title="4 часа", hours=4, honorarium_rub=90000), VenueTariff(venue_id=venue, title="Аренда", honorarium_rub=100000)])
        db.commit()
    activate_venue(client, venue)
    body = query(artist, venue)
    body["selections"].append(body["selections"][0])  # same supplier selected twice is not charged twice
    response = client.post("/event-studio/estimate", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state"] == "complete"
    assert result["min_rub"] == 160000 and result["max_rub"] == 190000
    assert result["selected_count"] == result["priced_count"] == 2
    assert [s["hours"] for s in result["items"][0]["sources"]] == [2, 4]
    assert result["is_orientation"] and result["currency"] == "RUB"
    assert "quote_id" not in result and "availability" not in result
    with SessionLocal() as db:
        assert db.query(Offer).count() == db.query(Booking).count() == 0
        record = db.query(AuditLog).filter_by(action="event.estimate_viewed").one()
        assert "planning-owner" not in record.payload


def test_unknown_partial_zero_and_missing_profiles_are_explicit(client, SessionLocal):
    _, artist, venue = fixtures(client)
    body = query(artist, venue)
    result = client.post("/event-studio/estimate", json=body).json()
    assert result["state"] == "unknown" and result["min_rub"] is None
    with SessionLocal() as db:
        db.add(ArtistTariff(artist_id=artist, title="Указан ноль", hours=1, honorarium_rub=0)); db.commit()
    result = client.post("/event-studio/estimate", json=body).json()
    assert result["state"] == "partial" and result["min_rub"] == result["max_rub"] == 0
    assert result["priced_count"] == 1 and result["selected_count"] == 2
    empty = client.post("/event-studio/estimate", json={"selections": []}).json()
    assert empty["state"] == "empty" and empty["min_rub"] is None
    missing = client.post("/event-studio/estimate", json=query(artist, str(uuid4()))).json()["items"][1]
    assert missing["state"] == "unavailable" and missing["name"] is None


def test_hidden_venue_prices_are_not_exposed_even_to_its_owner(client, SessionLocal):
    headers, artist, venue = fixtures(client)
    with SessionLocal() as db:
        db.get(Venue, venue).moderation_status = "needs_review"
        db.add(VenueTariff(venue_id=venue, title="Private package", honorarium_rub=777)); db.commit()
    result = client.post("/event-studio/estimate", json=query(artist, venue), headers=headers).json()
    hidden = result["items"][1]
    assert hidden["state"] == "unavailable" and hidden["name"] is None
    assert hidden["min_rub"] is None and hidden["sources"] == []
    # Numeric substrings may legitimately occur in opaque UUIDs. Check price fields.
    assert result["min_rub"] is None and result["max_rub"] is None
    assert all(item["sources"] == [] for item in result["items"])
    assert "Private package" not in str(result)


def test_no_price_injection_bounded_input_and_feature_gate(client, monkeypatch):
    _, artist, venue = fixtures(client)
    body = query(artist, venue)
    assert client.post("/event-studio/estimate", json={**body, "min_rub": 1}).status_code == 422
    assert client.post("/event-studio/estimate", json={"selections": body["selections"] * 16}).status_code == 422
    assert client.post("/event-studio/estimate", json={"selections": [{"resource_type": "artist", "resource_id": artist, "honorarium_rub": 1}]}).status_code == 422
    from booker_api.config import settings
    monkeypatch.setattr(settings, "smart_matching", False)
    assert client.post("/event-studio/estimate", json=body).status_code == 503
