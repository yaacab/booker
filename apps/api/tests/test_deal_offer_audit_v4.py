"""V4 DEAL-03: offer version history, renegotiation clear, audit/system message, immutability."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, StatementError

from booker_api.models import AuditLog, Message, OfferVersion
from tests.conftest import auth_header, register
from tests.test_offers import ack_both, setup_negotiation


def test_deal_room_version_history_authz(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    outsider = register(client, "outsider-v4@booker.test", "Чужой")
    denied = client.get(
        f"/offers/{ctx['offer']['id']}/versions",
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 403

    history = client.get(
        f"/offers/{ctx['offer']['id']}/versions",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["offer_id"] == ctx["offer"]["id"]
    assert len(body["versions"]) == 1
    assert body["versions"][0]["is_active"] is True
    assert body["versions"][0]["is_accepted"] is True
    assert body["versions"][0]["customer_ack"] is True
    assert body["versions"][0]["supplier_ack"] is True

    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["owner"]["token"]),
    ).json()
    assert room["accepted_offer_version_id"] == body["accepted_offer_version_id"]
    assert room["active_offer_version_id"] == body["active_version_id"]
    assert room["renegotiation_pending"] is False
    assert len(room["offer_versions"]) == 1


def test_new_version_clears_accepted_and_blocks_hold(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    room_before = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room_before["accepted_offer_version_id"] == room_before["quote"]["quote_id"]

    updated = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 120000, "terms": "пересогласование"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["previous_version_id"] == room_before["quote"]["quote_id"]

    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["accepted_offer_version_id"] is None
    assert room["active_offer_version_id"] == updated.json()["quote_id"]
    assert room["renegotiation_pending"] is True
    assert len(room["offer_versions"]) == 2

    hold = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert hold.status_code == 409


def test_new_version_emits_system_message_and_audit_diff(client, SessionLocal):
    ctx = setup_negotiation(client)
    previous_id = ctx["offer"]["version"]["id"]
    updated = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 130000, "terms": "новая смета v2"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert updated.status_code == 200, updated.text
    new_id = updated.json()["id"]

    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    system_bodies = [m["body"] for m in room["messages"] if m["kind"] == "system"]
    assert any(new_id in body and "новая версия" in body for body in system_bodies)

    timeline = room["offer_timeline"]
    version_events = [row for row in timeline if row["action"] == "offer.version"]
    assert version_events
    payload = version_events[-1]["payload"]
    assert payload["previous_version_id"] == previous_id
    assert payload["honorarium_rub"] == 130000
    assert payload["terms_changed"] is True
    assert payload["honorarium_delta_rub"] == 30000

    with SessionLocal() as db:
        audit = (
            db.query(AuditLog)
            .filter_by(action="offer.version", entity_id=new_id)
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert audit is not None
        assert previous_id in audit.payload
        messages = (
            db.query(Message)
            .filter(Message.kind == "system", Message.body.contains(new_id))
            .all()
        )
        assert messages


def test_offer_version_commercial_row_immutable(client):
    ctx = setup_negotiation(client)
    version_id = ctx["offer"]["version"]["id"]

    with client.app.state.SessionLocal() as db:
        with pytest.raises((DatabaseError, StatementError)):
            db.execute(
                text("UPDATE offer_versions SET honorarium_rub = 1 WHERE id = :id"),
                {"id": version_id},
            )
            db.commit()
        db.rollback()
        with pytest.raises((DatabaseError, StatementError)):
            db.execute(
                text("UPDATE offer_versions SET terms = 'взлом' WHERE id = :id"),
                {"id": version_id},
            )
            db.commit()
        db.rollback()
        db.execute(
            text("UPDATE offer_versions SET customer_ack = 1 WHERE id = :id"),
            {"id": version_id},
        )
        db.commit()
        row = db.get(OfferVersion, version_id)
        assert row.customer_ack is True


def test_outsider_cannot_read_deal_timeline(client):
    ctx = setup_negotiation(client)
    outsider = register(client, "timeline-outsider@booker.test", "Чужой")
    denied = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 403
