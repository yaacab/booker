"""OfferVersion / quote_id invariants — immutable versions, active quote, stale rejection."""

from sqlalchemy import text

from booker_api.models import Booking, ContractSignature, OfferAcknowledgement
from booker_api.offer_version_binding import backfill_accepted_offer_versions
from tests.conftest import auth_header, contract_otps, register
from tests.test_offers import ack_both, setup_negotiation


def _ack_side(client, ctx, side, token=None):
    token = token or (ctx["owner"]["token"] if side == "supplier" else ctx["customer"]["token"])
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    return client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": side, "quote_id": room["quote"]["quote_id"]},
        headers=auth_header(token),
    )


def _new_version(client, ctx, honorarium_rub, terms="новая смета"):
    return client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": honorarium_rub, "terms": terms},
        headers=auth_header(ctx["owner"]["token"]),
    )


def test_acting_organization_controls_ack_and_signature(client, SessionLocal):
    ctx = setup_negotiation(client)
    customer_headers = auth_header(ctx["customer"]["token"])
    supplier_headers = auth_header(ctx["owner"]["token"])
    added = client.post(
        f"/orgs/{ctx['artist_org']['id']}/members",
        json={
            "user_id": ctx["customer"]["user_id"],
            "role": "manager",
            "can_confirm_offer": True,
        },
        headers=supplier_headers,
    )
    assert added.status_code == 200, added.text
    quote_id = ctx["offer"]["version"]["quote_id"]
    assert client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers={**customer_headers, "X-Booker-Org": ctx["cust_org"]["id"]},
    ).json()["role"] == "customer"
    supplier_workspace = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers={**customer_headers, "X-Booker-Org": ctx["artist_org"]["id"]},
    ).json()
    assert supplier_workspace["role"] == "supplier"
    assert supplier_workspace["acting_org_id"] == ctx["artist_org"]["id"]

    ambiguous = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": "customer", "quote_id": quote_id},
        headers=customer_headers,
    )
    assert ambiguous.status_code == 409
    mismatch = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": "customer", "quote_id": quote_id},
        headers={**customer_headers, "X-Booker-Org": ctx["artist_org"]["id"]},
    )
    assert mismatch.status_code == 409
    customer_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"quote_id": quote_id},
        headers={**customer_headers, "X-Booker-Org": ctx["cust_org"]["id"]},
    )
    assert customer_ack.status_code == 200
    repeated_customer_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"quote_id": quote_id},
        headers={**customer_headers, "X-Booker-Org": ctx["cust_org"]["id"]},
    )
    assert repeated_customer_ack.status_code == 200
    same_actor_other_side = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"quote_id": quote_id},
        headers={**customer_headers, "X-Booker-Org": ctx["artist_org"]["id"]},
    )
    assert same_actor_other_side.status_code == 409
    supplier_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"quote_id": quote_id},
        headers={**supplier_headers, "X-Booker-Org": ctx["artist_org"]["id"]},
    )
    assert supplier_ack.status_code == 200

    with SessionLocal() as db:
        acknowledgements = {
            row.side: row
            for row in db.query(OfferAcknowledgement)
            .filter_by(offer_version_id=quote_id)
            .all()
        }
        assert acknowledgements["customer"].actor_user_id == ctx["customer"]["user_id"]
        assert acknowledgements["customer"].organization_id == ctx["cust_org"]["id"]
        assert acknowledgements["customer"].created_at is not None
        assert acknowledgements["supplier"].actor_user_id == ctx["owner"]["user_id"]
        assert acknowledgements["supplier"].organization_id == ctx["artist_org"]["id"]
        assert acknowledgements["supplier"].created_at is not None

    held = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers={**customer_headers, "X-Booker-Org": ctx["cust_org"]["id"]},
    )
    assert held.status_code == 200, held.text
    created = client.post(
        f"/bookings/{ctx['booking_id']}/contract",
        headers={**customer_headers, "X-Booker-Org": ctx["cust_org"]["id"]},
    )
    assert created.status_code == 200, created.text
    contract_id = created.json()["id"]
    contract_hash = created.json()["body_sha256"]
    customer_otps = contract_otps(
        SessionLocal,
        contract_id,
        actor_user_id=ctx["customer"]["user_id"],
    )
    supplier_otps = contract_otps(
        SessionLocal,
        contract_id,
        actor_user_id=ctx["owner"]["user_id"],
    )

    viewer = register(client, "contract-viewer@booker.test", "Наблюдатель")
    assert client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=customer_headers,
    ).status_code == 200
    assert client.post(
        f"/contracts/{contract_id}/sign",
        json={"otp": customer_otps["otp_customer"], "body_hash": contract_hash},
        headers={
            **auth_header(viewer["token"]),
            "X-Booker-Org": ctx["cust_org"]["id"],
        },
    ).status_code == 403

    ambiguous_sign = client.post(
        f"/contracts/{contract_id}/sign",
        json={"otp": customer_otps["otp_customer"], "body_hash": contract_hash},
        headers=customer_headers,
    )
    assert ambiguous_sign.status_code == 409
    customer_sign = client.post(
        f"/contracts/{contract_id}/sign",
        json={"otp": customer_otps["otp_customer"], "body_hash": contract_hash},
        headers={**customer_headers, "X-Booker-Org": ctx["cust_org"]["id"]},
    )
    assert customer_sign.status_code == 200
    repeated_customer_sign = client.post(
        f"/contracts/{contract_id}/sign",
        json={"otp": customer_otps["otp_customer"], "body_hash": contract_hash},
        headers={**customer_headers, "X-Booker-Org": ctx["cust_org"]["id"]},
    )
    assert repeated_customer_sign.status_code == 403
    same_signer_other_side = client.post(
        f"/contracts/{contract_id}/sign",
        json={"otp": customer_otps["otp_supplier"], "body_hash": contract_hash},
        headers={**customer_headers, "X-Booker-Org": ctx["artist_org"]["id"]},
    )
    assert same_signer_other_side.status_code == 409
    supplier_sign = client.post(
        f"/contracts/{contract_id}/sign",
        json={"otp": supplier_otps["otp_supplier"], "body_hash": contract_hash},
        headers={**supplier_headers, "X-Booker-Org": ctx["artist_org"]["id"]},
    )
    assert supplier_sign.status_code == 200

    with SessionLocal() as db:
        signatures = {
            row.side: row
            for row in db.query(ContractSignature).filter_by(contract_id=contract_id).all()
        }
        assert signatures["customer"].actor_user_id == ctx["customer"]["user_id"]
        assert signatures["customer"].organization_id == ctx["cust_org"]["id"]
        assert signatures["customer"].created_at is not None
        assert signatures["supplier"].actor_user_id == ctx["owner"]["user_id"]
        assert signatures["supplier"].organization_id == ctx["artist_org"]["id"]
        assert signatures["supplier"].created_at is not None


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


def test_accepted_version_persisted_and_legacy_backfill_requires_evidence(client):
    ctx = setup_negotiation(client)
    engine = client.app.state.SessionLocal.kw["bind"]
    booking_id = ctx["booking_id"]
    quote_id = ctx["offer"]["version"]["id"]

    with engine.begin() as connection:
        assert backfill_accepted_offer_versions(connection) == 0
    ack_both(client, ctx)
    db = client.app.state.SessionLocal()
    try:
        assert db.get(Booking, booking_id).accepted_offer_version_id == quote_id
    finally:
        db.close()

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE bookings SET accepted_offer_version_id = NULL WHERE id = :id"),
            {"id": booking_id},
        )
        assert backfill_accepted_offer_versions(connection) == 1
        assert connection.execute(
            text("SELECT accepted_offer_version_id FROM bookings WHERE id = :id"),
            {"id": booking_id},
        ).scalar_one() == quote_id


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

    # Missing quote_id must never silently select a newer price.
    v3 = _new_version(client, ctx, 140000)
    active_v3 = v3.json()["quote_id"]
    missing_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": "supplier"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert missing_ack.status_code == 400
    explicit_ack = client.post(
        f"/offers/{ctx['offer']['id']}/ack",
        json={"side": "supplier", "quote_id": active_v3},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert explicit_ack.status_code == 200
