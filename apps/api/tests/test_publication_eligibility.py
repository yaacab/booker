from datetime import timedelta

from booker_api.security import now
from tests.conftest import auth_header, publish_artist, publish_venue, register


def test_artist_publication_requires_evidence_and_closes_public_bypasses(client, SessionLocal):
    owner = register(client, "publication-owner@booker.test", "Владелец")
    manager = register(client, "publication-manager@booker.test", "Менеджер")
    platform_admin = register(client, "publication-platform@booker.test", "Администратор")
    customer = register(client, "publication-customer@booker.test", "Заказчик")
    owner_headers = auth_header(owner["token"])
    org = client.post(
        "/orgs",
        json={"name": "Проверяемый артист", "kind": "artist"},
        headers=owner_headers,
    ).json()
    client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": manager["user_id"], "role": "manager"},
        headers=owner_headers,
    )
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ Evidence", "category": "dj"},
        headers=owner_headers,
    ).json()

    assert client.get(f"/artists/{artist['id']}").status_code == 404
    assert client.get(f"/artists/{artist['id']}", headers=owner_headers).status_code == 200

    with SessionLocal() as db:
        from booker_api.models import Artist, User

        row = db.get(Artist, artist["id"])
        row.verified = True
        row.verified_status = "approved"
        admin_row = db.get(User, platform_admin["user_id"])
        admin_row.email_verified_at = now()
        admin_row.is_platform_admin = True
        db.commit()

    starts = (now() + timedelta(days=45)).replace(microsecond=0)
    assert client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
        },
        headers=owner_headers,
    ).status_code == 200
    assert client.post(
        f"/artists/{artist['id']}/tariffs",
        json={"title": "Сет", "honorarium_rub": 100000, "hours": 2},
        headers=owner_headers,
    ).status_code == 200

    blocked = client.put(
        f"/artists/{artist['id']}/publication",
        json={"enabled": True, "state_version": 0},
        headers=owner_headers,
    )
    assert blocked.status_code == 409
    assert {"media", "calendar_30d"} <= set(blocked.json()["detail"]["reason_codes"])

    evidence = {
        "media_url": "/design/puzzle-dj.png",
        "media_source_url": "/design/puzzle-dj.png",
        "media_rights_status": "owned",
        "rights_attested": True,
        "calendar_confirmed_through": (now() + timedelta(days=90)).isoformat(),
    }
    assert client.put(
        f"/artists/{artist['id']}/publication-evidence",
        json=evidence,
        headers=auth_header(manager["token"]),
    ).status_code == 403
    assert client.put(
        f"/artists/{artist['id']}/publication-evidence",
        json=evidence,
        headers=auth_header(platform_admin["token"]),
    ).status_code == 403
    assert client.put(
        f"/artists/{artist['id']}/publication-evidence",
        json=evidence,
        headers=auth_header(customer["token"]),
    ).status_code == 403
    assert client.put(
        f"/artists/{artist['id']}/publication",
        json={"enabled": True, "state_version": 0},
        headers=auth_header(customer["token"]),
    ).status_code == 403
    assert client.put(
        f"/artists/{artist['id']}/publication-evidence",
        json=evidence,
        headers=owner_headers,
    ).status_code == 200

    enabled = client.put(
        f"/artists/{artist['id']}/publication",
        json={"enabled": True, "state_version": 0},
        headers=owner_headers,
    )
    assert enabled.status_code == 200
    assert enabled.json()["state_version"] == 1
    assert client.get(f"/artists/{artist['id']}").status_code == 200
    assert client.get(f"/catalog/public-status/artist/{artist['id']}").status_code == 204

    far_search = client.get(
        "/catalog/search",
        params={"city": "Москва", "category": "dj", "date": (now() + timedelta(days=120)).isoformat()},
    ).json()
    assert all(item["id"] != artist["id"] for item in far_search["items"])

    stale = client.put(
        f"/artists/{artist['id']}/publication",
        json={"enabled": False, "state_version": 0},
        headers=owner_headers,
    )
    assert stale.status_code == 409
    disabled = client.put(
        f"/artists/{artist['id']}/publication",
        json={"enabled": False, "state_version": 1},
        headers=owner_headers,
    )
    assert disabled.status_code == 200
    assert client.get(f"/artists/{artist['id']}").status_code == 404
    assert client.get(f"/catalog/public-status/artist/{artist['id']}").status_code == 404

    customer_headers = auth_header(customer["token"])
    customer_org = client.post(
        "/orgs",
        json={"name": "Заказчик публикации", "kind": "customer"},
        headers=customer_headers,
    ).json()
    favorite = client.post(
        "/favorites",
        json={
            "target_type": "artist",
            "target_id": artist["id"],
            "organization_id": customer_org["id"],
        },
        headers=customer_headers,
    )
    assert favorite.status_code == 404
    event = client.post(
        "/events",
        json={"organization_id": customer_org["id"], "title": "Скрытая заявка", "event_date": starts.isoformat()},
        headers=customer_headers,
    ).json()
    request = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=customer_headers,
    )
    assert request.status_code == 404


def test_new_venue_hall_revokes_calendar_confirmation_and_publication(client):
    owner = register(client, "publication-venue@booker.test", "Площадка")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Venue Publication", "kind": "venue"}, headers=headers
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Venue Evidence", "capacity": 120},
        headers=headers,
    ).json()
    starts = (now() + timedelta(days=45)).replace(microsecond=0)
    assert client.post(
        "/slots",
        json={
            "resource_type": "hall",
            "resource_id": venue["hall_id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=5)).isoformat(),
        },
        headers=headers,
    ).status_code == 200


    publish_venue(client, owner, venue["id"])
    assert client.get(f"/venues/{venue['id']}").status_code == 200
    assert client.get(f"/catalog/public-status/venue/{venue['id']}").status_code == 204

    added = client.post(
        f"/venues/{venue['id']}/halls",
        json={"name": "Новый зал", "capacity": 40},
        headers=headers,
    )
    assert added.status_code == 200
    assert client.get(f"/venues/{venue['id']}").status_code == 404
    assert client.get(f"/catalog/public-status/venue/{venue['id']}").status_code == 404
    preview = client.get(f"/venues/{venue['id']}", headers=headers)
    assert preview.status_code == 200
    renewed = client.put(
        f"/venues/{venue['id']}/publication-evidence",
        json={"calendar_confirmed_through": (now() + timedelta(days=90)).isoformat()},
        headers=headers,
    )
    assert renewed.status_code == 200
    blocked = client.put(
        f"/venues/{venue['id']}/publication",
        json={"enabled": True, "state_version": 2},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert "calendar_entries" in blocked.json()["detail"]["reason_codes"]
    assert client.get(f"/venues/{venue['id']}").status_code == 404
    new_hall = added.json()["id"]
    assert client.post(
        "/slots",
        json={
            "resource_type": "hall", "resource_id": new_hall,
            "starts_at": (starts + timedelta(days=1)).isoformat(),
            "ends_at": (starts + timedelta(days=1, hours=5)).isoformat(),
        },
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"/venues/{venue['id']}/publication",
        json={"enabled": True, "state_version": 2},
        headers=headers,
    ).status_code == 200



def test_venue_publication_evidence_requires_real_representative(client):
    owner = register(client, "venue-evidence-owner@booker.test", "Owner")
    manager = register(client, "venue-evidence-manager@booker.test", "Manager")
    outsider = register(client, "venue-evidence-outsider@booker.test", "Outsider")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Private Venue", "kind": "venue"}, headers=headers
    ).json()
    assert client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": manager["user_id"], "role": "manager"},
        headers=headers,
    ).status_code == 200
    venue = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Private Hall"},
        headers=headers,
    ).json()
    paths_and_bodies = (
        (f"/venues/{venue['id']}/publication-evidence", {
            "calendar_confirmed_through": (now() + timedelta(days=90)).isoformat(),
        }),
        (f"/venues/{venue['id']}/photos", {
            "photo_url": "/design/puzzle-venue.png",
            "photo_source_url": "/design/puzzle-venue.png",
            "photo_rights_status": "owned", "rights_attested": True,
        }),
        (f"/venues/{venue['id']}/publication", {
            "enabled": True, "state_version": 0,
        }),
    )
    for actor in (manager, outsider):
        for path, body in paths_and_bodies:
            assert client.put(
                path, json=body, headers=auth_header(actor["token"])
            ).status_code == 403
    assert client.get(f"/venues/{venue['id']}").status_code == 404


def test_busy_only_calendar_cannot_publish_artist(client, SessionLocal):
    owner = register(client, "publication-busy@booker.test", "Busy Artist")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Busy Artist", "kind": "artist"}, headers=headers
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "Busy DJ", "category": "dj"},
        headers=headers,
    ).json()
    with SessionLocal() as db:
        from booker_api.models import Artist

        row = db.get(Artist, artist["id"])
        row.verified = True
        row.verified_status = "approved"
        db.commit()
    starts = (now() + timedelta(days=40)).replace(microsecond=0)
    assert client.post(
        "/calendar/vacation",
        json={
            "organization_id": org["id"], "resource_type": "artist",
            "resource_id": artist["id"], "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    ).status_code == 200
    assert client.post(
        f"/artists/{artist['id']}/tariffs",
        json={"title": "Сет", "honorarium_rub": 100000, "hours": 2},
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"/artists/{artist['id']}/publication-evidence",
        json={
            "media_url": "/design/puzzle-dj.png",
            "media_source_url": "/design/puzzle-dj.png",
            "media_rights_status": "owned", "rights_attested": True,
            "calendar_confirmed_through": (now() + timedelta(days=90)).isoformat(),
        },
        headers=headers,
    ).status_code == 200
    blocked = client.put(
        f"/artists/{artist['id']}/publication",
        json={"enabled": True, "state_version": 0},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert "calendar_entries" in blocked.json()["detail"]["reason_codes"]
    assert client.get(f"/artists/{artist['id']}").status_code == 404


def test_public_index_is_paginated_and_contains_only_eligible_profiles(client):
    owner = register(client, "public-index@booker.test", "Публичный индекс")
    headers = auth_header(owner["token"])
    org = client.post(
        "/orgs", json={"name": "Public Index Artists", "kind": "artist"}, headers=headers
    ).json()
    artists = [
        client.post(
            "/artists",
            json={"organization_id": org["id"], "name": name, "category": "dj"},
            headers=headers,
        ).json()
        for name in ("Index Alpha", "Index Beta", "Index Hidden")
    ]
    starts = (now() + timedelta(days=45)).replace(microsecond=0)
    for artist in artists[:2]:
        slot = client.post(
            "/slots",
            json={
                "resource_type": "artist",
                "resource_id": artist["id"],
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=3)).isoformat(),
            },
            headers=headers,
        )
        assert slot.status_code == 200, slot.text
        publish_artist(client, owner, artist["id"])

    first = client.get("/catalog/public-index", params={"limit": 1})
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 1
    assert first_body["next_cursor"]

    second = client.get(
        "/catalog/public-index",
        params={"limit": 1, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None

    indexed_ids = {first_body["items"][0]["id"], second_body["items"][0]["id"]}
    assert indexed_ids == {artists[0]["id"], artists[1]["id"]}
    assert artists[2]["id"] not in indexed_ids
    assert client.get("/catalog/public-index", params={"cursor": "broken"}).status_code == 400
