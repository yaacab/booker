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


def test_admin_metrics_requires_admin(client):
    user = register(client, "metrics-deny@booker.test", "User")
    res = client.get("/admin/metrics", headers=auth_header(user["token"]))
    assert res.status_code == 403


def test_admin_metrics_aggregates_audit(client):
    admin = _promote_admin(client, "metrics@booker.test")
    db = client.app.state.SessionLocal()
    try:
        from datetime import datetime, timedelta, timezone

        from booker_api.models import AuditLog

        ts = datetime.now(timezone.utc)
        db.add_all(
            [
                AuditLog(action="request.created", entity_type="request", entity_id="r1", created_at=ts),
                AuditLog(action="request.created", entity_type="request", entity_id="r1", created_at=ts),
                AuditLog(
                    action="request.created",
                    entity_type="request",
                    entity_id="r2",
                    created_at=ts - timedelta(days=10),
                ),
                AuditLog(action="offer.created", entity_type="offer", entity_id="o1", created_at=ts),
                AuditLog(action="service.created", entity_type="service", entity_id="s1", created_at=ts),
                AuditLog(action="payment.created", entity_type="payment", entity_id="p1", created_at=ts),
                AuditLog(action="payment.webhook", entity_type="payment", entity_id="p1", created_at=ts),
                AuditLog(
                    action="offer.created",
                    entity_type="offer",
                    entity_id="o-old",
                    created_at=ts - timedelta(days=40),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    res = client.get("/admin/metrics", headers=auth_header(admin["token"]))
    assert res.status_code == 200
    body = res.json()
    assert body["periods"]["7"]["request.created"] == {"count": 2, "unique_entities": 1}
    assert body["periods"]["30"]["request.created"] == {"count": 3, "unique_entities": 2}
    assert body["periods"]["7"]["offer.created"] == {"count": 1, "unique_entities": 1}
    assert body["periods"]["30"]["offer.created"] == {"count": 1, "unique_entities": 1}
    assert body["periods"]["7"]["payment"]["count"] == 2
    assert body["periods"]["7"]["payment"]["unique_entities"] == 1
    assert body["periods"]["7"]["payment"]["by_action"] == {
        "payment.created": 1,
        "payment.webhook": 1,
    }


def test_admin_metrics_client_events_by_name(client):
    admin = _promote_admin(client, "metrics-client@booker.test")
    db = client.app.state.SessionLocal()
    try:
        from datetime import datetime, timezone

        from booker_api.models import AuditLog

        ts = datetime.now(timezone.utc)
        db.add_all(
            [
                AuditLog(action="client.event", entity_type="client_event", entity_id="search.performed", created_at=ts),
                AuditLog(action="client.event", entity_type="client_event", entity_id="search.performed", created_at=ts),
                AuditLog(action="client.event", entity_type="client_event", entity_id="deal.room.opened", created_at=ts),
            ]
        )
        db.commit()
    finally:
        db.close()
    res = client.get("/admin/metrics", headers=auth_header(admin["token"]))
    row = res.json()["periods"]["7"]["client.event"]
    assert row["count"] == 3
    assert row["by_event"]["search.performed"] == 2
    assert row["by_event"]["deal.room.opened"] == 1
