"""OfferVersion / quote_id invariants — immutable versions, active quote, stale rejection."""

from tests.conftest import auth_header
from tests.test_offers import ack_both, setup_negotiation


def _ack_side(client, ctx, side, token=None):
    token = token or (ctx["owner"]["token"] if side == "supplier" else ctx["customer"]["token"])
    return client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": side},
        headers=auth_header(token),
    )


def _new_version(client, ctx, honorarium_rub, terms="новая смета"):
    return client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": honorarium_rub, "terms": terms},
        headers=auth_header(ctx["owner"]["token"]),
    )


def test_old_version_cannot_confirm_new_price(client):
    ctx = setup_negotiation(client)
    v1_id = ctx["offer"]["version"]["id"]
    ack_both(client, ctx)

    v2 = _new_version(client, ctx, 120000)
    assert v2.status_code == 200, v2.text
    v2_id = v2.json()["id"]
    assert v2_id != v1_id
    assert v2.json()["quote_id"] == v2_id
    assert v2.json()["active"] is False

    hold = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert hold.status_code == 409

    _ack_side(client, ctx, "supplier")
    hold = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert hold.status_code == 409

    _ack_side(client, ctx, "customer")
    hold = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert hold.status_code == 200

    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["quote"]["quote_id"] == v2_id
    assert room["quote"]["honorarium_rub"] == 120000


def test_quote_id_bound_to_offer_version(client):
    ctx = setup_negotiation(client)
    v1 = ctx["offer"]["version"]
    assert v1["quote_id"] == v1["id"]

    room0 = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    event_id = room0["event_id"]

    event = client.get(f"/events/{event_id}", headers=auth_header(ctx["customer"]["token"])).json()
    req_row = next(r for r in event["requests"] if r.get("booking_id") == ctx["booking_id"])
    assert req_row["quote_id"] == v1["id"]

    v2 = _new_version(client, ctx, 110000).json()
    assert v2["quote_id"] == v2["id"]
    assert v2["quote_id"] != v1["id"]

    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["quote"]["quote_id"] == v2["id"]
    assert room["documents"][0]["quote_id"] == v2["id"]

    event_after = client.get(f"/events/{event_id}", headers=auth_header(ctx["customer"]["token"])).json()
    req_after = next(r for r in event_after["requests"] if r.get("booking_id") == ctx["booking_id"])
    assert req_after["quote_id"] == v2["id"]


def test_material_change_creates_new_version(client):
    ctx = setup_negotiation(client)
    first_id = ctx["offer"]["version"]["id"]

    same_terms = _new_version(client, ctx, 100000, terms="2 часа сет")
    assert same_terms.status_code == 200
    body = same_terms.json()
    assert body["id"] != first_id
    assert body["quote_id"] == body["id"]
    assert body["honorarium_rub"] == 100000

    price_up = _new_version(client, ctx, 150000, terms="расширенный сет")
    assert price_up.status_code == 200
    up = price_up.json()
    assert up["id"] != first_id
    assert up["id"] != body["id"]
    assert up["honorarium_rub"] == 150000
    assert up["total_rub"] == 150000

    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import Offer, OfferVersion

        offer = db.get(Offer, ctx["offer"]["id"])
        versions = (
            db.query(OfferVersion)
            .filter(OfferVersion.offer_id == offer.id)
            .order_by(OfferVersion.created_at.asc())
            .all()
        )
        assert len(versions) == 3
        assert versions[0].honorarium_rub == 100000
        assert versions[0].customer_ack is False
        assert versions[1].honorarium_rub == 100000
        assert versions[2].honorarium_rub == 150000
        assert offer.active_version_id == versions[2].id
    finally:
        db.close()


def test_stale_quote_rejection_on_ack(client):
    ctx = setup_negotiation(client)
    stale_quote_id = ctx["offer"]["version"]["id"]

    v2 = _new_version(client, ctx, 130000)
    assert v2.status_code == 200
    active_quote_id = v2.json()["quote_id"]
    assert active_quote_id != stale_quote_id

    stale_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": "supplier", "quote_id": stale_quote_id},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert stale_ack.status_code == 409

    fresh_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": "supplier", "quote_id": active_quote_id},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert fresh_ack.status_code == 200
    assert fresh_ack.json()["quote_id"] == active_quote_id

    # ack without quote_id still works (uses active version)
    v3 = _new_version(client, ctx, 140000)
    active_v3 = v3.json()["quote_id"]
    legacy_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": "supplier"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert legacy_ack.status_code == 200
    assert legacy_ack.json()["quote_id"] == active_v3
