"""Catalog search filters — Spec v3 E01–E03 / Wave 1."""

from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, register


def _future_slot(hours=18):
    start = datetime.now(timezone.utc) + timedelta(days=10)
    start = start.replace(hour=hours, minute=0, second=0, microsecond=0)
    return start.isoformat(), (start + timedelta(hours=4)).isoformat()


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


def test_search_synthetic_venue_flag_present(client):
    """E03: synthetic availability_mode is returned on search cards."""
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
    from booker_api.models import Venue

    SessionLocal = client.app.state.SessionLocal
    db = SessionLocal()
    try:
        row = db.get(Venue, venue["id"])
        assert row is not None
        row.availability_mode = "synthetic"
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
    syn = next(v for v in res["venues"] if v["name"] == "Синтетика Холл")
    assert syn["availability_mode"] == "synthetic"
