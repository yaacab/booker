"""Negative object authorization checks for supply catalog mutations."""

from datetime import datetime, timedelta, timezone

import pytest

from booker_api.models import (
    Artist,
    ArtistTariff,
    AuditLog,
    AvailabilitySlot,
    Service,
    Venue,
    VenueHall,
    VenuePhoto,
    VenueTariff,
)
from tests.conftest import auth_header, register

TABLES = (
    Artist,
    Venue,
    VenueHall,
    VenuePhoto,
    ArtistTariff,
    VenueTariff,
    AvailabilitySlot,
    Service,
    AuditLog,
)


def _snapshot(SessionLocal):
    with SessionLocal() as db:
        return {
            table.__tablename__: tuple(
                sorted(
                    tuple(getattr(row, column.name) for column in table.__table__.columns)
                    for row in db.query(table).all()
                )
            )
            for table in TABLES
        }


@pytest.fixture()
def supply(client):
    owner = register(client, "supply-authz-owner@booker.test")
    viewer = register(client, "supply-authz-viewer@booker.test")
    outsider = register(client, "supply-authz-outsider@booker.test")
    owner_h = auth_header(owner["token"])

    artist_org_response = client.post(
        "/orgs", json={"name": "Artist supply", "kind": "artist"}, headers=owner_h
    )
    assert artist_org_response.status_code == 200, artist_org_response.text
    artist_org = artist_org_response.json()["id"]
    venue_org_response = client.post(
        "/orgs", json={"name": "Venue supply", "kind": "venue"}, headers=owner_h
    )
    assert venue_org_response.status_code == 200, venue_org_response.text
    venue_org = venue_org_response.json()["id"]
    foreign_org_response = client.post(
        "/orgs",
        json={"name": "Foreign supply", "kind": "artist"},
        headers=auth_header(outsider["token"]),
    )
    assert foreign_org_response.status_code == 200, foreign_org_response.text
    for org_id in (artist_org, venue_org):
        added = client.post(
            f"/orgs/{org_id}/members",
            json={"user_id": viewer["user_id"], "role": "viewer"},
            headers=owner_h,
        )
        assert added.status_code == 200, added.text
    artist_response = client.post(
        "/artists",
        json={"organization_id": artist_org, "name": "Test DJ", "category": "dj"},
        headers=owner_h,
    )
    assert artist_response.status_code == 200, artist_response.text
    venue_response = client.post(
        "/venues",
        json={"organization_id": venue_org, "name": "Test hall", "capacity": 100},
        headers=owner_h,
    )
    assert venue_response.status_code == 200, venue_response.text
    return {
        "artist_id": artist_response.json()["id"],
        "venue_id": venue_response.json()["id"],
        "hall_id": venue_response.json()["hall_id"],
        "artist_org": artist_org,
        "venue_org": venue_org,
        "viewer": viewer,
        "outsider": outsider,
    }


ROUTES = (
    "artist_evidence",
    "venue_evidence",
    "venue_photos",
    "venue_halls",
    "artist_tariffs",
    "venue_tariffs",
    "artist_slot",
    "hall_slot",
    "service_template_artist",
    "service_template_venue",
)


def _request(client, supply, route, headers):
    artist_id = supply["artist_id"]
    venue_id = supply["venue_id"]
    future = datetime.now(timezone.utc) + timedelta(days=60)
    evidence_date = (future + timedelta(days=30)).isoformat()
    if route == "artist_evidence":
        return client.patch(
            f"/artists/{artist_id}/publication-evidence",
            json={
                "media_url": "/media/authz-test.jpg",
                "media_source_url": "/media/authz-test.jpg",
                "media_rights_status": "owned",
                "rights_attested": True,
                "calendar_confirmed_through": evidence_date,
            },
            headers=headers,
        )
    if route == "venue_evidence":
        return client.patch(
            f"/venues/{venue_id}/publication-evidence",
            json={"calendar_confirmed_through": evidence_date},
            headers=headers,
        )
    if route == "venue_photos":
        return client.post(
            f"/venues/{venue_id}/photos",
            json={
                "photo_url": "/media/authz-test.jpg",
                "photo_source_url": "/media/authz-test.jpg",
                "photo_rights_status": "owned",
                "rights_attested": True,
            },
            headers=headers,
        )
    if route == "venue_halls":
        return client.post(
            f"/venues/{venue_id}/halls",
            json={"name": "Foreign hall", "capacity": 50},
            headers=headers,
        )
    if route in {"artist_tariffs", "venue_tariffs"}:
        kind = "artists" if route == "artist_tariffs" else "venues"
        resource_id = artist_id if route == "artist_tariffs" else venue_id
        return client.post(
            f"/{kind}/{resource_id}/tariffs",
            json={"title": "Foreign tariff", "honorarium_rub": 50000, "hours": 2},
            headers=headers,
        )
    if route in {"artist_slot", "hall_slot"}:
        return client.post(
            "/slots",
            json={
                "resource_type": "artist" if route == "artist_slot" else "hall",
                "resource_id": artist_id if route == "artist_slot" else supply["hall_id"],
                "starts_at": future.isoformat(),
                "ends_at": (future + timedelta(hours=2)).isoformat(),
            },
            headers=headers,
        )
    if route in {"service_template_artist", "service_template_venue"}:
        org_id = supply["artist_org"] if route.endswith("artist") else supply["venue_org"]
        return client.post(
            "/services/from-template",
            json={"organization_id": org_id, "template_id": "dj-standard"},
            headers=headers,
        )
    raise AssertionError(route)


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("actor", ("viewer", "outsider"))
def test_supply_mutation_denies_viewer_and_cross_tenant_owner_without_writes(
    client, SessionLocal, supply, route, actor
):
    before = _snapshot(SessionLocal)
    response = _request(client, supply, route, auth_header(supply[actor]["token"]))
    assert response.status_code == 403, (route, actor, response.text)
    assert _snapshot(SessionLocal) == before, (route, actor)
