"""Draft supply data must not become visible through public catalog reads."""

import json
from datetime import timedelta

import pytest

from booker_api.models import Artist, AvailabilitySlot, Venue, VenuePhoto, VenueTariff
from booker_api.security import now
from booker_api.venue_catalog import record_photos
from tests.conftest import auth_header, publish_artist, publish_venue, register
from tests.test_admin import _promote_admin
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers


@pytest.fixture()
def draft_supply(client, SessionLocal):
    owner = register(client, "privacy-owner@booker.test")
    outsider = register(client, "privacy-outsider@booker.test")
    owner_headers = auth_header(owner["token"])
    artist_org = client.post(
        "/orgs", json={"name": "Private artist", "kind": "artist"}, headers=owner_headers
    )
    venue_org = client.post(
        "/orgs", json={"name": "Private venue", "kind": "venue"}, headers=owner_headers
    )
    assert artist_org.status_code == venue_org.status_code == 200
    artist = client.post(
        "/artists",
        json={
            "organization_id": artist_org.json()["id"],
            "name": "DRAFT_ARTIST_PRIVATE",
            "category": "dj",
            "media_url": "/private/artist-photo.jpg",
            "rider_json": json.dumps({"internal_note": "ARTIST_PRIVATE_RIDER"}),
        },
        headers=owner_headers,
    )
    venue = client.post(
        "/venues",
        json={
            "organization_id": venue_org.json()["id"],
            "name": "DRAFT_VENUE_PRIVATE",
            "capacity": 100,
        },
        headers=owner_headers,
    )
    assert artist.status_code == venue.status_code == 200
    artist_id = artist.json()["id"]
    venue_id = venue.json()["id"]
    hall_id = venue.json()["hall_id"]
    # A research import that lacks the explicit demo verification flag is also private.
    imported = client.post(
        "/venues",
        json={
            "organization_id": venue_org.json()["id"],
            "name": "UNREVIEWED_IMPORT_PRIVATE",
            "capacity": 80,
        },
        headers=owner_headers,
    )
    assert imported.status_code == 200
    imported_id = imported.json()["id"]
    with SessionLocal() as db:
        db.get(Artist, artist_id).rider_json = json.dumps({"internal_note": "ARTIST_PRIVATE_RIDER"})
        owner_venue = db.get(Venue, venue_id)
        owner_venue.details_json = json.dumps({"internal_note": "VENUE_PRIVATE_DETAILS"})
        owner_venue.description = "VENUE_PRIVATE_DESCRIPTION"
        unreviewed = db.get(Venue, imported_id)
        unreviewed.source_type = "automated_import"
        unreviewed.details_json = json.dumps({"research_status": "needs_review"})
        db.add(VenueTariff(venue_id=imported_id, title="Research", honorarium_rub=10000))
        db.add(
            VenuePhoto(
                venue_id=imported_id,
                photo_url="/private/import.jpg",
                photo_source_url="/private/import.jpg",
                photo_rights_status="unknown",
            )
        )
        db.commit()
    return {
        "artist_id": artist_id,
        "venue_id": venue_id,
        "hall_id": hall_id,
        "imported_id": imported_id,
        "owner_headers": owner_headers,
        "outsider_headers": auth_header(outsider["token"]),
    }


@pytest.mark.parametrize("actor", ("guest", "outsider"))
@pytest.mark.parametrize(
    ("resource", "path", "expected_status"),
    (
        ("artist", "/artists/{artist_id}", 404),
        ("venue", "/venues/{venue_id}", 404),
        ("venue_halls", "/venues/{venue_id}/halls", None),
        ("venue_reviews", "/venues/{venue_id}/reviews", 404),
    ),
)
def test_draft_detail_and_children_hidden_from_guest_and_outsider(
    client, draft_supply, actor, resource, path, expected_status
):
    headers = draft_supply["outsider_headers"] if actor == "outsider" else {}
    response = client.get(path.format(**draft_supply), headers=headers)
    if resource == "venue_halls":
        assert response.status_code == (403 if actor == "outsider" else 401)
    else:
        assert response.status_code == expected_status, response.text
    assert draft_supply["artist_id"] not in response.text
    assert draft_supply["venue_id"] not in response.text
    assert draft_supply["hall_id"] not in response.text


def test_draft_stays_visible_to_owner_only(client, draft_supply):
    headers = draft_supply["owner_headers"]
    artist = client.get(f"/artists/{draft_supply['artist_id']}", headers=headers)
    venue = client.get(f"/venues/{draft_supply['venue_id']}", headers=headers)
    halls = client.get(f"/venues/{draft_supply['venue_id']}/halls", headers=headers)
    assert artist.status_code == venue.status_code == halls.status_code == 200
    assert artist.json()["id"] == draft_supply["artist_id"]
    assert venue.json()["id"] == draft_supply["venue_id"]
    assert halls.json()["items"][0]["id"] == draft_supply["hall_id"]
    admin = _promote_admin(client, "draft-preview-admin@booker.test", totp=TEST_TOTP_SECRET)
    assert client.get(
        f"/venues/{draft_supply['venue_id']}", headers=auth_header(admin["pre_promotion_token"])
    ).status_code == 404
    assert client.get(
        f"/venues/{draft_supply['venue_id']}", headers=admin_totp_headers(admin["token"])
    ).status_code == 200


@pytest.mark.parametrize("actor", ("guest", "outsider"))
def test_draft_excluded_from_search_public_index_and_demo(client, draft_supply, actor):
    headers = draft_supply["outsider_headers"] if actor == "outsider" else {}
    search = client.get("/catalog/search", headers=headers)
    index = client.get("/catalog/public-index", headers=headers)
    demo = client.get("/catalog/demo/venues", headers=headers)
    assert search.status_code == index.status_code == 200
    assert demo.status_code == (403 if actor == "outsider" else 401)
    responses = (search, index)
    for response in responses:
        for private_value in (
            draft_supply["artist_id"],
            draft_supply["venue_id"],
            draft_supply["imported_id"],
            "ARTIST_PRIVATE_RIDER",
            "VENUE_PRIVATE_DETAILS",
            "UNREVIEWED_IMPORT_PRIVATE",
        ):
            assert private_value not in response.text


def test_public_profile_hides_busy_slots_and_unattested_photo(client, SessionLocal):
    owner = register(client, "public-safe-owner@booker.test")
    outsider = register(client, "public-safe-outsider@booker.test")
    headers = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Safe Venue", "kind": "venue"}, headers=headers).json()
    venue = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Safe Hall", "capacity": 100},
        headers=headers,
    ).json()
    starts = (now() + timedelta(days=45)).replace(microsecond=0)
    open_slot = client.post(
        "/slots",
        json={
            "resource_type": "hall",
            "resource_id": venue["hall_id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
        },
        headers=headers,
    )
    assert open_slot.status_code == 200, open_slot.text
    publish_venue(client, owner, venue["id"])
    with SessionLocal() as db:
        db.get(Venue, venue["id"]).details_json = json.dumps({
            "event_contact": "PRIVATE_RESEARCH_CONTACT",
            "research_status": "internal_review",
        })
        db.add(AvailabilitySlot(
            resource_type="hall", resource_id=venue["hall_id"],
            starts_at=starts + timedelta(hours=1),
            ends_at=starts + timedelta(hours=2),
            status="busy", external_uid="ical:private-overlay",
        ))
        db.add(AvailabilitySlot(
            resource_type="hall", resource_id=venue["hall_id"],
            starts_at=starts + timedelta(days=4),
            ends_at=starts + timedelta(days=4, hours=4),
            status="open",
        ))
        for day, state in ((46, "busy"), (47, "held"), (48, "confirmed")):
            db.add(AvailabilitySlot(
                resource_type="hall",
                resource_id=venue["hall_id"],
                starts_at=starts + timedelta(days=day - 45),
                ends_at=starts + timedelta(days=day - 45, hours=4),
                status=state,
            ))
        db.add(VenuePhoto(
            venue_id=venue["id"],
            photo_url="/private/not-attested.jpg",
            photo_source_url="/private/not-attested.jpg",
            photo_rights_status="licensed",
            sort_order=-1,
        ))
        db.commit()

    for actor_headers in ({}, auth_header(outsider["token"])):
        response = client.get(f"/venues/{venue['id']}", headers=actor_headers)
        assert response.status_code == 200
        data = response.json()
        assert [slot["status"] for slot in data["slots"]] == ["open"]
        assert open_slot.json()["id"] not in {slot["id"] for slot in data["slots"]}
        assert "/private/not-attested.jpg" not in response.text
        assert "PRIVATE_RESEARCH_CONTACT" not in response.text
        search = client.get(
            "/catalog/search",
            params={"kind": "venue", "date": (starts + timedelta(days=4)).isoformat()},
            headers=actor_headers,
        )
        assert search.status_code == 200
        assert any(item["id"] == venue["id"] for item in search.json()["venues"])
        assert "/private/not-attested.jpg" not in search.text

    owner_view = client.get(f"/venues/{venue['id']}", headers=headers)
    assert {slot["status"] for slot in owner_view.json()["slots"]} == {
        "open", "busy", "held", "confirmed",
    }
    assert "/private/not-attested.jpg" in owner_view.text
    assert owner_view.json()["details"]["event_contact"] == "PRIVATE_RESEARCH_CONTACT"

    admin = _promote_admin(client, "public-safe-admin@booker.test", totp=TEST_TOTP_SECRET)
    admin_without_step_up = client.get(
        f"/venues/{venue['id']}", headers=auth_header(admin["pre_promotion_token"])
    )
    assert admin_without_step_up.status_code == 200
    assert [slot["status"] for slot in admin_without_step_up.json()["slots"]] == ["open"]
    assert "PRIVATE_RESEARCH_CONTACT" not in admin_without_step_up.text
    admin_with_step_up = client.get(
        f"/venues/{venue['id']}", headers=admin_totp_headers(admin["token"])
    )
    assert admin_with_step_up.status_code == 200
    assert "PRIVATE_RESEARCH_CONTACT" in admin_with_step_up.text
    assert "busy" in {slot["status"] for slot in admin_with_step_up.json()["slots"]}

    with SessionLocal() as db:
        row = db.get(Venue, venue["id"])
        existing_photo = db.query(VenuePhoto).filter_by(
            venue_id=venue["id"], photo_url="/design/puzzle-venue.png"
        ).one()
        assert existing_photo.rights_attested_at is not None, (
            existing_photo.photo_source_url, existing_photo.photo_rights_status
        )
        record_photos(db, row, {"photos": [{
            "photo_url": "/design/puzzle-venue.png",
            "photo_source_url": "/design/puzzle-venue.png",
            "photo_rights_status": "owned",
        }]})
        db.commit()
        photo = db.query(VenuePhoto).filter_by(
            venue_id=venue["id"], photo_url="/design/puzzle-venue.png"
        ).one()
        assert photo.rights_attested_at is not None, (
            photo.photo_source_url, photo.photo_rights_status
        )
    assert client.get(f"/venues/{venue['id']}").status_code == 200
    with SessionLocal() as db:
        row = db.get(Venue, venue["id"])
        record_photos(db, row, {"photos": [{
            "photo_url": "/design/puzzle-venue.png",
            "photo_source_url": "/new-source/venue-photo",
            "photo_rights_status": "owned",
        }]})
        db.commit()
        photo = db.query(VenuePhoto).filter_by(
            venue_id=venue["id"], photo_url="/design/puzzle-venue.png"
        ).one()
        assert photo.rights_attested_at is None
        assert photo.rights_attested_by_user_id is None
    assert client.get(f"/venues/{venue['id']}").status_code == 404
    assert client.get(f"/venues/{venue['id']}", headers=headers).status_code == 200
    reattested = client.put(
        f"/venues/{venue['id']}/photos",
        json={
            "photo_url": "/design/puzzle-venue.png",
            "photo_source_url": "/new-source/venue-photo",
            "photo_rights_status": "owned",
            "rights_attested": True,
            "sort_order": 0,
        },
        headers=headers,
    )
    assert reattested.status_code == 200
    assert client.get(f"/venues/{venue['id']}").status_code == 200
    with SessionLocal() as db:
        row = db.get(Venue, venue["id"])
        record_photos(db, row, {"photos": [{
            "photo_url": "/design/puzzle-venue.png",
            "photo_source_url": "/new-source/venue-photo",
            "photo_rights_status": "licensed",
        }]})
        db.commit()
        photo = db.query(VenuePhoto).filter_by(
            venue_id=venue["id"], photo_url="/design/puzzle-venue.png"
        ).one()
        assert photo.rights_attested_at is None
        assert photo.rights_attested_by_user_id is None
    assert client.get(f"/venues/{venue['id']}").status_code == 404


def test_venue_search_applies_busy_overlay_per_hall(client, SessionLocal):
    owner = register(client, "two-hall-search@booker.test")
    headers = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Two Hall Venue", "kind": "venue"}, headers=headers).json()
    venue = client.post(
        "/venues", json={"organization_id": org["id"], "name": "Independent Halls"},
        headers=headers,
    ).json()
    second = client.post(
        f"/venues/{venue['id']}/halls", json={"name": "Second Hall", "capacity": 90},
        headers=headers,
    )
    assert second.status_code == 200
    starts = (now() + timedelta(days=5)).replace(microsecond=0)
    for hall_id in (venue["hall_id"], second.json()["id"]):
        opened = client.post(
            "/slots",
            json={
                "resource_type": "hall", "resource_id": hall_id,
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=4)).isoformat(),
            },
            headers=headers,
        )
        assert opened.status_code == 200
    publish_venue(client, owner, venue["id"])
    with SessionLocal() as db:
        db.add(AvailabilitySlot(
            resource_type="hall", resource_id=venue["hall_id"],
            starts_at=starts + timedelta(hours=1),
            ends_at=starts + timedelta(hours=2),
            status="busy",
        ))
        db.commit()
    response = client.get(
        "/catalog/search", params={"kind": "venue", "date": starts.isoformat()}
    )
    assert response.status_code == 200
    item = next(row for row in response.json()["venues"] if row["id"] == venue["id"])
    assert item["open_slots"] == 1
    undated = client.get("/catalog/search", params={"kind": "venue"})
    assert undated.status_code == 200
    undated_item = next(row for row in undated.json()["venues"] if row["id"] == venue["id"])
    assert undated_item["open_slots"] == 1
    public = client.get(f"/venues/{venue['id']}")
    assert public.status_code == 200
    assert [slot["hall"] for slot in public.json()["slots"]] == ["Second Hall"]


def test_artist_public_profile_hides_busy_slots(client, SessionLocal):
    owner = register(client, "public-safe-artist@booker.test")
    headers = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Safe Artist", "kind": "artist"}, headers=headers).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "Safe DJ", "category": "dj"},
        headers=headers,
    ).json()
    starts = (now() + timedelta(days=45)).replace(microsecond=0)
    opened = client.post(
        "/slots",
        json={
            "resource_type": "artist", "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
        },
        headers=headers,
    )
    assert opened.status_code == 200
    publish_artist(client, owner, artist["id"])
    with SessionLocal() as db:
        db.add(AvailabilitySlot(
            resource_type="artist", resource_id=artist["id"],
            starts_at=starts + timedelta(hours=1),
            ends_at=starts + timedelta(hours=2),
            status="busy", external_uid="ical:private-artist-overlay",
        ))
        db.add(AvailabilitySlot(
            resource_type="artist", resource_id=artist["id"],
            starts_at=starts + timedelta(days=2),
            ends_at=starts + timedelta(days=2, hours=4),
            status="open",
        ))
        db.add(AvailabilitySlot(
            resource_type="artist", resource_id=artist["id"],
            starts_at=starts + timedelta(days=1),
            ends_at=starts + timedelta(days=1, hours=4),
            status="busy", external_uid="ical:private-artist-event",
        ))
        db.commit()
    public = client.get(f"/artists/{artist['id']}")
    assert public.status_code == 200
    assert [slot["status"] for slot in public.json()["slots"]] == ["open"]
    assert opened.json()["id"] not in {slot["id"] for slot in public.json()["slots"]}
    assert "private-artist-event" not in public.text
    private = client.get(f"/artists/{artist['id']}", headers=headers)
    assert {slot["status"] for slot in private.json()["slots"]} == {"open", "busy"}


@pytest.mark.parametrize("actor", ("guest", "outsider"))
@pytest.mark.parametrize("resource", ("artist", "venue"))
def test_draft_public_status_is_not_found(client, draft_supply, actor, resource):
    headers = draft_supply["outsider_headers"] if actor == "outsider" else {}
    resource_id = draft_supply[f"{resource}_id"]
    response = client.get(f"/catalog/public-status/{resource}/{resource_id}", headers=headers)
    assert response.status_code == 404
    assert resource_id not in response.text


def test_compare_rejects_draft_venues_without_leaking_columns(client, draft_supply):
    response = client.get(
        "/compare",
        params={
            "target_type": "venue",
            "ids": f"{draft_supply['venue_id']},{draft_supply['imported_id']}",
        },
    )
    assert response.status_code == 404
    assert "columns" not in response.text
    assert "UNREVIEWED_IMPORT_PRIVATE" not in response.text
