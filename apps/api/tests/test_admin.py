import pytest

from booker_api.config import settings
from booker_api.models import MoneyMovement, Payment, RefundRequest
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_payments import _awaiting_payment, _sign
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def _promote_admin(client, email: str, totp: str | None = None) -> dict:
    user = register(client, email, "Админ")
    user["pre_promotion_token"] = user["token"]
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import User

        row = db.get(User, user["user_id"])
        row.email_verified_at = now()
        row.is_platform_admin = True
        if totp:
            row.totp_enabled = True
            row.totp_secret = totp
        db.commit()
    finally:
        db.close()
    if totp:
        login = client.post("/auth/login", json={
            "email": email, "password": "password1", "totp": totp_code(totp),
        })
        assert login.status_code == 200, login.text
        user["token"] = login.json()["token"]
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
    admin = _promote_admin(client, "adm2@booker.test", totp=TEST_TOTP_SECRET)
    refund = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "totp": totp_code(),
        },
        headers=auth_header(admin["token"]),
    )
    assert refund.status_code == 200
    assert refund.json()["status"] == "pending"
    refund_id = refund.json()["id"]
    same = client.post(
        f"/admin/refunds/{refund_id}/approve",
        json={"totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert same.status_code == 403
    other = _promote_admin(client, "adm3@booker.test", totp=TEST_TOTP_SECRET)
    ok = client.post(
        f"/admin/refunds/{refund_id}/approve",
        json={"totp": totp_code()},
        headers=auth_header(other["token"]),
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "refunded"
    replay = client.post(
        f"/admin/refunds/{refund_id}/approve",
        json={"totp": totp_code()},
        headers=auth_header(other["token"]),
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True
    with client.app.state.SessionLocal() as db:
        payment_amount = db.get(Payment, ctx["payment_id"]).amount_rub
        movements = (
            db.query(MoneyMovement)
            .filter_by(payment_id=ctx["payment_id"])
            .order_by(MoneyMovement.created_at, MoneyMovement.id)
            .all()
        )
        assert [(m.kind, m.direction, m.amount_rub) for m in movements] == [
            ("capture", "credit", payment_amount),
            ("refund", "debit", payment_amount),
        ]
        movements[0].amount_rub += 1
        with pytest.raises(ValueError, match="неизменяемы"):
            db.commit()
        db.rollback()
    logs = client.get("/admin/audit", headers=auth_header(admin["token"]))
    assert logs.status_code == 200
    assert len(logs.json()["items"]) > 0


def test_refund_uses_original_stub_rail_after_checkout_mode_switch(client, monkeypatch):
    ctx = _awaiting_payment(client)
    captured = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-rail-switch",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-rail-switch", ctx["payment_id"], "succeeded"),
        },
    )
    assert captured.status_code == 200, captured.text
    initiator = _promote_admin(client, "refund-rail-first@booker.test", totp=TEST_TOTP_SECRET)
    approver = _promote_admin(client, "refund-rail-second@booker.test", totp=TEST_TOTP_SECRET)
    requested = client.post(
        "/admin/refunds",
        json={"payment_id": ctx["payment_id"], "totp": totp_code(), "reason": "Тест"},
        headers=auth_header(initiator["token"]),
    )
    assert requested.status_code == 200, requested.text
    monkeypatch.setattr(settings, "payment_provider", "external")
    approved = client.post(
        f"/admin/refunds/{requested.json()['id']}/approve",
        json={"totp": totp_code()},
        headers=auth_header(approver["token"]),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "refunded"


def test_refund_request_rejects_processing_duplicate_and_partial_without_calculation(client):
    ctx = _awaiting_payment(client)
    captured = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-refund-duplicate",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-refund-duplicate", ctx["payment_id"], "succeeded"),
        },
    )
    assert captured.status_code == 200, captured.text
    admin = _promote_admin(client, "refund-duplicate-admin@booker.test", totp=TEST_TOTP_SECRET)
    headers = auth_header(admin["token"])
    payload = {"payment_id": ctx["payment_id"], "totp": totp_code(), "reason": "Проверка"}
    first = client.post("/admin/refunds", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    with client.app.state.SessionLocal() as db:
        request_row = db.get(RefundRequest, first.json()["id"])
        request_row.status = "processing"
        db.commit()
    duplicate = client.post("/admin/refunds", json=payload, headers=headers)
    assert duplicate.status_code == 409
    with client.app.state.SessionLocal() as db:
        request_row = db.get(RefundRequest, first.json()["id"])
        request_row.status = "refunded"
        payment = db.get(Payment, ctx["payment_id"])
        payment.status = "partially_refunded"
        db.commit()
    partial = client.post("/admin/refunds", json=payload, headers=headers)
    assert partial.status_code == 409
    assert "расчёт остатка" in partial.json()["detail"]


def test_refund_finalization_failure_keeps_durable_dispatch_and_blocks_retry(client, monkeypatch):
    ctx = _awaiting_payment(client)
    captured = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-refund-finalization-failure",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign(
                "evt-refund-finalization-failure", ctx["payment_id"], "succeeded"
            ),
        },
    )
    assert captured.status_code == 200, captured.text
    initiator = _promote_admin(client, "refund-intent-first@booker.test", totp=TEST_TOTP_SECRET)
    approver = _promote_admin(client, "refund-intent-second@booker.test", totp=TEST_TOTP_SECRET)
    requested = client.post(
        "/admin/refunds",
        json={"payment_id": ctx["payment_id"], "totp": totp_code(), "reason": "Проверка сбоя"},
        headers=auth_header(initiator["token"]),
    )
    assert requested.status_code == 200, requested.text
    refund_request_id = requested.json()["id"]

    import booker_api.routers.admin as admin_router
    from booker_api.payments.stub import StubPaymentAdapter

    original_refund = StubPaymentAdapter.refund
    provider_calls = []

    def refund_once(self, **kwargs):
        provider_calls.append(kwargs["idempotency_key"])
        return original_refund(self, **kwargs)

    def fail_finalization(*_args, **_kwargs):
        raise RuntimeError("simulated finalization failure")

    monkeypatch.setattr(StubPaymentAdapter, "refund", refund_once)
    monkeypatch.setattr(admin_router, "append_money_movement", fail_finalization)
    url = f"/admin/refunds/{refund_request_id}/approve"
    headers = auth_header(approver["token"])
    with pytest.raises(RuntimeError, match="simulated finalization failure"):
        client.post(url, json={"totp": totp_code()}, headers=headers)

    with client.app.state.SessionLocal() as db:
        refund_request = db.get(RefundRequest, refund_request_id)
        payment = db.get(Payment, ctx["payment_id"])
        assert refund_request.status == "processing"
        assert payment.status == "succeeded"
        assert db.query(MoneyMovement).filter_by(payment_id=payment.id, kind="refund").count() == 0
    replay = client.post(url, json={"totp": totp_code()}, headers=headers)
    assert replay.status_code == 409
    assert provider_calls == [f"refund-{refund_request_id}"]


def test_refund_rejects_provider_kind_inconsistent_with_amount(client, monkeypatch):
    ctx = _awaiting_payment(client)
    captured = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-refund-wrong-kind",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-refund-wrong-kind", ctx["payment_id"], "succeeded"),
        },
    )
    assert captured.status_code == 200, captured.text
    initiator = _promote_admin(client, "refund-kind-first@booker.test", totp=TEST_TOTP_SECRET)
    approver = _promote_admin(client, "refund-kind-second@booker.test", totp=TEST_TOTP_SECRET)
    requested = client.post(
        "/admin/refunds",
        json={"payment_id": ctx["payment_id"], "totp": totp_code()},
        headers=auth_header(initiator["token"]),
    )
    assert requested.status_code == 200, requested.text
    refund_request_id = requested.json()["id"]
    with client.app.state.SessionLocal() as db:
        amount_rub = db.get(Payment, ctx["payment_id"]).amount_rub

    from booker_api.payments.adapter import RefundOutcome
    from booker_api.payments.stub import StubPaymentAdapter

    monkeypatch.setattr(
        StubPaymentAdapter,
        "refund",
        lambda _self, **_kwargs: RefundOutcome(
            refund_id="provider-inconsistent-kind",
            amount_rub=amount_rub,
            kind="partial",
            status="succeeded",
        ),
    )
    response = client.post(
        f"/admin/refunds/{refund_request_id}/approve",
        json={"totp": totp_code()},
        headers=auth_header(approver["token"]),
    )
    assert response.status_code == 409
    with client.app.state.SessionLocal() as db:
        assert db.get(RefundRequest, refund_request_id).status == "processing"
        assert db.get(Payment, ctx["payment_id"]).status == "succeeded"
        assert db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"], kind="refund").count() == 0


def test_list_verifications_includes_pending_venues(client):
    admin = _promote_admin(client, "adm-ver@booker.test", totp=TEST_TOTP_SECRET)
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


def test_verification_rejects_unknown_target_type(client):
    admin = _promote_admin(client, "verify-type-admin@booker.test", totp=TEST_TOTP_SECRET)
    owner = register(client, "verify-type-owner@booker.test", "Owner")
    headers = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Venue", "kind": "venue"}, headers=headers).json()
    venue = client.post(
        "/venues", json={"organization_id": org["id"], "name": "Venue"}, headers=headers
    ).json()
    response = client.post(
        "/admin/verifications",
        json={"target_type": "payment", "target_id": venue["id"], "approve": True},
        headers=auth_header(admin["token"]),
    )
    assert response.status_code == 422
    with client.app.state.SessionLocal() as db:
        from booker_api.models import Venue

        assert db.get(Venue, venue["id"]).verified_status == "pending"


def test_non_admin_cannot_run_verification_dispute_outbox_or_read_audit(client):
    user = register(client, "admin-guard-outsider@booker.test", "Outsider")
    headers = auth_header(user["token"])
    checks = (
        ("get", "/admin/verifications", None),
        ("post", "/admin/verifications", {
            "target_type": "artist", "target_id": "unknown", "approve": True,
        }),
        ("post", "/admin/disputes?booking_id=unknown", {
            "category": "quality", "notes": "Unauthorized",
        }),
        ("post", "/admin/email-outbox/retry", None),
        ("get", "/admin/audit", None),
    )
    for method, path, body in checks:
        response = getattr(client, method)(path, headers=headers, **({"json": body} if body else {}))
        assert response.status_code == 403, (path, response.text)


def test_admin_metrics_requires_admin(client):
    user = register(client, "metrics-deny@booker.test", "User")
    res = client.get("/admin/metrics", headers=auth_header(user["token"]))
    assert res.status_code == 403


def test_non_admin_cannot_read_admin_queues_or_delete_audit(client):
    user = register(client, "admin-private-queues@booker.test", "Outsider")
    headers = auth_header(user["token"])
    for path in (
        "/admin/disputes",
        "/admin/support/tickets",
        "/admin/venue-catalog/venues",
        "/admin/venue-catalog/venues/unknown/history",
        "/admin/venue-catalog/batches",
        "/admin/venue-catalog/report",
    ):
        denied = client.get(path, headers=headers)
        assert denied.status_code == 403, (path, denied.text)
    deleted = client.delete("/admin/audit/unknown", headers=headers)
    assert deleted.status_code == 403


def test_admin_metrics_aggregates_audit(client):
    admin = _promote_admin(client, "metrics@booker.test", totp=TEST_TOTP_SECRET)
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
    admin = _promote_admin(client, "metrics-client@booker.test", totp=TEST_TOTP_SECRET)
    db = client.app.state.SessionLocal()
    try:
        import json
        from datetime import datetime, timezone

        from booker_api.models import AuditLog

        ts = datetime.now(timezone.utc)
        db.add_all(
            [
                AuditLog(
                    action="client.event",
                    entity_type="client_event",
                    entity_id="evt-1",
                    actor_user_id=admin["user_id"],
                    payload=json.dumps({"name": "search.performed"}),
                    created_at=ts,
                ),
                AuditLog(
                    action="client.event",
                    entity_type="client_event",
                    entity_id="evt-2",
                    actor_user_id=admin["user_id"],
                    payload=json.dumps({"name": "search.performed"}),
                    created_at=ts,
                ),
                AuditLog(
                    action="client.event",
                    entity_type="client_event",
                    entity_id="evt-3",
                    actor_user_id="other-user",
                    payload=json.dumps({"name": "deal.room.opened"}),
                    created_at=ts,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()
    res = client.get("/admin/metrics", headers=auth_header(admin["token"]))
    row = res.json()["periods"]["7"]["client.event"]
    assert row["count"] == 3
    assert row["unique_entities"] == 2
    assert row["by_event"]["search.performed"] == 2
    assert row["by_event"]["deal.room.opened"] == 1


def test_admin_metrics_client_events_unique_users(client):
    admin = _promote_admin(client, "metrics-uniq@booker.test", totp=TEST_TOTP_SECRET)
    db = client.app.state.SessionLocal()
    try:
        import json
        from datetime import datetime, timezone

        from booker_api.models import AuditLog

        ts = datetime.now(timezone.utc)
        for idx, user_id in enumerate(["u1", "u2", "u3"]):
            db.add(
                AuditLog(
                    action="client.event",
                    entity_type="client_event",
                    entity_id=f"evt-{idx}",
                    actor_user_id=user_id,
                    payload=json.dumps({"name": "search.performed"}),
                    created_at=ts,
                )
            )
        db.commit()
    finally:
        db.close()
    res = client.get("/admin/metrics", headers=auth_header(admin["token"]))
    row = res.json()["periods"]["7"]["client.event"]
    assert row["count"] == 3
    assert row["unique_entities"] == 3


def test_admin_metrics_dashboards(client):
    admin = _promote_admin(client, "metrics-dash@booker.test", totp=TEST_TOTP_SECRET)
    db = client.app.state.SessionLocal()
    try:
        from datetime import datetime, timezone

        from booker_api.models import AuditLog

        ts = datetime.now(timezone.utc)
        db.add_all(
            [
                AuditLog(
                    action="client.event",
                    entity_type="client_event",
                    entity_id="evt-studio-1",
                    payload='{"name": "event.studio.started"}',
                    created_at=ts,
                ),
                AuditLog(
                    action="client.event",
                    entity_type="client_event",
                    entity_id="evt-studio-2",
                    payload='{"name": "event.studio.completed"}',
                    created_at=ts,
                ),
                AuditLog(action="request.created", entity_type="request", entity_id="r1", created_at=ts),
                AuditLog(action="offer.created", entity_type="offer", entity_id="o1", created_at=ts),
                AuditLog(action="hold.created", entity_type="booking", entity_id="b1", created_at=ts),
                AuditLog(action="hold.expired", entity_type="booking", entity_id="b2", created_at=ts),
                AuditLog(
                    action="client.event",
                    entity_type="client_event",
                    entity_id="evt-search-1",
                    payload='{"name": "search.performed"}',
                    created_at=ts,
                ),
                AuditLog(
                    action="client.event",
                    entity_type="client_event",
                    entity_id="evt-deal-1",
                    payload='{"name": "deal.room.opened"}',
                    created_at=ts,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    res = client.get("/admin/metrics", headers=auth_header(admin["token"]))
    dash = res.json()["periods"]["7"]["dashboards"]
    funnel_counts = {s["step"]: s["count"] for s in dash["funnel"]["steps"]}
    assert funnel_counts["event.studio.started"] == 1
    assert funnel_counts["request.created"] == 1
    assert dash["liquidity"]["offer_response_pct"] == 100.0
    assert dash["leakage"]["studio_abandoned"] == 0
    assert dash["leakage"]["holds_expired"] == 1


def test_legacy_admin_totp_enable_cannot_bypass_channel_proof(client):
    admin = _promote_admin(client, "totp-setup@booker.test")
    res = client.post(
        "/admin/totp/enable",
        json={"secret": TEST_TOTP_SECRET, "password": "password1", "code": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert res.status_code == 410


def test_non_admin_cannot_enable_admin_totp(client, SessionLocal):
    from booker_api.models import User

    user = register(client, "totp-non-admin@booker.test", "User")
    denied = client.post(
        "/admin/totp/enable",
        json={"secret": TEST_TOTP_SECRET, "password": "password1", "code": totp_code()},
        headers=auth_header(user["token"]),
    )
    assert denied.status_code == 410
    with SessionLocal() as db:
        row = db.get(User, user["user_id"])
        assert row.totp_enabled is False
        assert row.totp_secret is None


def test_admin_can_run_idempotent_payment_reminder_worker(client):
    ordinary = register(client, "reminders-nonadmin@booker.test", "User")
    assert client.post(
        "/admin/payment-reminders/run?totp=000000",
        headers=auth_header(ordinary["token"]),
    ).status_code == 403
    no_totp = _promote_admin(client, "reminders-no-totp@booker.test", totp=None)
    denied = client.post(
        f"/admin/payment-reminders/run?totp={totp_code()}",
        headers=auth_header(no_totp["token"]),
    )
    assert denied.status_code == 403
    admin = _promote_admin(client, "reminders-admin@booker.test", totp=TEST_TOTP_SECRET)
    assert client.post(
        "/admin/payment-reminders/run?totp=000000",
        headers=auth_header(admin["token"]),
    ).status_code == 403
    first = client.post(
        f"/admin/payment-reminders/run?totp={totp_code()}",
        headers=auth_header(admin["token"]),
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"created": 0, "existing": 0}
