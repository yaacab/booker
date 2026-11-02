from tests.conftest import auth_header, register
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
    assert "booking_id" not in items[0]
    assert "author_user_id" not in items[0]

    artist_list = client.get(f"/artists/{ctx['artist']['id']}/reviews")
    assert artist_list.status_code == 200
    assert len(artist_list.json()["items"]) == 1
    assert "booking_id" not in artist_list.json()["items"][0]
    assert "author_user_id" not in artist_list.json()["items"][0]


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


def test_viewer_cannot_publish_review_for_organization(client, SessionLocal):
    from booker_api.models import AuditLog, Review

    ctx = _completed_booking(client)
    viewer = register(client, "viewer-rev@booker.test", "Viewer")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=ctx["ch"],
    )
    assert added.status_code == 200, added.text
    with SessionLocal() as db:
        before = (db.query(Review).count(), db.query(AuditLog).count())
    denied = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 1, "text": "Отзыв наблюдателя"},
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403, denied.text
    with SessionLocal() as db:
        assert (db.query(Review).count(), db.query(AuditLog).count()) == before


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
    body = res.json()
    assert body["items"] == []
    assert body["reputation"]["review_count"] == 0
    assert body["reputation"]["show_rating"] is False


def test_reputation_hides_average_before_ten_reviews(client, SessionLocal):
    from booker_api.models import Booking, Review

    ctx = _completed_booking(client)
    org_id = ctx["artist_org"]["id"]
    with SessionLocal() as db:
        base = db.get(Booking, ctx["booking_id"])
        assert base is not None
        for idx in range(9):
            clone = Booking(
                event_id=base.event_id,
                offer_id=base.offer_id,
                slot_id=base.slot_id,
                status="Completed",
            )
            db.add(clone)
            db.flush()
            db.add(
                Review(
                    booking_id=clone.id,
                    author_user_id=ctx["customer"]["user_id"],
                    org_id=org_id,
                    rating=4,
                    text=f"факт {idx}",
                )
            )
        db.commit()

    below = client.get(f"/organizations/{org_id}/reputation")
    assert below.status_code == 200
    below_body = below.json()
    assert below_body["review_count"] == 9
    assert below_body["show_rating"] is False
    assert "average_rating" not in below_body

    with SessionLocal() as db:
        base = db.get(Booking, ctx["booking_id"])
        assert base is not None
        tenth = Booking(
            event_id=base.event_id,
            offer_id=base.offer_id,
            slot_id=base.slot_id,
            status="Completed",
        )
        db.add(tenth)
        db.flush()
        db.add(
            Review(
                booking_id=tenth.id,
                author_user_id=ctx["customer"]["user_id"],
                org_id=org_id,
                rating=5,
                text="десятый",
            )
        )
        db.commit()

    above = client.get(f"/organizations/{org_id}/reputation")
    assert above.status_code == 200
    above_body = above.json()
    assert above_body["review_count"] == 10
    assert above_body["show_rating"] is True
    assert above_body["average_rating"] == 4.1


def test_deal_room_exposes_review_projection_after_complete(client):
    ctx = _completed_booking(client)
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=ctx["ch"])
    assert room.status_code == 200, room.text
    reviews = room.json()["reviews"]
    assert reviews["can_submit"] is True
    assert reviews["my_review"] is None
    assert reviews["target_org_id"] == ctx["artist_org"]["id"]

    posted = client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 5, "text": "из deal room"},
        headers=ctx["ch"],
    )
    assert posted.status_code == 200, posted.text

    again = client.get(f"/deal-room/{ctx['booking_id']}", headers=ctx["ch"])
    assert again.status_code == 200
    after = again.json()["reviews"]
    assert after["can_submit"] is False
    assert after["my_review"]["rating"] == 5
    assert after["pending_counterparty"] is True


def test_artist_catalog_facts_include_review_count(client):
    ctx = _completed_booking(client)
    client.post(
        f"/bookings/{ctx['booking_id']}/reviews",
        json={"rating": 5, "text": "в факты каталога"},
        headers=ctx["ch"],
    )
    artist = client.get(f"/artists/{ctx['artist']['id']}")
    assert artist.status_code == 200, artist.text
    facts = artist.json()["facts"]
    assert facts["reviews"] == 1
    assert facts["show_rating"] is False
    assert "average_rating" not in facts
