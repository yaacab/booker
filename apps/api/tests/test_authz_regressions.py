"""Регрессионные тесты авторизации по результатам аудита (IDOR, OTP, гарды)."""

from datetime import timedelta

from booker_api.config import settings
from booker_api.security import now
from tests.conftest import auth_header, register
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
        json={"body": "привет"},
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 403
    allowed = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "привет"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert allowed.status_code == 200


def test_hold_booking_forbidden_for_outsider(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    outsider = register(client, "hold-out@booker.test", "Посторонний")
    res = client.post(
        f"/bookings/{ctx['booking_id']}/hold",
        headers=auth_header(outsider["token"]),
    )
    assert res.status_code == 403


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
    assert contract["otp_customer"] != "123456"
    assert contract["otp_customer"] != contract["otp_supplier"]
    wrong = client.post(
        f"/contracts/{contract['id']}/sign",
        json={"side": "customer", "otp": "000000"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert wrong.status_code == 403
    cross = client.post(
        f"/contracts/{contract['id']}/sign",
        json={"side": "supplier", "otp": contract["otp_supplier"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert cross.status_code == 403
    ok = client.post(
        f"/contracts/{contract['id']}/sign",
        json={"side": "supplier", "otp": contract["otp_supplier"]},
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
    approver = _promote_admin(client, "ref-b@booker.test")
    early = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "approver_user_id": approver["user_id"],
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
            "approver_user_id": approver["user_id"],
            "totp": totp_code(),
        },
        headers=auth_header(admin["token"]),
    )
    assert first.status_code == 200
    second = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "approver_user_id": approver["user_id"],
            "totp": totp_code(),
        },
        headers=auth_header(admin["token"]),
    )
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert second.json()["status"] == "refunded"


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


def test_logout_invalidates_session(client):
    user = register(client, "logout@booker.test", "Выход")
    out = client.post("/auth/logout", headers=auth_header(user["token"]))
    assert out.status_code == 200
    me = client.get("/me", headers=auth_header(user["token"]))
    assert me.status_code == 401


def test_expired_session_rejected(client):
    user = register(client, "expired@booker.test", "Просрочен")
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import SessionToken

        row = db.get(SessionToken, user["token"])
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
