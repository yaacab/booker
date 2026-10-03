from booker_api.models import (
    Booking,
    Dispute,
    DisputeEvidence,
    MoneyMovement,
    Payment,
    RefundRequest,
)
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_attachments import MINIMAL_PDF
from tests.test_payments import _awaiting_payment, _sign
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def _confirm(client):
    ctx = _awaiting_payment(client)
    client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-dispute",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-dispute", ctx["payment_id"], "succeeded"),
        },
    )
    return ctx


def test_dispute_requires_category_from_list(client):
    ctx = _confirm(client)
    free = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "whatever", "notes": "текст"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert free.status_code == 400
    ok = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "no_show", "notes": "артист не приехал"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert ok.status_code == 200
    assert ok.json()["ai_decides"] is False
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["status"] == "Dispute"


def test_booking_dispute_list_denies_outsider(client):
    ctx = _confirm(client)
    customer_headers = auth_header(ctx["customer"]["token"])
    created = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "quality", "notes": "Private dispute details"},
        headers=customer_headers,
    )
    assert created.status_code == 200, created.text
    outsider = register(client, "dispute-list-outsider@booker.test", "Outsider")
    path = f"/bookings/{ctx['booking_id']}/disputes"
    assert client.get(path, headers=customer_headers).status_code == 200
    denied = client.get(path, headers=auth_header(outsider["token"]))
    assert denied.status_code == 403
    assert "Private dispute details" not in denied.text


def test_tampered_clean_attachment_cannot_be_added_as_dispute_evidence(
    client, tmp_path, monkeypatch
):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _confirm(client)
    headers = auth_header(ctx["customer"]["token"])
    opened = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "payment", "notes": "Проверка доказательства"},
        headers=headers,
    )
    assert opened.status_code == 200
    uploaded = client.post(
        f"/bookings/{ctx['booking_id']}/attachments",
        files={"file": ("evidence.pdf", MINIMAL_PDF, "application/pdf")},
        headers=headers,
    )
    assert uploaded.status_code == 200
    attachment_id = uploaded.json()["id"]
    admin = _promote_admin(client, "tampered-evidence-admin@booker.test", totp=TEST_TOTP_SECRET)
    scanned = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "Проверено", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert scanned.status_code == 200
    stored = next((tmp_path / ctx["booking_id"]).iterdir())
    stored.write_bytes(MINIMAL_PDF + b"tampered")
    denied = client.post(
        f"/disputes/{opened.json()['id']}/evidence",
        json={"attachment_id": attachment_id, "note": "Изменённый файл"},
        headers=headers,
    )
    assert denied.status_code == 409
    with client.app.state.SessionLocal() as db:
        assert db.query(DisputeEvidence).count() == 0


def test_dispute_assignment_and_resolution_require_configured_admin_totp(client):
    ctx = _confirm(client)
    opened = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "payment", "notes": "Проверка второго фактора"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert opened.status_code == 200
    dispute_id = opened.json()["id"]
    admin = _promote_admin(client, "no-totp-dispute@booker.test")
    headers = auth_header(admin["token"])
    denied_assignment = client.put(
        f"/admin/disputes/{dispute_id}/assignment",
        json={"assignee_user_id": admin["user_id"], "state_version": 0, "totp": totp_code()},
        headers=headers,
    )
    assert denied_assignment.status_code == 403
    with client.app.state.SessionLocal() as db:
        dispute = db.get(Dispute, dispute_id)
        assert dispute.state_version == 0
        dispute.assigned_to_user_id = admin["user_id"]
        dispute.status = "in_review"
        dispute.state_version = 1
        db.commit()
    denied_resolution = client.put(
        f"/admin/disputes/{dispute_id}/resolve",
        json={
            "decision_kind": "refund_review_required",
            "decision_note": "Решение оператора",
            "state_version": 1,
            "totp": totp_code(),
        },
        headers=headers,
    )
    assert denied_resolution.status_code == 403
    with client.app.state.SessionLocal() as db:
        dispute = db.get(Dispute, dispute_id)
        assert dispute.status == "in_review"
        assert dispute.state_version == 1


def test_dispute_case_queue_evidence_and_resolution_are_fail_closed(
    client, tmp_path, monkeypatch
):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _confirm(client)
    customer_headers = auth_header(ctx["customer"]["token"])
    opened = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "payment", "notes": "Оплата требует проверки"},
        headers=customer_headers,
    )
    assert opened.status_code == 200, opened.text
    dispute = opened.json()
    assert dispute["priority"] == "urgent"
    assert dispute["response_due_at"] is not None
    assert dispute["state_version"] == 0
    assert dispute["ai_decides"] is False

    duplicate = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "quality", "notes": "Повтор"},
        headers=customer_headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["dispute_id"] == dispute["id"]

    outsider = register(client, "dispute-outsider@booker.test", "Outsider")
    hidden = client.get(
        f"/bookings/{ctx['booking_id']}/disputes",
        headers=auth_header(outsider["token"]),
    )
    assert hidden.status_code == 403

    upload = client.post(
        f"/bookings/{ctx['booking_id']}/attachments",
        files={"file": ("evidence.pdf", MINIMAL_PDF, "application/pdf")},
        headers=customer_headers,
    )
    assert upload.status_code == 200, upload.text
    attachment_id = upload.json()["id"]
    quarantined = client.post(
        f"/disputes/{dispute['id']}/evidence",
        json={"attachment_id": attachment_id, "note": "Подтверждение"},
        headers=customer_headers,
    )
    assert quarantined.status_code == 409

    operator = _promote_admin(client, "dispute-operator@booker.test", totp=TEST_TOTP_SECRET)
    second_operator = _promote_admin(
        client, "dispute-second@booker.test", totp=TEST_TOTP_SECRET
    )
    scan = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "Проверено", "totp": totp_code()},
        headers=auth_header(operator["token"]),
    )
    assert scan.status_code == 200, scan.text
    evidence = client.post(
        f"/disputes/{dispute['id']}/evidence",
        json={"attachment_id": attachment_id, "note": "Подтверждение"},
        headers=customer_headers,
    )
    assert evidence.status_code == 200, evidence.text
    replay = client.post(
        f"/disputes/{dispute['id']}/evidence",
        json={"attachment_id": attachment_id, "note": "Повтор"},
        headers=customer_headers,
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True

    queue = client.get("/admin/disputes", headers=auth_header(operator["token"]))
    assert queue.status_code == 200
    queued = next(row for row in queue.json()["items"] if row["id"] == dispute["id"])
    assert queued["evidence"][0]["attachment_id"] == attachment_id

    no_totp = client.put(
        f"/admin/disputes/{dispute['id']}/assignment",
        json={"assignee_user_id": operator["user_id"], "state_version": 0},
        headers=auth_header(operator["token"]),
    )
    assert no_totp.status_code == 403
    assigned = client.put(
        f"/admin/disputes/{dispute['id']}/assignment",
        json={
            "assignee_user_id": operator["user_id"],
            "state_version": 0,
            "totp": totp_code(),
        },
        headers=auth_header(operator["token"]),
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["status"] == "in_review"
    assert assigned.json()["state_version"] == 1

    wrong_operator = client.put(
        f"/admin/disputes/{dispute['id']}/resolve",
        json={
            "decision_kind": "refund_review_required",
            "decision_note": "Передать на отдельную проверку возврата",
            "state_version": 1,
            "totp": totp_code(),
        },
        headers=auth_header(second_operator["token"]),
    )
    assert wrong_operator.status_code == 403
    stale = client.put(
        f"/admin/disputes/{dispute['id']}/resolve",
        json={
            "decision_kind": "refund_review_required",
            "decision_note": "Передать на отдельную проверку возврата",
            "state_version": 0,
            "totp": totp_code(),
        },
        headers=auth_header(operator["token"]),
    )
    assert stale.status_code == 409

    with client.app.state.SessionLocal() as db:
        payment_status_before = db.get(Payment, ctx["payment_id"]).status
        movements_before = db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).count()
        assert db.query(RefundRequest).filter_by(payment_id=ctx["payment_id"]).count() == 0
    resolved = client.put(
        f"/admin/disputes/{dispute['id']}/resolve",
        json={
            "decision_kind": "refund_review_required",
            "decision_note": "Передать на отдельную проверку возврата",
            "state_version": 1,
            "totp": totp_code(),
        },
        headers=auth_header(operator["token"]),
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["requires_separate_refund_request"] is True
    assert resolved.json()["automatic_money_movement"] is False

    with client.app.state.SessionLocal() as db:
        assert db.get(Payment, ctx["payment_id"]).status == payment_status_before
        assert db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).count() == movements_before
        assert db.query(RefundRequest).filter_by(payment_id=ctx["payment_id"]).count() == 0
        assert db.get(Booking, ctx["booking_id"]).status == "Resolved"

    closed_evidence = client.post(
        f"/disputes/{dispute['id']}/evidence",
        json={"attachment_id": attachment_id, "note": "Позднее доказательство"},
        headers=customer_headers,
    )
    assert closed_evidence.status_code == 409
    participant_view = client.get(
        f"/bookings/{ctx['booking_id']}/disputes", headers=customer_headers
    )
    assert participant_view.status_code == 200
    assert participant_view.json()["items"][0]["decision_kind"] == "refund_review_required"
