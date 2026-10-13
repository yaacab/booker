"""Evidence and authorization checks for draft acknowledgements."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from booker_api.config import settings
from booker_api.models import (
    AuditLog,
    Booking,
    Contract,
    ContractChallenge,
    ContractSignature,
    EmailOutbox,
    Message,
    TeamMember,
)
from tests.conftest import auth_header, contract_otps, register
from tests.test_offers import ack_both, setup_negotiation


def _issue(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    customer_headers = auth_header(ctx["customer"]["token"])
    assert client.post(f"/bookings/{ctx['booking_id']}/hold", headers=customer_headers).status_code == 200
    response = client.post(f"/bookings/{ctx['booking_id']}/contract", headers=customer_headers)
    assert response.status_code == 200, response.text
    return ctx, response.json()


def test_exact_snapshot_and_hash_evidence(client, SessionLocal):
    ctx, contract = _issue(client)
    assert "2 часа сет" in contract["body"]
    assert "Условия платежей JSON:" in contract["body"]
    assert "Предмет и стороны сделки JSON:" in contract["body"]
    assert '"title":"Корпоратив"' in contract["body"]
    assert f'"booking_id":"{ctx["booking_id"]}"' in contract["body"]
    assert f'"slot_id":"{ctx["slot"]["id"]}"' in contract["body"]
    inbox = client.get(
        "/notifications?limit=100",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()["items"]
    private_code_messages = [
        item for item in inbox
        if item["entity_id"] == contract["id"] and item["channel"] == "in_app"
    ]
    assert len(private_code_messages) == 1
    assert "Ваш код технического подтверждения" in private_code_messages[0]["body"]
    assert contract["offer_version_id"] == ctx["offer"]["version"]["quote_id"]
    assert contract["body_sha256"] == hashlib.sha256(contract["body"].encode()).hexdigest()
    assert contract["effect"] == "technical_draft_acknowledgement"
    with SessionLocal() as db:
        row = db.get(Contract, contract["id"])
        assert row.otp_customer is None and row.otp_supplier is None
        challenges = db.query(ContractChallenge).filter_by(contract_id=row.id).all()
        assert len(challenges) == 2
        assert all("$" in challenge.otp_hash for challenge in challenges)
        assert all(challenge.actor_user_id in {ctx["customer"]["user_id"], ctx["owner"]["user_id"]} for challenge in challenges)
    otps = contract_otps(SessionLocal, contract["id"])
    customer_headers = auth_header(ctx["customer"]["token"])
    wrong_hash = client.post(f"/contracts/{contract['id']}/sign", headers=customer_headers,
                             json={"otp": otps["otp_customer"], "body_hash": "0" * 64})
    assert wrong_hash.status_code == 409
    signed = client.post(f"/contracts/{contract['id']}/sign", headers=customer_headers,
                         json={"otp": otps["otp_customer"], "body_hash": contract["body_sha256"]})
    assert signed.status_code == 200, signed.text
    replay = client.post(f"/contracts/{contract['id']}/sign", headers=customer_headers,
                         json={"otp": otps["otp_customer"], "body_hash": contract["body_sha256"]})
    assert replay.status_code == 403
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=customer_headers).json()
    assert room["contract"]["body"] == contract["body"]
    assert room["contract"]["body_sha256"] == contract["body_sha256"]
    assert room["contract"]["acknowledgements"][0]["body_sha256"] == contract["body_sha256"]
    with SessionLocal() as db:
        signature = db.query(ContractSignature).filter_by(contract_id=contract["id"]).one()
        assert signature.offer_version_id == contract["offer_version_id"]


def test_viewer_has_no_challenge_and_snapshot_is_immutable(client, SessionLocal):
    ctx = setup_negotiation(client)
    viewer = register(client, "draft-viewer@booker.test", "Наблюдатель")
    assert client.post(f"/orgs/{ctx['cust_org']['id']}/members",
                       json={"user_id": viewer["user_id"], "role": "viewer"},
                       headers=auth_header(ctx["customer"]["token"])).status_code == 200
    ack_both(client, ctx)
    customer_headers = auth_header(ctx["customer"]["token"])
    assert client.post(f"/bookings/{ctx['booking_id']}/hold", headers=customer_headers).status_code == 200
    contract = client.post(f"/bookings/{ctx['booking_id']}/contract", headers=customer_headers).json()
    with SessionLocal() as db:
        assert db.query(ContractChallenge).filter_by(contract_id=contract["id"], actor_user_id=viewer["user_id"]).count() == 0
    with pytest.raises(DatabaseError), SessionLocal() as db:
        db.execute(text("UPDATE contracts SET body = 'tampered' WHERE id = :id"), {"id": contract["id"]})
        db.commit()


def test_role_downgrade_revokes_issued_code(client, SessionLocal):
    ctx, contract = _issue(client)
    code = contract_otps(SessionLocal, contract["id"])["otp_customer"]
    with SessionLocal() as db:
        member = db.query(TeamMember).filter_by(
            organization_id=ctx["cust_org"]["id"],
            user_id=ctx["customer"]["user_id"],
        ).one()
        member.role = "viewer"
        db.commit()
    response = client.post(
        f"/contracts/{contract['id']}/sign",
        headers=auth_header(ctx["customer"]["token"]),
        json={"otp": code, "body_hash": contract["body_sha256"]},
    )
    assert response.status_code == 403


def test_expired_code_fails_closed(client, SessionLocal, monkeypatch):
    from booker_api.routers import payments

    original = payments.new_challenge

    def expired_challenge():
        code, digest, _expiry = original()
        return code, digest, datetime.now(timezone.utc) - timedelta(seconds=1)

    monkeypatch.setattr(payments, "new_challenge", expired_challenge)
    ctx, contract = _issue(client)
    code = contract_otps(SessionLocal, contract["id"])["otp_customer"]
    response = client.post(
        f"/contracts/{contract['id']}/sign",
        headers=auth_header(ctx["customer"]["token"]),
        json={"otp": code, "body_hash": contract["body_sha256"]},
    )
    assert response.status_code == 403

    monkeypatch.setattr(payments, "new_challenge", original)
    reissued = client.post(
        f"/contracts/{contract['id']}/challenge",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert reissued.status_code == 200, reissued.text
    assert reissued.json()["effect"] == "technical_draft_acknowledgement"
    replacement = contract_otps(SessionLocal, contract["id"])["otp_customer"]
    assert replacement != code
    confirmed = client.post(
        f"/contracts/{contract['id']}/sign",
        headers=auth_header(ctx["customer"]["token"]),
        json={"otp": replacement, "body_hash": contract["body_sha256"]},
    )
    assert confirmed.status_code == 200, confirmed.text


def test_active_challenge_is_not_reissued(client):
    ctx, contract = _issue(client)
    response = client.post(
        f"/contracts/{contract['id']}/challenge",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Текущий код ещё действует"


def test_event_composition_change_is_blocked_after_snapshot_issue(
    client, SessionLocal
):
    ctx, contract = _issue(client)
    requirement = ctx["event"]["requirements"][0]
    changed = client.put(
        f"/events/{ctx['event']['id']}/requirements",
        headers=auth_header(ctx["customer"]["token"]),
        json={"items": [{
            "id": requirement["id"],
            "category_code": "dj",
            "qty": 2,
            "required": True,
            "notes": "Изменение состава после выпуска снимка",
        }]},
    )
    assert changed.status_code == 409, changed.text
    assert "зафиксирован" in changed.json()["detail"]
    otps = contract_otps(SessionLocal, contract["id"])
    customer = client.post(
        f"/contracts/{contract['id']}/sign",
        headers=auth_header(ctx["customer"]["token"]),
        json={"otp": otps["otp_customer"], "body_hash": contract["body_sha256"]},
    )
    supplier = client.post(
        f"/contracts/{contract['id']}/sign",
        headers=auth_header(ctx["owner"]["token"]),
        json={"otp": otps["otp_supplier"], "body_hash": contract["body_sha256"]},
    )
    assert customer.status_code == 200, customer.text
    assert supplier.status_code == 200, supplier.text
    assert supplier.json()["booking_status"] == "AwaitingPayment"
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["contract"]["body"] == contract["body"]
    assert "Изменение состава после выпуска снимка" not in room["contract"]["body"]


def test_payment_requires_matching_immutable_signature_rows(client, SessionLocal):
    ctx, contract = _issue(client)
    with SessionLocal() as db:
        row = db.get(Contract, contract["id"])
        booking = db.get(Booking, ctx["booking_id"])
        row.customer_signed = True
        row.supplier_signed = True
        booking.status = "AwaitingPayment"
        db.commit()
    response = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        headers=auth_header(ctx["customer"]["token"]),
        json={"idempotency_key": "forged-contract-flags"},
    )
    assert response.status_code == 409


def test_smtp_reissue_uses_unique_ephemeral_delivery_without_outbox_plaintext(
    client, SessionLocal, monkeypatch
):
    from booker_api.notifications.transports import smtp
    from booker_api.routers import payments

    deliveries: list[tuple[str, str]] = []

    def deliver(row):
        deliveries.append((row.idempotency_key, row.body))
        return True, "sent"

    monkeypatch.setattr(settings, "in_app_provider", "audit")
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.booker.test")
    monkeypatch.setattr(smtp, "_deliver", deliver)
    original = payments.new_challenge

    def expired_challenge():
        code, digest, _expiry = original()
        return code, digest, datetime.now(timezone.utc) - timedelta(seconds=1)

    monkeypatch.setattr(payments, "new_challenge", expired_challenge)
    ctx, contract = _issue(client)
    initial_keys = {key for key, _body in deliveries}
    initial_customer_body = next(
        body for _key, body in deliveries if "Ваш код технического" in body
    )

    monkeypatch.setattr(payments, "new_challenge", original)
    reissued = client.post(
        f"/contracts/{contract['id']}/challenge",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert reissued.status_code == 200, reissued.text
    assert len({key for key, _body in deliveries}) == len(deliveries)
    assert {key for key, _body in deliveries} > initial_keys
    assert deliveries[-1][1] != initial_customer_body
    with SessionLocal() as db:
        assert db.query(EmailOutbox).filter_by(entity_id=contract["id"]).count() == 0
        audit_payloads = [
            row.payload
            for row in db.query(AuditLog).filter_by(
                action="notification.email",
                entity_id=contract["id"],
            ).all()
        ]
    for _key, body in deliveries:
        code = body.rsplit(": ", 1)[-1]
        assert all(code not in payload for payload in audit_payloads)


def test_challenge_is_not_persisted_when_no_transport_delivers(
    client, SessionLocal, monkeypatch
):
    monkeypatch.setattr(settings, "in_app_provider", "disabled")
    monkeypatch.setattr(settings, "email_provider", "disabled")
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    headers = auth_header(ctx["customer"]["token"])
    assert client.post(f"/bookings/{ctx['booking_id']}/hold", headers=headers).status_code == 200
    issued = client.post(f"/bookings/{ctx['booking_id']}/contract", headers=headers)
    assert issued.status_code == 200, issued.text
    assert issued.json()["otp_delivered"] is False
    with SessionLocal() as db:
        assert db.query(ContractChallenge).filter_by(
            contract_id=issued.json()["id"]
        ).count() == 0
    reissue = client.post(
        f"/contracts/{issued.json()['id']}/challenge",
        headers=headers,
    )
    assert reissue.status_code == 503
    with SessionLocal() as db:
        assert db.query(ContractChallenge).filter_by(
            contract_id=issued.json()["id"]
        ).count() == 0


def test_initial_delivery_reports_each_side_and_never_claims_both_on_partial_failure(
    client, SessionLocal, monkeypatch
):
    from booker_api.routers import payments

    calls = 0

    def partial_notify(_db, *, actor_user_id, notifications):
        nonlocal calls
        del actor_user_id, notifications
        calls += 1
        delivered = calls == 1
        return [{
            "channel": "email",
            "status": "sent" if delivered else "failed",
            "sent": delivered,
            "provider": "smtp",
        }]

    monkeypatch.setattr(payments, "notify", partial_notify)
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    headers = auth_header(ctx["customer"]["token"])
    assert client.post(
        f"/bookings/{ctx['booking_id']}/hold", headers=headers
    ).status_code == 200
    issued = client.post(
        f"/bookings/{ctx['booking_id']}/contract", headers=headers
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["otp_delivered"] is False
    assert issued.json()["otp_delivery"] == {"customer": True, "supplier": False}
    with SessionLocal() as db:
        sides = {
            row.side
            for row in db.query(ContractChallenge).filter_by(
                contract_id=issued.json()["id"]
            ).all()
        }
        system_message = (
            db.query(Message)
            .filter(Message.body.like("Черновик условий готов%"))
            .order_by(Message.created_at.desc())
            .first()
        )
        assert sides == {"customer"}
        assert system_message is not None
        assert "только одной стороне" in system_message.body
