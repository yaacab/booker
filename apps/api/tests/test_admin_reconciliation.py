from datetime import timedelta

from booker_api.models import AuditLog, Booking, EmailOutbox, Payment, ReconciliationDiscrepancy
from booker_api.reconciliation import import_reconciliation_report
from tests.conftest import auth_header
from tests.test_admin import _promote_admin
from tests.test_reconciliation import _captured, _report_row, _run
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def _payload(facts, *, entries=None):
    return {
        "provider": "stub",
        "merchant": facts["merchant"],
        "report_id": "admin-report-1",
        "period_start": (facts["movement_at"] - timedelta(hours=1)).isoformat(),
        "period_end": (facts["movement_at"] + timedelta(hours=1)).isoformat(),
        "entries": [_report_row(facts)] if entries is None else entries,
        "totp": totp_code(),
    }


def test_admin_reconciliation_acl_totp_import_replay_and_resolution(client):
    ctx, facts = _captured(client)
    customer_headers = auth_header(ctx["customer"]["token"])
    admin = _promote_admin(client, "reconciliation-admin@booker.test", TEST_TOTP_SECRET)
    admin_headers = auth_header(admin["token"])
    body = _payload(facts, entries=[])

    assert client.post("/admin/reconciliation/runs", json=body, headers=customer_headers).status_code == 403
    assert client.get("/admin/reconciliation/runs", headers=customer_headers).status_code == 403
    assert client.post("/admin/reconciliation/runs", json={**body, "totp": "000000"}, headers=admin_headers).status_code == 403
    assert client.get("/admin/reconciliation/runs", headers=admin_headers).status_code == 403

    created = client.post("/admin/reconciliation/runs", json=body, headers=admin_headers)
    assert created.status_code == 200, created.text
    assert created.json()["discrepancies"] == 1
    replay = client.post("/admin/reconciliation/runs", json=body, headers=admin_headers)
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True
    read_headers = {**admin_headers, "X-Booker-TOTP": totp_code()}
    runs = client.get("/admin/reconciliation/runs", headers=read_headers)
    queue = client.get("/admin/reconciliation/discrepancies", headers=read_headers)
    assert runs.status_code == queue.status_code == 200
    assert len(runs.json()["items"]) == len(queue.json()["items"]) == 1
    discrepancy_id = queue.json()["items"][0]["id"]
    assert "details_json" not in queue.json()["items"][0]
    detail_url = f"/admin/reconciliation/discrepancies/{discrepancy_id}"
    assert client.get(detail_url, headers=customer_headers).status_code == 403
    no_totp_admin = _promote_admin(client, "reconciliation-read-no-totp@booker.test")
    no_totp_headers = auth_header(no_totp_admin["token"])
    assert client.get("/admin/reconciliation/discrepancies", headers=no_totp_headers).status_code == 403
    assert client.get(detail_url, headers=no_totp_headers).status_code == 403
    assert client.get(detail_url, headers=admin_headers).status_code == 403
    assert client.get(
        "/admin/reconciliation/discrepancies/missing", headers=read_headers
    ).status_code == 404
    detail = client.get(detail_url, headers=read_headers)
    assert detail.status_code == 200
    assert detail.json()["movement"]["amount_rub"] == facts["amount_rub"]

    with client.app.state.SessionLocal() as db:
        payment = db.get(Payment, facts["payment_id"])
        assert db.get(Booking, payment.booking_id).payout_blocked is True
        alerts = db.query(EmailOutbox).filter_by(template="reconciliation_p0").all()
        assert len(alerts) == 1
        assert facts["provider_reference"] not in alerts[0].body

    resolve_url = f"/admin/reconciliation/discrepancies/{discrepancy_id}/resolve"
    decision = {"resolution": "Сверено вручную по независимому акту", "totp": totp_code()}
    assert client.post(resolve_url, json=decision, headers=customer_headers).status_code == 403
    assert client.post(resolve_url, json=decision, headers=no_totp_headers).status_code == 403
    assert client.post(resolve_url, json={**decision, "totp": "000000"}, headers=admin_headers).status_code == 403
    assert client.post(
        "/admin/reconciliation/discrepancies/missing/resolve",
        json=decision, headers=admin_headers,
    ).status_code == 404
    resolved = client.post(resolve_url, json=decision, headers=admin_headers)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert client.post(resolve_url, json=decision, headers=admin_headers).json()["idempotent"] is True
    assert client.post(resolve_url, json={**decision, "resolution": "Другая причина"}, headers=admin_headers).status_code == 409
    with client.app.state.SessionLocal() as db:
        payment = db.get(Payment, facts["payment_id"])
        assert db.get(Booking, payment.booking_id).payout_blocked is False
        row = db.get(ReconciliationDiscrepancy, discrepancy_id)
        assert row.resolved_by_user_id == admin["user_id"]
        assert db.query(AuditLog).filter_by(action="reconciliation.discrepancy_resolved").count() == 1


def test_reconciliation_input_limits_and_report_conflict_alert(client):
    _, facts = _captured(client)
    admin = _promote_admin(client, "reconciliation-limits@booker.test", TEST_TOTP_SECRET)
    headers = auth_header(admin["token"])
    body = _payload(facts)
    assert client.post("/admin/reconciliation/runs", json={**body, "extra": "secret"}, headers=headers).status_code == 422
    assert client.post("/admin/reconciliation/runs", json={**body, "entries": [_report_row(facts)] * 501}, headers=headers).status_code == 422
    assert client.post("/admin/reconciliation/runs", json=body, headers=headers).status_code == 200
    conflicting = _payload(facts, entries=[_report_row(facts, amount_rub=facts["amount_rub"] + 1)])
    assert client.post("/admin/reconciliation/runs", json=conflicting, headers=headers).status_code == 409
    with client.app.state.SessionLocal() as db:
        assert db.query(ReconciliationDiscrepancy).filter_by(kind="report_hash_conflict").count() == 1
        assert db.query(EmailOutbox).filter_by(template="reconciliation_p0").count() == 1


def test_reconciliation_admin_must_enable_totp_even_when_optional_globally(client):
    _, facts = _captured(client)
    admin = _promote_admin(client, "reconciliation-no-totp@booker.test")
    assert client.post("/admin/reconciliation/runs", json=_payload(facts), headers=auth_header(admin["token"])).status_code == 403


def test_closed_hash_conflict_reappears_as_new_open_alert(client):
    _, facts = _captured(client)
    admin = _promote_admin(client, "reconciliation-repeat@booker.test", TEST_TOTP_SECRET)
    headers = auth_header(admin["token"])
    assert client.post("/admin/reconciliation/runs", json=_payload(facts), headers=headers).status_code == 200
    conflict = _payload(facts, entries=[_report_row(facts, amount_rub=facts["amount_rub"] + 1)])
    assert client.post("/admin/reconciliation/runs", json=conflict, headers=headers).status_code == 409
    with client.app.state.SessionLocal() as db:
        first = db.query(ReconciliationDiscrepancy).filter_by(kind="report_hash_conflict").one()
        first_id = first.id
    response = client.post(
        f"/admin/reconciliation/discrepancies/{first_id}/resolve",
        json={"resolution": "Проверено по документу партнёра", "totp": totp_code()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert client.post("/admin/reconciliation/runs", json=conflict, headers=headers).status_code == 409
    with client.app.state.SessionLocal() as db:
        rows = db.query(ReconciliationDiscrepancy).filter_by(kind="report_hash_conflict").all()
        assert len(rows) == 2
        assert {row.status for row in rows} == {"open", "resolved"}
        assert db.query(EmailOutbox).filter_by(template="reconciliation_p0").count() == 2
        payment = db.get(Payment, facts["payment_id"])
        assert db.get(Booking, payment.booking_id).payout_blocked is True


def test_another_merchant_run_cannot_clear_existing_booking_block(client):
    _, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        first = _run(db, facts, entries=[])
        db.commit()
        assert first["discrepancies"] == 1
        payment = db.get(Payment, facts["payment_id"])
        booking_id = payment.booking_id
        payment.provider_merchant = "second-merchant"
        db.commit()
        second = import_reconciliation_report(
            db,
            provider="stub",
            merchant="second-merchant",
            report_id="second-merchant-report",
            period_start=facts["movement_at"] + timedelta(days=1),
            period_end=facts["movement_at"] + timedelta(days=2),
            entries=[],
        )
        db.commit()
        assert second["status"] == "completed"
        assert db.get(Booking, booking_id).payout_blocked is True
