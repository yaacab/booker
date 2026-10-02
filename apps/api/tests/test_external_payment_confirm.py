"""External transfers are reviewed records, never platform captures."""

from booker_api.config import settings
from booker_api.models import (
    AuditLog,
    Booking,
    ExternalPaymentReport,
    MoneyMovement,
    Payment,
    PaymentWebhookEvent,
)
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_payments import _awaiting_payment, _sign
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def _report(client, ctx, key="external-report-1"):
    return client.post(
        f"/payments/{ctx['payment_id']}/external-report",
        json={"idempotency_key": key, "reference": "bank-operation-123", "details": "Перевод исполнителю"},
        headers=auth_header(ctx["customer"]["token"]),
    )


def test_external_payment_report_rejects_customer_viewer(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "external")
    ctx = _awaiting_payment(client)
    viewer = register(client, "external-report-viewer@booker.test", "Viewer")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert added.status_code == 200
    denied = client.post(
        f"/payments/{ctx['payment_id']}/external-report",
        json={"idempotency_key": "viewer-report-key", "reference": "bank-operation-viewer"},
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.query(ExternalPaymentReport).count() == 0


def test_external_report_key_rejects_changed_bank_reference_or_details(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "external")
    ctx = _awaiting_payment(client)
    original = _report(client, ctx, "immutable-bank-report")
    assert original.status_code == 200
    url = f"/payments/{ctx['payment_id']}/external-report"
    for reference, details in (
        ("different-bank-operation", "Перевод исполнителю"),
        ("bank-operation-123", "Другие детали перевода"),
    ):
        replay = client.post(
            url,
            json={
                "idempotency_key": "immutable-bank-report",
                "reference": reference,
                "details": details,
            },
            headers=auth_header(ctx["customer"]["token"]),
        )
        assert replay.status_code == 409
    with client.app.state.SessionLocal() as db:
        reports = db.query(ExternalPaymentReport).all()
        assert len(reports) == 1
        assert reports[0].reference == "bank-operation-123"
        assert reports[0].details == "Перевод исполнителю"


def test_external_payment_admin_routes_require_totp_before_read_or_decision(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "external")
    ctx = _awaiting_payment(client)
    report = _report(client, ctx)
    assert report.status_code == 200
    admin = _promote_admin(client, "external-no-totp@booker.test")
    headers = auth_header(admin["token"])
    payment_url = f"/admin/payments/{ctx['payment_id']}"
    assert client.get(
        f"{payment_url}/external-reports", params={"totp": totp_code()}, headers=headers
    ).status_code == 403
    body = {"report_id": report.json()["id"], "review_note": "not allowed", "recipient_confirmed": True}
    for action in ("confirm-external", "request-external-clarification"):
        assert client.post(
            f"{payment_url}/{action}", json=body, params={"totp": totp_code()}, headers=headers
        ).status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.get(Payment, ctx["payment_id"]).status == "pending"
        assert db.get(ExternalPaymentReport, report.json()["id"]).status == "submitted"


def test_external_review_rejects_report_from_another_payment(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "external")
    ctx = _awaiting_payment(client)
    report = _report(client, ctx)
    assert report.status_code == 200
    with client.app.state.SessionLocal() as db:
        other_payment = Payment(
            booking_id=ctx["booking_id"], amount_rub=1_000, provider="external",
            status="pending", idempotency_key="other-external-payment",
        )
        db.add(other_payment)
        db.commit()
        other_payment_id = other_payment.id
    admin = _promote_admin(client, "external-pairing-admin@booker.test", totp=TEST_TOTP_SECRET)
    headers = auth_header(admin["token"])
    body = {"report_id": report.json()["id"], "review_note": "Wrong payment", "recipient_confirmed": True}
    for action in ("confirm-external", "request-external-clarification"):
        denied = client.post(
            f"/admin/payments/{other_payment_id}/{action}",
            json=body, params={"totp": totp_code()}, headers=headers,
        )
        assert denied.status_code == 404
    with client.app.state.SessionLocal() as db:
        assert db.get(Payment, other_payment_id).status == "pending"
        assert db.get(ExternalPaymentReport, report.json()["id"]).status == "submitted"


def test_external_report_review_is_not_capture(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "external")
    ctx = _awaiting_payment(client)
    outsider = register(client, "external-outsider@booker.test")
    assert client.post(
        f"/payments/{ctx['payment_id']}/external-report",
        json={"idempotency_key": "outsider", "reference": "operation-1"},
        headers=auth_header(outsider["token"]),
    ).status_code == 403
    report_response = _report(client, ctx)
    assert report_response.status_code == 200, report_response.text
    report_id = report_response.json()["id"]
    assert _report(client, ctx).json()["idempotent"] is True
    assert _report(client, ctx, "new-key").status_code == 409
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=auth_header(ctx["customer"]["token"])).json()
    assert room["payment"]["external_report"]["status"] == "submitted"
    assert "reference" not in room["payment"]["external_report"]

    admin = _promote_admin(client, "ext-pay-admin@booker.test", totp=TEST_TOTP_SECRET)
    queue = client.get(
        f"/admin/payments/{ctx['payment_id']}/external-reports",
        params={"totp": totp_code()}, headers=auth_header(admin["token"]),
    )
    assert queue.status_code == 200
    assert queue.json()["reports"][0]["reference"] == "bank-operation-123"
    url = f"/admin/payments/{ctx['payment_id']}/confirm-external"
    body = {"report_id": report_id, "review_note": "Получатель подтвердил перевод", "recipient_confirmed": True}
    assert client.post(url, json=body, params={"totp": totp_code()}, headers=auth_header(outsider["token"])).status_code == 403
    assert client.post(url, json={**body, "recipient_confirmed": False}, params={"totp": totp_code()}, headers=auth_header(admin["token"])).status_code == 409
    assert client.post(url, json=body, params={"totp": totp_code()}, headers=auth_header(admin["token"])).status_code == 409
    ack = client.post(
        f"/payments/{ctx['payment_id']}/external-reports/{report_id}/recipient-ack",
        json={"idempotency_key": "recipient-ack-123"},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert ack.status_code == 200, ack.text
    res = client.post(url, json=body, params={"totp": totp_code()}, headers=auth_header(admin["token"]))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "external_recorded"
    assert client.post(url, json=body, params={"totp": totp_code()}, headers=auth_header(admin["token"])).json()["idempotent"] is True

    db = client.app.state.SessionLocal()
    try:
        assert db.get(Payment, ctx["payment_id"]).status == "external_recorded"
        assert db.get(Booking, ctx["booking_id"]).status == "AwaitingPayment"
        assert db.get(ExternalPaymentReport, report_id).status == "recorded"
        assert db.query(PaymentWebhookEvent).filter_by(payment_id=ctx["payment_id"]).count() == 0
        assert db.query(AuditLog).filter_by(entity_id=ctx["payment_id"], action="payment.captured").count() == 0
        assert db.query(AuditLog).filter_by(entity_id=ctx["payment_id"], action="payment.external_recorded").count() == 1
        assert db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).count() == 0
    finally:
        db.close()


def test_external_clarification_and_provider_switch_guard(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "external")
    ctx = _awaiting_payment(client)
    report_id = _report(client, ctx).json()["id"]
    admin = _promote_admin(client, "ext-clarify-admin@booker.test", totp=TEST_TOTP_SECRET)
    res = client.post(
        f"/admin/payments/{ctx['payment_id']}/request-external-clarification",
        json={"report_id": report_id, "review_note": "Уточните получателя"},
        params={"totp": totp_code()}, headers=auth_header(admin["token"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["payment_status"] == "pending"
    assert _report(client, ctx, "second-report").status_code == 200
    monkeypatch.setattr(settings, "payment_provider", "stub")
    event_id = "switched-provider-event"
    webhook = client.post("/payments/webhook", json={
        "event_id": event_id, "payment_id": ctx["payment_id"], "status": "succeeded",
        "signature": _sign(event_id, ctx["payment_id"], "succeeded"),
    })
    assert webhook.status_code == 409
    stub = client.post(
        f"/payments/{ctx['payment_id']}/stub-complete",
        json={"status": "succeeded"}, headers=auth_header(ctx["customer"]["token"]),
    )
    assert stub.status_code == 403
    db = client.app.state.SessionLocal()
    try:
        assert db.get(Payment, ctx["payment_id"]).status == "pending"
        assert db.get(Booking, ctx["booking_id"]).status == "AwaitingPayment"
    finally:
        db.close()
