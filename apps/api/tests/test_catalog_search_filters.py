"""Catalog search filters — Spec v3 E01–E03 / Wave 1."""

from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, register


def _future_slot(hours=18):
    start = datetime.now(timezone.utc) + timedelta(days=10)
    start = start.replace(hour=hours, minute=0, second=0, microsecond=0)
    return start.isoformat(), (start + timedelta(hours=4)).isoformat()


def _make_venue_publication_ready(client, venue_id: str) -> None:
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import AvailabilitySlot, Venue, VenueHall, VenuePhoto, VenueTariff

        venue = db.get(Venue, venue_id)
        venue.moderation_status = "published"
        venue.availability_mode = "owner"
        venue.partnership_status = "verified"
        venue.is_claimed = True
        venue.verified = True
        hall = db.query(VenueHall).filter(VenueHall.venue_id == venue_id).first()
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
        db.add(VenueTariff(venue_id=venue_id, title="Серверный тариф", honorarium_rub=50000))
        db.add(
            VenuePhoto(
                venue_id=venue_id,
                photo_url=f"https://venue.example/{venue_id}.jpg",
                photo_source_url="https://venue.example/gallery",
                photo_rights_status="official_permission",
            )
        )
        db.commit()
    finally:
        db.close()


def test_seeded_club_signal_is_publicly_visible(client):
    from booker_api.models import (
        AvailabilitySlot,
        Organization,
        TeamMember,
        Venue,
        VenueHall,
        VenuePhoto,
        VenueTariff,
    )
    from booker_api.seed import seed
    from booker_api.venue_catalog import publication_gate_blockers

    SessionLocal = client.app.state.SessionLocal
    db = SessionLocal()
    try:
        research_org = Organization(name="Research import", kind="venue", city="Москва")
        db.add(research_org)
        db.flush()
        research_venue = Venue(
            organization_id=research_org.id,
            name="Клуб Сигнал",
            city="Москва",
            listing_origin="open_data",
            availability_mode="research",
            source_type="automated_import",
            partnership_status="unverified_listing",
            is_claimed=False,
            is_partner=False,
            verified=False,
            moderation_status="needs_review",
        )
        db.add(research_venue)
        db.commit()

        seed(db)
        seed(db)

        venue = (
            db.query(Venue)
            .join(Organization, Organization.id == Venue.organization_id)
            .filter(Venue.name == "Клуб Сигнал", Organization.name == "Сигнал")
            .one()
        )
        assert venue.listing_origin == "owner"
        assert venue.source_type == "owner_submission"
        assert venue.availability_mode == "owner"
        assert venue.partnership_status == "verified"
        assert venue.is_claimed is True
        assert venue.is_partner is True
        assert publication_gate_blockers(db, venue) == []
        db.refresh(research_venue)
        assert research_venue.source_type == "automated_import"
        assert research_venue.availability_mode == "research"
        assert research_venue.partnership_status == "unverified_listing"
        assert research_venue.moderation_status == "needs_review"
        hall_ids = [
            hall_id
            for (hall_id,) in db.query(VenueHall.id).filter(VenueHall.venue_id == venue.id)
        ]
        assert (
            db.query(TeamMember)
            .filter(TeamMember.organization_id == venue.organization_id)
            .count()
            == 1
        )
        assert (
            db.query(VenueTariff)
            .filter(VenueTariff.venue_id == venue.id, VenueTariff.honorarium_rub > 0)
            .count()
            == 1
        )
        assert (
            db.query(VenuePhoto)
            .filter(
                VenuePhoto.venue_id == venue.id,
                VenuePhoto.photo_rights_status == "official_permission",
            )
            .count()
            == 1
        )
        assert (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_type == "hall",
                AvailabilitySlot.resource_id.in_(hall_ids),
                AvailabilitySlot.status == "open",
                AvailabilitySlot.ends_at >= datetime.now(timezone.utc) + timedelta(days=30),
            )
            .count()
            >= 1
        )
    finally:
        db.close()

    response = client.get("/catalog/search", params={"city": "Москва", "kind": "venue"})
    assert response.status_code == 200
    signal = next(item for item in response.json()["venues"] if item["name"] == "Клуб Сигнал")
    assert signal["availability_mode"] == "owner"
    assert signal["partnership_status"] == "verified"
    assert signal["honorarium_from_rub"] == 220000
    assert signal["cover_photo"] == {
        "url": "/design/puzzle-venue.png",
        "source_url": "https://bukergo.ru/design/puzzle-venue.png",
        "rights_status": "official_permission",
    }


def test_search_artist_format_travel_budget(client):
    owner = register(client, "w1-art@booker.test", "W1 Art")
    org = client.post(
        "/orgs",
        json={"name": "W1 Artist Org", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    hi = client.post(
        "/artists",
        json={
            "organization_id": org["id"],
            "name": "Hi Budget DJ",
            "city": "Москва",
            "category": "dj",
            "rider_json": '{"format":"club set","travel_ok":true}',
        },
        headers=auth_header(owner["token"]),
    ).json()
    lo = client.post(
        "/artists",
        json={
            "organization_id": org["id"],
            "name": "Lo Budget Host",
            "city": "Москва",
            "category": "host",
            "rider_json": '{"format":"wedding toast","travel_ok":false}',
        },
        headers=auth_header(owner["token"]),
    ).json()
    starts, ends = _future_slot()
    for artist_id, price in ((hi["id"], 150000), (lo["id"], 40000)):
        client.post(
            f"/artists/{artist_id}/tariffs",
            json={"title": "Сет", "honorarium_rub": price, "hours": 2},
            headers=auth_header(owner["token"]),
        )
        assert (
            client.post(
                "/slots",
                json={
                    "resource_type": "artist",
                    "resource_id": artist_id,
                    "starts_at": starts,
                    "ends_at": ends,
                },
                headers=auth_header(owner["token"]),
            ).status_code
            == 200
        )

    by_format = client.get("/catalog/search", params={"city": "Москва", "format": "wedding"}).json()
    names = {i["name"] for i in by_format["items"]}
    assert "Lo Budget Host" in names
    assert "Hi Budget DJ" not in names

    by_travel = client.get("/catalog/search", params={"city": "Москва", "travel": True}).json()
    names = {i["name"] for i in by_travel["items"]}
    assert "Hi Budget DJ" in names
    assert "Lo Budget Host" not in names

    by_budget = client.get("/catalog/search", params={"city": "Москва", "budget_max": 50000}).json()
    names = {i["name"] for i in by_budget["items"]}
    assert "Lo Budget Host" in names
    assert "Hi Budget DJ" not in names


def test_search_venue_guests_matching_halls(client):
    owner = register(client, "w1-ven@booker.test", "W1 Ven")
    org = client.post(
        "/orgs",
        json={"name": "W1 Venue Org", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    small = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Малый зал 40", "city": "Москва", "capacity": 40},
        headers=auth_header(owner["token"]),
    ).json()
    large = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Банкет 120", "city": "Москва", "capacity": 120},
        headers=auth_header(owner["token"]),
    ).json()
    _make_venue_publication_ready(client, small["id"])
    _make_venue_publication_ready(client, large["id"])
    # Extra small hall on large venue should not satisfy guests=80 alone — capacity 120 hall does.
    client.post(
        f"/venues/{large['id']}/halls",
        json={"name": "Кабинет 20", "capacity": 20},
        headers=auth_header(owner["token"]),
    )
    starts, ends = _future_slot(19)
    for venue_id in (small["id"], large["id"]):
        halls = client.get(f"/venues/{venue_id}/halls", headers=auth_header(owner["token"])).json()["items"]
        for hall in halls:
            client.post(
                "/slots",
                json={
                    "resource_type": "hall",
                    "resource_id": hall["id"],
                    "starts_at": starts,
                    "ends_at": ends,
                },
                headers=auth_header(owner["token"]),
            )

    res = client.get(
        "/catalog/search",
        params={"city": "Москва", "kind": "venue", "guests": 80},
    ).json()
    names = {v["name"] for v in res["venues"]}
    assert "Банкет 120" in names
    assert "Малый зал 40" not in names
    banquet = next(v for v in res["venues"] if v["name"] == "Банкет 120")
    assert all(h["capacity"] >= 80 for h in banquet["matching_halls"])
    assert any(h["capacity"] >= 80 for h in banquet["matching_halls"])


def test_search_hides_synthetic_venue(client):
    """Research/synthetic availability cannot satisfy the owner-calendar gate."""
    owner = register(client, "w1-syn@booker.test", "W1 Syn")
    org = client.post(
        "/orgs",
        json={"name": "W1 Syn Org", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Синтетика Холл", "city": "Москва", "capacity": 90},
        headers=auth_header(owner["token"]),
    ).json()
    _make_venue_publication_ready(client, venue["id"])
    from booker_api.models import Venue

    SessionLocal = client.app.state.SessionLocal
    db = SessionLocal()
    try:
        row = db.get(Venue, venue["id"])
        assert row is not None
        row.availability_mode = "synthetic"
        row.district = "Хамовники"
        row.metro = "Парк культуры"
        db.commit()
    finally:
        db.close()

    halls = client.get(f"/venues/{venue['id']}/halls", headers=auth_header(owner["token"])).json()["items"]
    starts, ends = _future_slot(17)
    client.post(
        "/slots",
        json={
            "resource_type": "hall",
            "resource_id": halls[0]["id"],
            "starts_at": starts,
            "ends_at": ends,
        },
        headers=auth_header(owner["token"]),
    )
    res = client.get("/catalog/search", params={"city": "Москва", "kind": "venue"}).json()
    assert venue["id"] not in {v["id"] for v in res["venues"]}
    matching = client.get("/catalog/search", params={"district":" хамовники ","metro":"КУЛЬТУРЫ"}).json()
    assert venue["id"] not in {v["id"] for v in matching["venues"]}
    other = client.get("/catalog/search", params={"district":"Якиманка"}).json()
    assert venue["id"] not in {v["id"] for v in other["venues"]}
    wrong_metro = client.get("/catalog/search", params={"district":"Хамовники", "metro":"Сокол"}).json()
    assert venue["id"] not in {v["id"] for v in wrong_metro["venues"]}



def test_search_next_open_at_includes_timezone_offset(client):
    owner = register(client, "tz-art@booker.test", "TZ Art")
    org = client.post(
        "/orgs",
        json={"name": "TZ Artist Org", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={
            "organization_id": org["id"],
            "name": "TZ DJ",
            "city": "Москва",
            "category": "dj",
        },
        headers=auth_header(owner["token"]),
    ).json()
    starts, ends = _future_slot()
    assert (
        client.post(
            "/slots",
            json={
                "resource_type": "artist",
                "resource_id": artist["id"],
                "starts_at": starts,
                "ends_at": ends,
            },
            headers=auth_header(owner["token"]),
        ).status_code
        == 200
    )
    res = client.get("/catalog/search", params={"city": "Москва", "category": "dj"}).json()
    hit = next(i for i in res["items"] if i["name"] == "TZ DJ")
    assert hit["next_open_at"]
    assert hit["next_open_at"].endswith("+03:00") or hit["next_open_at"].endswith("+0300")
