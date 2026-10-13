"""Регрессионные тесты авторизации по результатам аудита (IDOR, OTP, гарды)."""

from datetime import timedelta

from booker_api.config import settings
from booker_api.security import now
from tests.conftest import auth_header, contract_otps, register
from tests.test_admin import _promote_admin
from tests.test_offers import ack_both, setup_negotiation
from tests.test_payments import _awaiting_payment, _sign
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def _succeeded_payment(client):
    ctx = _awaiting_payment(client)
    res = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-reg",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-reg", ctx["payment_id"], "succeeded"),
        },
    )
    assert res.status_code == 200
    return ctx


def test_post_message_forbidden_for_outsider(client):
    ctx = setup_negotiation(client)
    outsider = register(client, "msg-out@booker.test", "Посторонний")
    denied = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "привет", "idempotency_key": "outsider-message"},
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 404
    allowed = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "привет", "idempotency_key": "customer-message"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert allowed.status_code == 200


def test_deal_room_viewer_cannot_post_message(client):
    from booker_api.models import Message

    ctx = setup_negotiation(client)
    viewer = register(client, "deal-message-viewer@booker.test", "Viewer")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert added.status_code == 200
    with client.app.state.SessionLocal() as db:
        before = db.query(Message).count()
    denied = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "viewer may not write", "idempotency_key": "viewer-message-key"},
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.query(Message).count() == before


def test_hold_booking_forbidden_for_outsider(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    outsider = register(client, "hold-out@booker.test", "Посторонний")
    res = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(outsider["token"]),
    )
    assert res.status_code == 403


def test_supplier_viewer_cannot_hold_booking(client):
    from booker_api.models import BookingHold

    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    viewer = register(client, "hold-viewer@booker.test", "Viewer")
    added = client.post(
        f"/orgs/{ctx['artist_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert added.status_code == 200
    denied = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.query(BookingHold).count() == 0


def test_supplier_manager_can_cancel_when_also_customer_viewer(client):
    ctx = setup_negotiation(client)
    actor = register(client, "dual-cancel@booker.test", "Dual member")
    for org_id, role, inviter in (
        (ctx["cust_org"]["id"], "viewer", ctx["customer"]),
        (ctx["artist_org"]["id"], "manager", ctx["owner"]),
    ):
        added = client.post(
            f"/orgs/{org_id}/members",
            json={"user_id": actor["user_id"], "role": role},
            headers=auth_header(inviter["token"]),
        )
        assert added.status_code == 200
    cancelled = client.post(
        f"/bookings/{ctx['booking_id']}/cancel",
        json={"reason": "Решение менеджера исполнителя"},
        headers=auth_header(actor["token"]),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "Cancelled"


def test_platform_admin_cannot_cancel_booking_without_totp(client):
    from booker_api.models import Booking

    ctx = setup_negotiation(client)
    admin = _promote_admin(client, "cancel-no-totp@booker.test")
    denied = client.post(
        f"/bookings/{ctx['booking_id']}/cancel",
        json={"reason": "Admin without step-up"},
        headers=auth_header(admin["token"]),
    )
    assert denied.status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.get(Booking, ctx["booking_id"]).status == "Negotiation"
    verified = _promote_admin(client, "cancel-with-totp@booker.test", totp=TEST_TOTP_SECRET)
    allowed = client.post(
        f"/bookings/{ctx['booking_id']}/cancel",
        json={"reason": "Admin reviewed cancellation"},
        headers={**auth_header(verified["token"]), "X-Booker-TOTP": totp_code()},
    )
    assert allowed.status_code == 200


def test_customer_viewer_cannot_complete_stub_payment(client):
    from booker_api.models import Payment

    ctx = _awaiting_payment(client)
    viewer = register(client, "pay-viewer@booker.test", "Viewer")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert added.status_code == 200
    denied = client.post(
        f"/payments/{ctx['payment_id']}/stub-complete",
        json={"status": "succeeded"},
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.get(Payment, ctx["payment_id"]).status == "pending"


def test_viewer_and_platform_admin_cannot_create_customer_contract(client):
    from booker_api.models import Booking, Contract

    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    held = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert held.status_code == 200
    viewer = register(client, "contract-create-viewer@booker.test", "Viewer")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert added.status_code == 200
    admin = _promote_admin(client, "contract-create-admin@booker.test")
    for token in (viewer["token"], admin["token"]):
        denied = client.post(
            f"/bookings/{ctx['booking_id']}/contract",
            headers=auth_header(token),
        )
        assert denied.status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.query(Contract).count() == 0
        assert db.get(Booking, ctx["booking_id"]).status == "DateHeld"


def test_customer_viewer_cannot_open_dispute(client):
    from booker_api.models import Dispute

    ctx = _succeeded_payment(client)
    viewer = register(client, "dispute-viewer@booker.test", "Viewer")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert added.status_code == 200
    denied = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "payment", "notes": "viewer must not mutate"},
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.query(Dispute).count() == 0


def test_outsider_cannot_infer_dispute_status_from_evidence_endpoint(client):
    from booker_api.models import Dispute

    ctx = _succeeded_payment(client)
    opened = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "payment", "notes": "Проверка доступа"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert opened.status_code == 200
    dispute_id = opened.json()["id"]
    outsider = register(client, "evidence-outsider@booker.test", "Outsider")
    url = f"/disputes/{dispute_id}/evidence"
    payload = {"attachment_id": "missing", "note": "test"}
    headers = auth_header(outsider["token"])
    assert client.post(url, json=payload, headers=headers).status_code == 404
    with client.app.state.SessionLocal() as db:
        dispute = db.get(Dispute, dispute_id)
        dispute.status = "resolved"
        db.commit()
    assert client.post(url, json=payload, headers=headers).status_code == 404


def test_create_offer_rejects_foreign_slot(client):
    ctx = setup_negotiation(client)
    other = register(client, "slot-owner@booker.test", "Другой артист")
    org = client.post(
        "/orgs",
        json={"name": "Чужое шоу", "kind": "artist"},
        headers=auth_header(other["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ Other", "category": "dj"},
        headers=auth_header(other["token"]),
    ).json()
    foreign_slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": "2026-09-05T18:00:00+00:00",
            "ends_at": "2026-09-05T22:00:00+00:00",
        },
        headers=auth_header(other["token"]),
    ).json()
    # создаём отдельную заявку на артиста из ctx и пробуем оффер с чужим слотом
    event_id = client.get(
        f"/deal-room/{ctx['booking_id']}", headers=auth_header(ctx["customer"]["token"])
    ).json()["event_id"]
    req = client.post(
        f"/events/{event_id}/requests",
        json={"resource_type": "artist", "resource_id": ctx["artist"]["id"]},
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    res = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 50000, "slot_id": foreign_slot["id"]},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert res.status_code == 400


def test_quick_request_rejects_foreign_slot(client):
    ctx = setup_negotiation(client)
    other = register(client, "qr-owner@booker.test", "Другой артист")
    org = client.post(
        "/orgs",
        json={"name": "Иное шоу", "kind": "artist"},
        headers=auth_header(other["token"]),
    ).json()
    other_artist = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ Else", "category": "dj"},
        headers=auth_header(other["token"]),
    ).json()
    other_slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": other_artist["id"],
            "starts_at": "2026-09-06T18:00:00+00:00",
            "ends_at": "2026-09-06T22:00:00+00:00",
        },
        headers=auth_header(other["token"]),
    ).json()
    res = client.post(
        "/quick-request",
        json={"artist_id": ctx["artist"]["id"], "slot_id": other_slot["id"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert res.status_code == 400


def test_contract_requires_participant_and_real_otp(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(ctx["customer"]["token"]),
    )
    outsider = register(client, "ctr-out@booker.test", "Посторонний")
    denied = client.post(
        f"/bookings/{ctx['booking_id']}/contract",
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 403
    contract = client.post(
        f"/bookings/{ctx['booking_id']}/contract",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert contract.get("otp_delivered") is True
    assert "otp_customer" not in contract
    otps = contract_otps(client.app.state.SessionLocal, contract["id"])
    assert otps["otp_customer"] != "123456"
    assert otps["otp_customer"] != otps["otp_supplier"]
    wrong = client.post(
        f"/contracts/{contract['id']}/sign",
        json={"side": "customer", "otp": "000000", "body_hash": contract["body_sha256"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert wrong.status_code == 403
    cross = client.post(
        f"/contracts/{contract['id']}/sign",
        json={"side": "supplier", "otp": otps["otp_supplier"], "body_hash": contract["body_sha256"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert cross.status_code == 409
    ok = client.post(
        f"/contracts/{contract['id']}/sign",
        json={"side": "supplier", "otp": otps["otp_supplier"], "body_hash": contract["body_sha256"]},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert ok.status_code == 200


def test_admin_disputes_requires_admin(client):
    ctx = _succeeded_payment(client)
    denied = client.post(
        f"/admin/disputes?booking_id={ctx['booking_id']}",
        json={"category": "no_show", "notes": "тест"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert denied.status_code == 403


def test_refund_guards_status_and_idempotency(client):
    ctx = _awaiting_payment(client)  # платёж ещё не succeeded
    admin = _promote_admin(client, "ref-a@booker.test", totp=TEST_TOTP_SECRET)
    early = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "totp": totp_code(),
        },
        headers=auth_header(admin["token"]),
    )
    assert early.status_code == 409
    client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-ref-2",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-ref-2", ctx["payment_id"], "succeeded"),
        },
    )
    first = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "totp": totp_code(),
        },
        headers=auth_header(admin["token"]),
    )
    assert first.status_code == 200
    assert first.json()["status"] == "pending"
    second = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "totp": totp_code(),
        },
        headers=auth_header(admin["token"]),
    )
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert second.json()["status"] == "pending"
    approver = _promote_admin(client, "ref-b@booker.test", totp=TEST_TOTP_SECRET)
    approved = client.post(
        f"/admin/refunds/{first.json()['id']}/approve",
        json={"totp": totp_code()},
        headers=auth_header(approver["token"]),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "refunded"
    replay = client.post(
        f"/admin/refunds/{first.json()['id']}/approve",
        json={"totp": totp_code()},
        headers=auth_header(approver["token"]),
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True
    assert replay.json()["status"] == "refunded"


def test_sse_requires_auth_and_membership(client):
    ctx = setup_negotiation(client)
    anon = client.get(f"/sse/bookings/{ctx['booking_id']}")
    assert anon.status_code == 401
    outsider = register(client, "sse-out@booker.test", "Посторонний")
    denied = client.get(
        f"/sse/bookings/{ctx['booking_id']}",
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 403
    ok = client.get(
        f"/sse/bookings/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert ok.status_code == 200
    via_query = client.get(f"/sse/bookings/{ctx['booking_id']}?token={ctx['customer']['token']}")
    assert via_query.status_code == 200


def test_holds_expire_requires_internal_token_or_admin(client):
    anon = client.post("/holds/expire")
    assert anon.status_code == 403
    ok = client.post("/holds/expire", headers={"X-Internal-Token": settings.webhook_secret})
    assert ok.status_code == 200


def test_viewer_cannot_write_catalog(client):
    owner = register(client, "cat-owner@booker.test", "Владелец")
    viewer = register(client, "cat-viewer@booker.test", "Смотритель")
    org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    added = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(owner["token"]),
    )
    assert added.status_code == 200
    denied = client.post(
        "/artists",
        json={"organization_id": org["id"], "name": "DJ View", "category": "dj"},
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403


def test_add_member_duplicate_conflict(client):
    owner = register(client, "dup-owner@booker.test", "Владелец")
    member = register(client, "dup-member@booker.test", "Участник")
    org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    first = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": member["user_id"], "role": "manager"},
        headers=auth_header(owner["token"]),
    )
    assert first.status_code == 200
    dup = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": member["user_id"], "role": "manager"},
        headers=auth_header(owner["token"]),
    )
    assert dup.status_code == 409


def test_org_admin_cannot_assign_owner(client):
    owner = register(client, "role-owner@booker.test", "Владелец")
    admin = register(client, "role-admin@booker.test", "Администратор")
    candidate = register(client, "role-candidate@booker.test", "Кандидат")
    org = client.post(
        "/orgs",
        json={"name": "Команда", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    added = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": admin["user_id"], "role": "admin"},
        headers=auth_header(owner["token"]),
    )
    assert added.status_code == 200

    denied = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": candidate["user_id"], "role": "owner"},
        headers=auth_header(admin["token"]),
    )
    assert denied.status_code == 403

    allowed = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": candidate["user_id"], "role": "owner"},
        headers=auth_header(owner["token"]),
    )
    assert allowed.status_code == 200


def test_logout_invalidates_session(client):
    user = register(client, "logout@booker.test", "Выход")
    out = client.post("/auth/logout", headers=auth_header(user["token"]))
    assert out.status_code == 200
    me = client.get("/me", headers=auth_header(user["token"]))
    assert me.status_code == 401


def test_expired_session_rejected(client):
    import hashlib

    user = register(client, "expired@booker.test", "Просрочен")
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import SessionToken

        token_hash = hashlib.sha256(user["token"].encode()).hexdigest()
        row = db.get(SessionToken, token_hash)
        assert row is not None
        row.expires_at = now() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    me = client.get("/me", headers=auth_header(user["token"]))
    assert me.status_code == 401


def test_new_version_rejected_after_payment_and_bad_honorarium(client):
    ctx = _awaiting_payment(client)
    bad = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 0},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert bad.status_code == 400
    client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-nv",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-nv", ctx["payment_id"], "succeeded"),
        },
    )
    late = client.post(
        f"/offers/{ctx['offer']['id']}/versions",
        json={"honorarium_rub": 150000},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert late.status_code == 409


def test_create_event_missing_fields_400(client):
    user = register(client, "ev-400@booker.test", "Клиент")
    res = client.post("/events", json={}, headers=auth_header(user["token"]))
    assert res.status_code == 400
