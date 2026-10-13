"""External transfer correction preserves reports and never invents a bank capture."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from booker_api.config import settings
from booker_api.db import ensure_sqlite_columns
from booker_api.event_day import check_in_booking
from booker_api.models import (
    AuditLog,
    Booking,
    ExternalPaymentEvent,
    ExternalPaymentReport,
    MoneyMovement,
    Payment,
    PaymentObligation,
)
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_payments import _awaiting_payment
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def _reviewed(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "external")
    ctx = _awaiting_payment(client)
    report = client.post(
        f"/payments/{ctx['payment_id']}/external-report",
        json={"idempotency_key": "correction-report", "reference": "operation-123"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert report.status_code == 200, report.text
    report_id = report.json()["id"]
    ack = client.post(
        f"/payments/{ctx['payment_id']}/external-reports/{report_id}/recipient-ack",
        json={"idempotency_key": "correction-ack"}, headers=auth_header(ctx["owner"]["token"]),
    )
    assert ack.status_code == 200, ack.text
    original_admin = _promote_admin(client, "correction-original@booker.test",
                                    totp=TEST_TOTP_SECRET)
    reviewed = client.post(
        f"/admin/payments/{ctx['payment_id']}/confirm-external",
        json={"report_id": report_id, "review_note": "Сведения сторон совпали",
              "recipient_confirmed": True},
        params={"totp": totp_code()}, headers=auth_header(original_admin["token"]),
    )
    assert reviewed.status_code == 200, reviewed.text
    room = client.get(f"/deal-room/{ctx['booking_id']}",
                      headers=auth_header(ctx["customer"]["token"])).json()
    review_event = next(row for row in room["payment"]["external_timeline"]
                        if row["kind"] == "admin_evidence_reviewed")
    return ctx, report_id, review_event["event_id"], original_admin, room


def test_correction_requires_exact_target_version_and_second_totp_admin(client, monkeypatch):
    ctx, report_id, target_id, original_admin, room = _reviewed(client, monkeypatch)
    url = f"/payments/{ctx['payment_id']}/external-corrections"
    body = {"report_id": report_id, "target_event_id": target_id,
            "reason_code": "wrong_report", "note": "Получатель оспорил сведения",
            "expected_version": room["payment"]["evidence_version"],
            "idempotency_key": "correction-request-1"}
    outsider = register(client, "correction-outsider@booker.test")
    assert client.post(url, json=body, headers=auth_header(outsider["token"])).status_code == 403
    assert client.post(url, json={**body, "amount_rub": 1},
                       headers=auth_header(ctx["customer"]["token"])).status_code == 422
    assert client.post(url, json={**body, "target_event_id": "wrong"},
                       headers=auth_header(ctx["customer"]["token"])).status_code == 404
    assert client.post(url, json={**body, "expected_version": 0},
                       headers=auth_header(ctx["customer"]["token"])).status_code == 409
    requested = client.post(url, json=body, headers=auth_header(ctx["customer"]["token"]))
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["event_id"]
    assert client.post(url, json=body,
                       headers=auth_header(ctx["customer"]["token"])).json()["idempotent"] is True
    assert client.post(url, json={**body, "reason_code": "partial"},
                       headers=auth_header(ctx["customer"]["token"])).status_code == 409

    approval = {"request_event_id": request_id,
                "expected_version": requested.json()["evidence_version"],
                "idempotency_key": "correction-approval-1"}
    approve_url = f"/admin/payments/{ctx['payment_id']}/external-corrections/approve"
    assert client.post(approve_url, json=approval, params={"totp": totp_code()},
                       headers=auth_header(original_admin["token"])).status_code == 403
    no_totp = _promote_admin(client, "correction-no-totp@booker.test")
    assert client.post(approve_url, json=approval, params={"totp": totp_code()},
                       headers=auth_header(no_totp["token"])).status_code == 403
    second_admin = _promote_admin(client, "correction-second@booker.test",
                                  totp=TEST_TOTP_SECRET)
    approved = client.post(approve_url, json=approval, params={"totp": totp_code()},
                           headers=auth_header(second_admin["token"]))
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "corrected"
    assert approved.json()["reliable_money_fact"] is False
    assert client.post(approve_url, json=approval, params={"totp": totp_code()},
                       headers=auth_header(second_admin["token"])).json()["idempotent"] is True
    assert client.post(approve_url, json={**approval, "idempotency_key": "new-approval-key"},
                       params={"totp": totp_code()},
                       headers=auth_header(second_admin["token"])).status_code == 409
    with client.app.state.SessionLocal() as db:
        report = db.get(ExternalPaymentReport, report_id)
        payment = db.get(Payment, ctx["payment_id"])
        booking = db.get(Booking, ctx["booking_id"])
        obligation = db.get(PaymentObligation, payment.obligation_id)
        assert report.status == "recorded" and report.reviewed_by_user_id == original_admin["user_id"]
        assert payment.status == "pending" and obligation.status == "pending"
        assert booking.status == "AwaitingPayment" and booking.payout_blocked is True
        assert db.query(MoneyMovement).filter_by(payment_id=payment.id).count() == 0
        assert db.query(ExternalPaymentEvent).filter_by(payment_id=payment.id).count() == 5
        assert db.query(AuditLog).filter_by(action="payment.external_correction_approved",
                                            entity_id=payment.id).count() == 1
    room_after = client.get(f"/deal-room/{ctx['booking_id']}",
                            headers=auth_header(ctx["customer"]["token"])).json()
    assert room_after["payment"]["effective_evidence_state"] == "corrected"
    assert [row["kind"] for row in room_after["payment"]["external_timeline"]][-1] == (
        "correction_approved"
    )
    event_id = approved.json()["event_id"]
    engine = client.app.state.SessionLocal.kw["bind"]
    with engine.begin() as conn, pytest.raises(DatabaseError, match="append-only"):
        conn.execute(text("UPDATE external_payment_events SET note = 'changed' WHERE id = :id"),
                     {"id": event_id})
    with engine.begin() as conn, pytest.raises(DatabaseError, match="append-only"):
        conn.execute(text("DELETE FROM external_payment_events WHERE id = :id"),
                     {"id": event_id})

    new_report = client.post(
        f"/payments/{ctx['payment_id']}/external-report",
        json={"idempotency_key": "correction-new-report", "reference": "new-operation-456"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert new_report.status_code == 200, new_report.text
    new_room = client.get(f"/deal-room/{ctx['booking_id']}",
                          headers=auth_header(ctx["customer"]["token"])).json()
    assert new_room["payment"]["external_report"]["id"] == new_report.json()["id"]
    assert new_room["payment"]["effective_evidence_state"] == "payer_reported"


def test_partial_or_disputed_report_is_not_money_fact(client, monkeypatch):
    ctx, report_id, target_id, _admin, room = _reviewed(client, monkeypatch)
    for reason in ("partial", "disputed"):
        body = {"report_id": report_id, "target_event_id": target_id,
                "reason_code": reason, "note": "Нужна сверка сторон",
                "expected_version": room["payment"]["evidence_version"],
                "idempotency_key": f"reason-{reason}-test"}
        response = client.post(f"/payments/{ctx['payment_id']}/external-corrections",
                               json=body, headers=auth_header(ctx["customer"]["token"]))
        if reason == "partial":
            assert response.status_code == 200
        else:
            assert response.status_code == 409
    with client.app.state.SessionLocal() as db:
        assert db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).count() == 0
        assert db.get(ExternalPaymentReport, report_id).status == "recorded"


@pytest.mark.parametrize("has_report", [False, True])
def test_legacy_external_confirmed_bookings_are_quarantined(client, monkeypatch, has_report):
    monkeypatch.setattr(settings, "payment_provider", "external")
    if has_report:
        ctx, report_id, _target, _admin, _room = _reviewed(client, monkeypatch)
    else:
        ctx, report_id = _awaiting_payment(client), None
    with client.app.state.SessionLocal() as db:
        booking = db.get(Booking, ctx["booking_id"])
        booking.status = "Confirmed"
        if not has_report:
            db.get(Payment, ctx["payment_id"]).status = "succeeded"
        db.commit()
    ensure_sqlite_columns(client.app.state.SessionLocal.kw["bind"])
    with client.app.state.SessionLocal() as db:
        booking = db.get(Booking, ctx["booking_id"])
        assert booking.status == "Confirmed"
        assert booking.payout_blocked is True
        assert booking.payout_block_reason == "legacy_external_unverified"
        with pytest.raises(ValueError, match="ручной сверки"):
            check_in_booking(booking)
        assert db.get(Payment, ctx["payment_id"]).status == "external_recorded"
        if report_id:
            assert db.get(ExternalPaymentReport, report_id).status == "recorded"
