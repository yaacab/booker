"""Bounded catalog pages preserve the existing public publication and slot gates."""

import json
from datetime import timedelta
from time import perf_counter

from sqlalchemy import event

from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    TeamMember,
    User,
    Venue,
    VenueHall,
    VenuePhoto,
    VenueTariff,
)
from booker_api.publication_eligibility import (
    artist_publication_eligibility,
    batch_publication_eligibility,
    venue_publication_eligibility,
)
from booker_api.security import now
from tests.conftest import auth_header, publish_venue, register


def _seed_artists(client, SessionLocal, count, *, published, matching=None):
    owner = register(client, f"page-owner-{count}@booker.test")
    org = client.post(
        "/orgs", json={"name": "Page artists", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    start = now() + timedelta(days=5)
    with SessionLocal() as db:
        user_id = db.query(User).filter(User.email == f"page-owner-{count}@booker.test").one().id
        for index in range(count):
            resource_id = f"artist-{index:03d}"
            is_public = index in published
            db.add(Artist(
                id=resource_id, organization_id=org["id"], name=resource_id,
                city="Москва", category="dj", verified=is_public,
                rider_json=json.dumps({"format": "selected" if index in (matching or set()) else "other"}),
                verified_status="approved" if is_public else "pending",
                publication_enabled=is_public, media_url="/test/artist.jpg",
                media_source_url="/test/artist.jpg", media_rights_status="owned",
                media_rights_attested_at=start if is_public else None,
                media_rights_attested_by_user_id=user_id if is_public else None,
                calendar_confirmed_through=start + timedelta(days=90) if is_public else None,
                calendar_confirmed_at=start if is_public else None,
                calendar_confirmed_by_user_id=user_id if is_public else None,
            ))
            if is_public:
                db.add(ArtistTariff(
                    artist_id=resource_id, title="Test tariff", honorarium_rub=50000,
                ))
                db.add(AvailabilitySlot(
                    resource_type="artist", resource_id=resource_id,
                    starts_at=start, ends_at=start + timedelta(hours=2), status="open",
                ))
        db.commit()
    return owner


def _seed_venues(client, SessionLocal, count):
    email = f"page-venues-{count}@booker.test"
    owner = register(client, email)
    org = client.post(
        "/orgs", json={"name": "Page venues", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    start = now() + timedelta(days=5)
    with SessionLocal() as db:
        user_id = db.query(User).filter(User.email == email).one().id
        for index in range(count):
            venue_id = f"venue-{index:03d}"
            hall_id = f"hall-{index:03d}"
            db.add(Venue(
                id=venue_id, organization_id=org["id"], name=venue_id, city="Москва",
                verified=True, verified_status="approved", publication_enabled=True,
                moderation_status="published", is_claimed=True,
                calendar_confirmed_through=start + timedelta(days=90),
                calendar_confirmed_at=start, calendar_confirmed_by_user_id=user_id,
            ))
            db.add(VenueHall(id=hall_id, venue_id=venue_id, name="Main", capacity=100))
            db.add(VenueTariff(venue_id=venue_id, title="Test venue", honorarium_rub=100000))
            db.add(VenuePhoto(
                venue_id=venue_id, photo_url=f"/test/{venue_id}.jpg",
                photo_source_url=f"/test/{venue_id}.jpg", photo_rights_status="owned",
                rights_attested_at=start, rights_attested_by_user_id=user_id,
            ))
            db.add(AvailabilitySlot(
                resource_type="hall", resource_id=hall_id, starts_at=start,
                ends_at=start + timedelta(hours=2), status="open",
            ))
        db.commit()
    return owner


def test_page_cursor_crosses_filtered_batch_without_duplicate_or_skip(client, SessionLocal):
    _seed_artists(client, SessionLocal, 75, published=set(range(75)), matching={0, 65, 74})
    cursor = None
    seen = []
    for _ in range(6):
        params = {"kind": "artist", "limit": 1, "format": "SELECTED"}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/catalog/search-page", params=params)
        assert response.status_code == 200, response.text
        page = response.json()
        seen.extend(item["id"] for item in page["items"])
        assert page["venues"] == []
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        assert page["next_cursor"] and page["next_cursor"] != cursor
        cursor = page["next_cursor"]
    assert seen == ["artist-000", "artist-065", "artist-074"]


def test_page_crosses_artist_venue_boundary_after_full_filtered_batch(client, SessionLocal):
    owner = _seed_artists(client, SessionLocal, 64, published=set(range(64)))
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Page boundary venue", "kind": "venue"}, headers=headers,
    ).json()
    venue = client.post(
        "/venues", json={"organization_id": org["id"], "name": "Boundary venue"},
        headers=headers,
    ).json()
    start = now() + timedelta(days=5)
    slot = client.post(
        "/slots", json={"resource_type": "hall", "resource_id": venue["hall_id"],
                        "starts_at": start.isoformat(),
                        "ends_at": (start + timedelta(hours=2)).isoformat()},
        headers=headers,
    )
    assert slot.status_code == 200, slot.text
    publish_venue(client, owner, venue["id"])
    params = {"limit": 1, "format": "not-present"}
    first = client.get("/catalog/search-page", params=params)
    assert first.status_code == 200
    assert first.json()["items"] == []
    assert [item["id"] for item in first.json()["venues"]] == [venue["id"]]
    assert first.json()["has_more"] is False
    assert first.json()["next_cursor"] is None


def test_cursor_is_filter_bound_and_limit_is_validated(client, SessionLocal):
    _seed_artists(client, SessionLocal, 3, published={0, 1, 2})
    first = client.get("/catalog/search-page", params={"limit": 1, "exclude": "z,a"})
    assert first.status_code == 200
    cursor = first.json()["next_cursor"]
    assert cursor
    equivalent = client.get(
        "/catalog/search-page",
        params={"limit": 1, "exclude": "a,z", "cursor": cursor},
    )
    assert equivalent.status_code == 200
    for changed in ({"city": "Казань"}, {"category": "host"}, {"exclude": "a"}):
        response = client.get("/catalog/search-page", params={"cursor": cursor, **changed})
        assert response.status_code == 400
    assert client.get("/catalog/search-page", params={"cursor": "bad!"}).status_code == 400
    assert client.get("/catalog/search-page", params={"limit": 51}).status_code == 422
    assert client.get("/catalog/search-page", params={"limit": 0}).status_code == 422


def test_page_excludes_research_and_unattested_media(client, SessionLocal, engine):
    owner = register(client, "page-venue-owner@booker.test")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Page venues", "kind": "venue"}, headers=headers,
    ).json()
    visible = client.post(
        "/venues", json={"organization_id": org["id"], "name": "Allowed venue"},
        headers=headers,
    ).json()
    research = client.post(
        "/venues", json={"organization_id": org["id"], "name": "Research venue"},
        headers=headers,
    ).json()
    start = now() + timedelta(days=5)
    for venue in (visible, research):
        slot = client.post(
            "/slots", json={"resource_type": "hall", "resource_id": venue["hall_id"],
                            "starts_at": start.isoformat(),
                            "ends_at": (start + timedelta(hours=3)).isoformat()},
            headers=headers,
        )
        assert slot.status_code == 200, slot.text
    publish_venue(client, owner, visible["id"])
    with SessionLocal() as db:
        for index in range(300):
            db.add(Venue(
                id=f"research-{index:03d}", organization_id=org["id"],
                name=f"Research {index}", city="Москва", source_type="automated_import",
                moderation_status="needs_review", publication_enabled=False,
            ))
        db.add(VenuePhoto(
            venue_id=visible["id"], photo_url="/private/unattested.jpg",
            photo_source_url="/private/unattested.jpg", photo_rights_status="unknown",
            sort_order=-10,
        ))
        db.commit()
    statements = 0

    def count_sql(_conn, _cursor, _statement, _parameters, _context, _executemany):
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        response = client.get("/catalog/search-page", params={"kind": "venue"})
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["venues"]] == [visible["id"]]
    assert response.json()["venues"][0]["cover_photo"]["url"] != "/private/unattested.jpg"
    assert research["id"] not in response.text
    assert "/private/unattested.jpg" not in response.text
    assert statements < 30  # 300 unpublished research rows never enter the publication loop.


def test_page_preserves_busy_overlay_per_hall(client, SessionLocal):
    owner = register(client, "page-busy-owner@booker.test")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Busy venue", "kind": "venue"}, headers=headers,
    ).json()
    venue = client.post(
        "/venues", json={"organization_id": org["id"], "name": "Two halls"},
        headers=headers,
    ).json()
    second = client.post(
        f"/venues/{venue['id']}/halls", json={"name": "Second hall", "capacity": 90},
        headers=headers,
    ).json()
    start = now() + timedelta(days=5)
    for hall_id in (venue["hall_id"], second["id"]):
        response = client.post(
            "/slots", json={"resource_type": "hall", "resource_id": hall_id,
                            "starts_at": start.isoformat(),
                            "ends_at": (start + timedelta(hours=4)).isoformat()},
            headers=headers,
        )
        assert response.status_code == 200, response.text
    publish_venue(client, owner, venue["id"])
    with SessionLocal() as db:
        db.add(AvailabilitySlot(
            resource_type="hall", resource_id=venue["hall_id"],
            starts_at=start + timedelta(hours=1), ends_at=start + timedelta(hours=2),
            status="busy",
        ))
        db.commit()
    params = {"kind": "venue", "date": start.isoformat()}
    legacy = client.get("/catalog/search", params=params)
    page = client.get("/catalog/search-page", params=params)
    assert legacy.status_code == page.status_code == 200
    legacy_item = next(item for item in legacy.json()["venues"] if item["id"] == venue["id"])
    page_item = next(item for item in page.json()["venues"] if item["id"] == venue["id"])
    assert page_item == legacy_item
    assert page_item["open_slots"] == 1


def test_artist_batch_checks_match_canonical_for_every_gate(client, SessionLocal):
    _seed_artists(client, SessionLocal, 18, published=set(range(18)))
    with SessionLocal() as db:
        artists = db.query(Artist).order_by(Artist.id).all()
        rows = {int(row.id.rsplit("-", 1)[1]): row for row in artists}
        rows[1].publication_enabled = False
        rows[2].verified = False
        rows[3].verified_status = "pending"
        rows[5].media_url = " "
        rows[6].media_source_url = " "
        rows[7].media_rights_status = "unknown"
        rows[8].media_rights_attested_at = None
        rows[9].media_rights_attested_by_user_id = None
        rows[10].calendar_confirmed_through = now() + timedelta(days=29)
        rows[11].calendar_confirmed_at = None
        rows[12].calendar_confirmed_by_user_id = None
        db.query(ArtistTariff).filter(ArtistTariff.artist_id == rows[4].id).one().honorarium_rub = 0
        db.delete(db.query(ArtistTariff).filter(ArtistTariff.artist_id == rows[15].id).one())
        db.query(AvailabilitySlot).filter(
            AvailabilitySlot.resource_type == "artist", AvailabilitySlot.resource_id == rows[13].id
        ).one().status = "busy"
        old_slot = db.query(AvailabilitySlot).filter(
            AvailabilitySlot.resource_type == "artist", AvailabilitySlot.resource_id == rows[14].id
        ).one()
        old_slot.starts_at = now() - timedelta(days=3)
        old_slot.ends_at = now() - timedelta(days=2)
        db.query(AvailabilitySlot).filter(
            AvailabilitySlot.resource_type == "artist", AvailabilitySlot.resource_id == rows[16].id
        ).one().status = "held"
        rows[17].calendar_confirmed_through = now() + timedelta(days=150)
        db.flush()
        for required in (None, now() + timedelta(days=120)):
            batch = batch_publication_eligibility(db, artists, [], required_through=required)
            for artist in artists:
                canonical = artist_publication_eligibility(db, artist, required_through=required)
                assert batch[("artist", artist.id)] == canonical, artist.id
            assert batch[("artist", rows[0].id)].eligible is (required is None)
            assert batch[("artist", rows[16].id)].checks["calendar_entries"] is True
            assert batch[("artist", rows[17].id)].checks["calendar_30d"] is True
        assert batch[("artist", rows[13].id)].checks["calendar_entries"] is False
        assert batch[("artist", rows[14].id)].checks["calendar_entries"] is False
        org_id = rows[0].organization_id
        db.query(TeamMember).filter(TeamMember.organization_id == org_id).delete()
        db.flush()
        batch = batch_publication_eligibility(db, artists, [])
        assert all(not value.checks["representative"] for value in batch.values())
        for artist in artists:
            assert batch[("artist", artist.id)] == artist_publication_eligibility(db, artist)


def test_venue_batch_checks_match_canonical_for_all_halls_media_and_30d(client, SessionLocal):
    _seed_venues(client, SessionLocal, 15)
    with SessionLocal() as db:
        venues = db.query(Venue).order_by(Venue.id).all()
        rows = {int(row.id.rsplit("-", 1)[1]): row for row in venues}
        rows[1].publication_enabled = False
        rows[2].verified = False
        rows[3].moderation_status = "needs_review"
        rows[4].is_claimed = False
        db.query(VenueTariff).filter(VenueTariff.venue_id == rows[5].id).one().honorarium_rub = 0
        db.query(VenuePhoto).filter(VenuePhoto.venue_id == rows[6].id).one().photo_rights_status = "unknown"
        db.query(VenuePhoto).filter(VenuePhoto.venue_id == rows[7].id).one().rights_attested_at = None
        db.query(VenuePhoto).filter(VenuePhoto.venue_id == rows[8].id).one().rights_attested_by_user_id = None
        db.add(VenueHall(id="second-hall-009", venue_id=rows[9].id, name="Second", capacity=40))
        db.add(VenueHall(id="second-hall-010", venue_id=rows[10].id, name="Second", capacity=40))
        start = now() + timedelta(days=5)
        db.add(AvailabilitySlot(
            resource_type="hall", resource_id="second-hall-010", starts_at=start,
            ends_at=start + timedelta(hours=2), status="held",
        ))
        rows[11].calendar_confirmed_through = now() + timedelta(days=29)
        hall = db.query(VenueHall).filter(VenueHall.venue_id == rows[12].id).one()
        db.delete(hall)
        db.query(AvailabilitySlot).filter(
            AvailabilitySlot.resource_type == "hall", AvailabilitySlot.resource_id == "hall-013"
        ).one().status = "busy"
        rows[14].calendar_confirmed_through = now() + timedelta(days=150)
        db.flush()
        for required in (None, now() + timedelta(days=120)):
            batch = batch_publication_eligibility(db, [], venues, required_through=required)
            for venue in venues:
                canonical = venue_publication_eligibility(db, venue, required_through=required)
                assert batch[("venue", venue.id)] == canonical, venue.id
            assert batch[("venue", rows[0].id)].eligible is (required is None)
            assert batch[("venue", rows[9].id)].checks["calendar_entries"] is False
            assert batch[("venue", rows[10].id)].checks["calendar_entries"] is True
            assert batch[("venue", rows[14].id)].checks["calendar_30d"] is True
        assert batch[("venue", rows[12].id)].checks["halls"] is False
        assert batch[("venue", rows[13].id)].checks["calendar_entries"] is False


def test_page_uses_required_through_for_distant_search_date(client, SessionLocal):
    _seed_artists(client, SessionLocal, 1, published={0})
    distant = (now() + timedelta(days=120)).isoformat()
    params = {"kind": "artist", "date": distant}
    legacy = client.get("/catalog/search", params=params)
    page = client.get("/catalog/search-page", params=params)
    assert legacy.status_code == page.status_code == 200
    assert legacy.json()["items"] == page.json()["items"] == []


def test_page_batches_card_data_but_retains_canonical_gate(client, SessionLocal, engine):
    _seed_artists(client, SessionLocal, 24, published=set(range(24)))
    counts = []

    def count_sql(_conn, _cursor, _statement, _parameters, _context, _executemany):
        counts[-1] += 1

    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        observations = []
        for path in ("/catalog/search", "/catalog/search-page"):
            counts.append(0)
            started = perf_counter()
            response = client.get(path, params={"kind": "artist"})
            observations.append((counts[-1], (perf_counter() - started) * 1000))
            assert response.status_code == 200, response.text
            assert len(response.json()["items"]) == 24
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)
    assert observations[1][0] < observations[0][0]
    assert observations[1][0] <= 25
    print(f"P07 isolated SQLite legacy/page SQL+HTTP-ms: {observations}")


def test_page_venue_query_count_is_bounded_for_24_published(client, SessionLocal, engine):
    _seed_venues(client, SessionLocal, 24)
    statements = 0

    def count_sql(_conn, _cursor, _statement, _parameters, _context, _executemany):
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        started = perf_counter()
        response = client.get("/catalog/search-page", params={"kind": "venue", "limit": 24})
        elapsed_ms = (perf_counter() - started) * 1000
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)
    assert response.status_code == 200, response.text
    assert len(response.json()["venues"]) == 24
    assert statements <= 25
    print(f"P07 isolated SQLite 24 venues: SQL={statements}, HTTP-ms={elapsed_ms:.2f}")
