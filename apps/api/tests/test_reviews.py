import pytest

from tests.conftest import activate_venue, auth_header, register
from tests.test_event_day_checkin import _confirmed_booking


def _completed_booking(client):
    ctx = _confirmed_booking(client)
    check_in = client.post(f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"])
    assert check_in.status_code == 200, check_in.text
    check_out = client.post(f"/bookings/{ctx['booking_id']}/check-out", headers=ctx["ch"])
    assert check_out.status_code == 200, check_out.text
    assert check_out.json()["status"] == "Completed"
    return ctx


def test_review_rejected_when_confirmed(client):
    ctx = _confirmed_booking(client)
    res = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 5, "text": "ещё рано"},
        headers=ctx["ch"],
    )
    assert res.status_code == 409
    assert "заверш" in res.json()["detail"].lower()


def test_review_accepted_when_completed(client):
    ctx = _completed_booking(client)
    res = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 5, "text": "всё прошло отлично"},
        headers=ctx["ch"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["booking_id"] == ctx["booking_id"]
    assert body["rating"] == 5
    assert body["text"] == "всё прошло отлично"
    assert body["org_id"] == ctx["artist_org"]["id"]
    assert body["author_user_id"] == ctx["customer"]["user_id"]

    listed = client.get(f"/organizations/{ctx['artist_org']['id']}/reviews")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]

    artist_list = client.get(f"/artists/{ctx['artist']['id']}/reviews")
    assert artist_list.status_code == 200
    assert len(artist_list.json()["items"]) == 1


def test_review_duplicate_rejected(client):
    ctx = _completed_booking(client)
    first = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 4, "text": "первый"},
        headers=ctx["ch"],
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 3, "text": "повтор"},
        headers=ctx["ch"],
    )
    assert second.status_code == 409
    assert "уже" in second.json()["detail"].lower()


def test_review_forbidden_for_stranger(client):
    ctx = _completed_booking(client)
    stranger = register(client, "stranger-rev@booker.test", "Чужой")
    res = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 1, "text": "спам"},
        headers=auth_header(stranger["token"]),
    )
    assert res.status_code == 403


def test_supplier_can_review_customer_org(client):
    ctx = _completed_booking(client)
    oh = auth_header(ctx["owner"]["token"])
    res = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 5, "text": "заказчик на связи"},
        headers=oh,
    )
    assert res.status_code == 200, res.text
    assert res.json()["org_id"] == ctx["cust_org"]["id"]


def test_empty_org_reviews_is_empty_list(client):
    owner = register(client, "empty-rev@booker.test", "Пустой")
    org = client.post(
        "/orgs",
        json={"name": "Без отзывов", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    res = client.get(f"/organizations/{org['id']}/reviews")
    assert res.status_code == 200
    assert res.json()["items"] == []


def _completed_venue_review(client, *, resource_type="venue"):
    """Retarget a completed fixture deal to an active venue in the same supplier org."""
    from booker_api.models import Booking, Offer, Request

    ctx = _completed_booking(client)
    venue = client.post(
        "/venues",
        json={"organization_id": ctx["artist_org"]["id"], "name": "Отзывная площадка", "capacity": 100},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert venue.status_code == 200, venue.text
    venue = venue.json()
    activate_venue(client, venue["id"])

    db = client.app.state.SessionLocal()
    try:
        offer = db.get(Offer, db.get(Booking, ctx["booking_id"]).offer_id)
        request = db.get(Request, offer.request_id)
        request.resource_type = resource_type
        request.resource_id = venue["hall_id"] if resource_type == "hall" else venue["id"]
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 5, "text": "Отзыв о скрываемой площадке"},
        headers=ctx["ch"],
    )
    assert response.status_code == 200, response.text
    return ctx, venue, response.json()


@pytest.mark.parametrize("resource_type", ["venue", "hall"])
@pytest.mark.parametrize("revocation", ["media", "calendar", "price", "partnership"])
def test_revoked_venue_reviews_hidden_from_guest_and_org_aggregate(client, resource_type, revocation):
    from booker_api.models import AvailabilitySlot, Venue, VenuePhoto, VenueTariff

    ctx, venue, review = _completed_venue_review(client, resource_type=resource_type)
    venue_url = f"/venues/{venue['id']}/reviews"
    org_url = f"/organizations/{ctx['artist_org']['id']}/reviews"
    assert client.get(venue_url).json()["count"] == 1
    assert [item["id"] for item in client.get(org_url).json()["items"]] == [review["id"]]

    db = client.app.state.SessionLocal()
    try:
        row = db.get(Venue, venue["id"])
        if revocation == "media":
            db.query(VenuePhoto).filter_by(venue_id=row.id).delete()
        elif revocation == "calendar":
            db.query(AvailabilitySlot).filter_by(resource_type="hall", resource_id=venue["hall_id"]).delete()
        elif revocation == "price":
            db.query(VenueTariff).filter_by(venue_id=row.id).delete()
        else:
            row.partnership_status = "claimed"
        db.commit()
    finally:
        db.close()

    assert client.get(venue_url).status_code == 404
    assert client.get(org_url).json()["items"] == []
    owner_headers = auth_header(ctx["owner"]["token"])
    assert client.get(venue_url, headers=owner_headers).json()["count"] == 1
    assert [item["id"] for item in client.get(org_url, headers=owner_headers).json()["items"]] == [review["id"]]
