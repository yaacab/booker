from tests.conftest import auth_header, register
from tests.test_payments import _awaiting_payment, _sign


def _promote_admin(client, email: str, totp: str | None = None) -> dict:
    user = register(client, email, "Админ")
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import User

        row = db.get(User, user["user_id"])
        row.is_platform_admin = True
        if totp:
            row.totp_enabled = True
            row.totp_secret = totp
        db.commit()
    finally:
        db.close()
    return user


def test_audit_cannot_be_deleted(client):
    admin = _promote_admin(client, "adm@booker.test")
    res = client.delete("/admin/audit/any", headers=auth_header(admin["token"]))
    assert res.status_code == 403


def test_refund_requires_second_admin(client):
    ctx = _awaiting_payment(client)
    client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-ref",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-ref", ctx["payment_id"], "succeeded"),
        },
    )
    admin = _promote_admin(client, "adm2@booker.test", totp="111111")
    same = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "approver_user_id": admin["user_id"],
            "totp": "111111",
        },
        headers=auth_header(admin["token"]),
    )
    assert same.status_code == 403
    other = _promote_admin(client, "adm3@booker.test")
    ok = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "approver_user_id": other["user_id"],
            "totp": "111111",
        },
        headers=auth_header(admin["token"]),
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "refunded"
    logs = client.get("/admin/audit", headers=auth_header(admin["token"]))
    assert logs.status_code == 200
    assert len(logs.json()["items"]) > 0


def test_list_verifications_includes_pending_venues(client):
    admin = _promote_admin(client, "adm-ver@booker.test")
    owner = register(client, "venue-ver@booker.test", "Venue Owner")
    org = client.post(
        "/orgs",
        json={"name": "Площадка", "kind": "venue"},
        headers=auth_header(owner["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": org["id"], "name": "Зал для проверки", "city": "Москва", "capacity": 80},
        headers=auth_header(owner["token"]),
    ).json()
    res = client.get("/admin/verifications", headers=auth_header(admin["token"]))
    assert res.status_code == 200
    body = res.json()
    venues = body.get("venues") or []
    assert any(v["id"] == venue["id"] and v["status"] == "pending" for v in venues)
