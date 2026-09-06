"""E13: external payment confirm by operator (not live provider)."""

from booker_api.config import settings
from booker_api.models import AuditLog, Payment
from tests.conftest import auth_header
from tests.test_admin import _promote_admin
from tests.test_payments import _awaiting_payment
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def test_confirm_external_payment_succeeds_and_audits(client, monkeypatch):
    """Stub≠PSP: external path is operator confirm + audit, not online acquiring."""
    monkeypatch.setattr(settings, "payment_provider", "external")
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", False)
    ctx = _awaiting_payment(client)

    SessionLocal = client.app.state.SessionLocal
    db = SessionLocal()
    try:
        pay = db.get(Payment, ctx["payment_id"])
        assert pay is not None
        assert pay.provider == "external"
        assert pay.status != "succeeded"
    finally:
        db.close()

    admin = _promote_admin(client, "ext-pay-admin@booker.test", totp=TEST_TOTP_SECRET)
    res = client.post(
        f"/admin/payments/{ctx['payment_id']}/confirm-external",
        params={"totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("payment_status") == "succeeded" or body.get("status") == "succeeded"

    db = SessionLocal()
    try:
        pay = db.get(Payment, ctx["payment_id"])
        assert pay is not None
        assert pay.status == "succeeded"
        audits = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "payment",
                AuditLog.entity_id == ctx["payment_id"],
                AuditLog.action == "payment.captured",
            )
            .all()
        )
        assert len(audits) >= 1
        assert audits[0].actor_user_id == admin["user_id"]
    finally:
        db.close()

    replay = client.post(
        f"/admin/payments/{ctx['payment_id']}/confirm-external",
        params={"totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert replay.status_code == 200
    assert replay.json().get("idempotent") is True or replay.json().get("status") == "succeeded"
