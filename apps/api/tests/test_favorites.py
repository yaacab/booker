"""W3-FAV / E04: избранное без побочных booking/hold/request."""

from booker_api.models import Booking, BookingHold, Request
from tests.conftest import auth_header, register


def _counts(SessionLocal) -> dict[str, int]:
    db = SessionLocal()
    try:
        return {
            "requests": db.query(Request).count(),
            "bookings": db.query(Booking).count(),
            "holds": db.query(BookingHold).count(),
        }
    finally:
        db.close()


def _seed_artist_and_venue(client):
    customer = register(client, "fav-cust@booker.test", "Заказчик")
    owner = register(client, "fav-supply@booker.test", "Снабжение")
    cust_h = auth_header(customer["token"])
    own_h = auth_header(owner["token"])
    cust_org = client.post(
        "/orgs",
        json={"name": "Клиент ФАВ", "kind": "customer"},
        headers=cust_h,
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Артист ФАВ", "kind": "artist"},
        headers=own_h,
    ).json()
    venue_org = client.post(
        "/orgs",
        json={"name": "Площадка ФАВ", "kind": "venue"},
        headers=own_h,
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Избранный", "category": "dj"},
        headers=own_h,
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": venue_org["id"], "name": "Зал Избранный", "capacity": 100},
        headers=own_h,
    ).json()
    return {
        "customer": customer,
        "cust_h": cust_h,
        "cust_org": cust_org,
        "artist": artist,
        "venue": venue,
        "owner": owner,
        "own_h": own_h,
    }


def test_add_list_remove_favorites(client, SessionLocal):
    ctx = _seed_artist_and_venue(client)
    before = _counts(SessionLocal)

    added = client.post(
        "/favorites",
        json={
            "target_type": "artist",
            "target_id": ctx["artist"]["id"],
            "organization_id": ctx["cust_org"]["id"],
        },
        headers=ctx["cust_h"],
    )
    assert added.status_code == 201, added.text
    body = added.json()
    assert body["target_type"] == "artist"
    assert body["target_id"] == ctx["artist"]["id"]
    assert body["user_id"] == ctx["customer"]["user_id"]
    assert body["organization_id"] == ctx["cust_org"]["id"]
    assert body["name"] == "DJ Избранный"
    assert _counts(SessionLocal) == before

    listed = client.get(
        f"/favorites?organization_id={ctx['cust_org']['id']}",
        headers=ctx["cust_h"],
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]

    venue_fav = client.post(
        "/favorites",
        json={
            "target_type": "venue",
            "target_id": ctx["venue"]["id"],
            "organization_id": ctx["cust_org"]["id"],
        },
        headers=ctx["cust_h"],
    )
    assert venue_fav.status_code == 201, venue_fav.text

    listed2 = client.get("/favorites", headers={**ctx["cust_h"], "X-Booker-Org": ctx["cust_org"]["id"]})
    assert listed2.status_code == 200
    assert len(listed2.json()["items"]) == 2

    # idempotent re-add
    again = client.post(
        "/favorites",
        json={
            "target_type": "artist",
            "target_id": ctx["artist"]["id"],
            "organization_id": ctx["cust_org"]["id"],
        },
        headers=ctx["cust_h"],
    )
    assert again.status_code == 201
    assert again.json()["id"] == body["id"]

    removed = client.delete(f"/favorites/{body['id']}", headers=ctx["cust_h"])
    assert removed.status_code == 204

    remaining = client.get(
        f"/favorites?organization_id={ctx['cust_org']['id']}",
        headers=ctx["cust_h"],
    ).json()["items"]
    assert len(remaining) == 1
    assert remaining[0]["target_type"] == "venue"

    by_target = client.delete(
        f"/favorites/target/venue/{ctx['venue']['id']}?organization_id={ctx['cust_org']['id']}",
        headers=ctx["cust_h"],
    )
    assert by_target.status_code == 204
    empty = client.get(
        f"/favorites?organization_id={ctx['cust_org']['id']}",
        headers=ctx["cust_h"],
    ).json()["items"]
    assert empty == []
    assert _counts(SessionLocal) == before


def test_favorites_e04_no_booking_hold_request(client, SessionLocal):
    ctx = _seed_artist_and_venue(client)
    before = _counts(SessionLocal)
    res = client.post(
        "/favorites",
        json={
            "target_type": "artist",
            "target_id": ctx["artist"]["id"],
            "organization_id": ctx["cust_org"]["id"],
        },
        headers=ctx["cust_h"],
    )
    assert res.status_code == 201, res.text
    assert _counts(SessionLocal) == before


def test_favorites_auth_required_and_idor(client):
    ctx = _seed_artist_and_venue(client)
    anon = client.get("/favorites")
    assert anon.status_code == 401

    created = client.post(
        "/favorites",
        json={
            "target_type": "artist",
            "target_id": ctx["artist"]["id"],
            "organization_id": ctx["cust_org"]["id"],
        },
        headers=ctx["cust_h"],
    ).json()

    stranger = register(client, "fav-stranger@booker.test", "Чужой")
    stranger_org = client.post(
        "/orgs",
        json={"name": "Чужой", "kind": "customer"},
        headers=auth_header(stranger["token"]),
    ).json()
    listed = client.get(
        f"/favorites?organization_id={stranger_org['id']}",
        headers=auth_header(stranger["token"]),
    )
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    denied = client.delete(
        f"/favorites/{created['id']}",
        headers=auth_header(stranger["token"]),
    )
    assert denied.status_code == 404

    foreign_org = client.get(
        f"/favorites?organization_id={ctx['cust_org']['id']}",
        headers=auth_header(stranger["token"]),
    )
    assert foreign_org.status_code == 403
