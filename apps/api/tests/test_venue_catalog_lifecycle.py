from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, register


def _admin(client) -> dict:
    user = register(client, "venue-catalog-admin@booker.test", "Catalog Admin")
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import User

        row = db.get(User, user["user_id"])
        row.is_platform_admin = True
        db.commit()
    finally:
        db.close()
    return user


def _open_data_venue(client) -> dict:
    owner = register(client, "venue-catalog-owner@booker.test", "Venue Owner")
    org = client.post(
        "/orgs",
        json={"name": "Тестовая площадка", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={
            "organization_id": org["id"],
            "name": "Площадка из открытых данных",
            "city": "Москва",
            "capacity": 120,
        },
        headers=auth_header(owner["token"]),
    ).json()
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import Venue

        row = db.get(Venue, venue["id"])
        row.address = "Москва, Тестовая улица, 1"
        row.listing_origin = "open_data"
        row.source_type = "automated_import"
        row.partnership_status = "unverified_listing"
        row.is_claimed = False
        row.moderation_status = "published"
        row.completeness_score = 70
        row.last_crawled_at = datetime.now(timezone.utc)
        row.data_freshness_status = "fresh"
        db.commit()
    finally:
        db.close()
    return venue


def test_admin_status_change_preserves_origin_and_updates_public_disclosure(client):
    venue = _open_data_venue(client)
    admin = _admin(client)

    before = client.get(f"/venues/{venue['id']}")
    assert before.status_code == 200
    assert before.json()["public_disclosure"] == "Информация из открытых источников"

    changed = client.post(
        f"/admin/venue-catalog/venues/{venue['id']}/status",
        json={
            "partnership_status": "verified",
            "comment": "Представитель подтвердил данные",
        },
        headers=auth_header(admin["token"]),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["source_type"] == "automated_import"
    assert changed.json()["partnership_status"] == "verified"
    assert changed.json()["is_claimed"] is True

    after = client.get(f"/venues/{venue['id']}")
    assert after.status_code == 200
    assert after.json()["source_type"] == "automated_import"
    assert after.json()["public_disclosure"] is None

    history = client.get(
        f"/admin/venue-catalog/venues/{venue['id']}/history",
        headers=auth_header(admin["token"]),
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["new_status"] == "verified"


def test_moderation_hides_venue_and_freshness_marks_old_data(client):
    venue = _open_data_venue(client)
    admin = _admin(client)
    hidden = client.post(
        f"/admin/venue-catalog/venues/{venue['id']}/moderation",
        json={"moderation_status": "needs_review", "comment": "Недостаточно данных"},
        headers=auth_header(admin["token"]),
    )
    assert hidden.status_code == 200
    assert client.get(f"/venues/{venue['id']}").status_code == 404

    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import Venue

        row = db.get(Venue, venue["id"])
        row.moderation_status = "published"
        row.last_crawled_at = datetime.now(timezone.utc) - timedelta(days=181)
        db.commit()
    finally:
        db.close()
    refreshed = client.post(
        "/admin/venue-catalog/freshness/recalculate",
        headers=auth_header(admin["token"]),
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["stale"] == 1
