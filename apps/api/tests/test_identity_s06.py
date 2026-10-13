import hashlib
import re
import smtplib
from datetime import timedelta

from fastapi.testclient import TestClient

from booker_api.config import settings
from booker_api.models import AuditLog, EmailOutbox, PasswordResetToken, User
from booker_api.notifications.outbox import (
    TransientEmail,
    _deliver,
    enqueue_email,
    retry_pending_outbox,
)
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code

BOOTSTRAP_TOTP_SECRET = "QZJN7AZ6IO7MCPYTT6ZE6ZPHFFIPMKE5"
NEW_TOTP_SECRET = "5MCLMV2DJV7ZVQURFZSCELPTE4RZLYXQ"


def _promote_admin(client, email: str, totp: str | None = None) -> dict:
    """The admin fixture represents an operator who already proved the mailbox."""
    user = register(client, email, "Админ")
    with client.app.state.SessionLocal() as db:
        row = db.get(User, user["user_id"])
        row.email_verified_at = now()
        row.is_platform_admin = True
        if totp:
            row.totp_enabled = True
            row.totp_secret = totp
        db.commit()
    return user


def _capture_admin_proofs(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "in_app_provider", "disabled")
    messages = []

    def capture(message):
        assert isinstance(message, TransientEmail)
        if not message.idempotency_key.startswith("auth.email_verification:"):
            messages.append(message)
        return True, "sent"

    monkeypatch.setattr("booker_api.notifications.transports.smtp._deliver", capture)
    return messages


def _admin_proof(message: TransientEmail) -> str:
    match = re.search(r"настройки второго фактора:\n([A-Za-z0-9_-]+)\n", message.body)
    assert match is not None
    return match.group(1)


def _reset_token(message: TransientEmail) -> str:
    match = re.search(r"[?]reset=([A-Za-z0-9_-]+)", message.body)
    assert match is not None
    return match.group(1)


def test_recover_sends_each_new_token_after_commit_without_outbox_secret(
    client, SessionLocal, monkeypatch,
):
    user = register(client, "reset-rotation@booker.test")
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "in_app_provider", "disabled")
    delivered = []

    def fake_deliver(message):
        assert isinstance(message, TransientEmail)
        raw = _reset_token(message)
        with SessionLocal() as db:
            assert db.get(PasswordResetToken, hashlib.sha256(raw.encode()).hexdigest())
            assert db.query(EmailOutbox).filter_by(template="auth.password_reset").count() == 0
        delivered.append(raw)
        return True, "sent"

    monkeypatch.setattr("booker_api.notifications.transports.smtp._deliver", fake_deliver)
    for _ in range(2):
        response = client.post("/auth/recover", json={"email": "reset-rotation@booker.test"})
        assert response.status_code == 200
    assert len(delivered) == 2
    assert delivered[0] != delivered[1]
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).filter_by(user_id=user["user_id"]).count() == 2
        assert db.query(EmailOutbox).filter_by(template="auth.password_reset").count() == 0
        events = db.query(AuditLog).filter_by(action="notification.email").all()
        assert len(events) == 2
        for event in events:
            assert all(raw not in event.payload for raw in delivered)
    changed = client.post(
        "/auth/recover/confirm",
        json={"token": delivered[1], "password": "new-password123"},
    )
    assert changed.status_code == 200
    assert client.post(
        "/auth/recover/confirm", json={"token": delivered[0], "password": "again-password123"},
    ).status_code == 400


def test_failed_reset_delivery_can_be_reissued_without_persisting_secret(
    client, SessionLocal, monkeypatch,
):
    register(client, "reset-retry@booker.test")
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "in_app_provider", "disabled")
    attempted = []

    def fake_deliver(message):
        attempted.append(_reset_token(message))
        return (len(attempted) == 2), "unavailable"

    monkeypatch.setattr("booker_api.notifications.transports.smtp._deliver", fake_deliver)
    for _ in range(2):
        assert client.post("/auth/recover", json={"email": "reset-retry@booker.test"}).status_code == 200
    assert len(attempted) == 2
    assert attempted[0] != attempted[1]
    with SessionLocal() as db:
        assert db.query(EmailOutbox).filter_by(template="auth.password_reset").count() == 0


def test_smtp_rejection_is_a_delivery_failure_without_secret_in_error(monkeypatch):
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.example.test")

    class RejectingSmtp:
        def __init__(self, *args, **kwargs):
            raise smtplib.SMTPException("rejected")

    monkeypatch.setattr("booker_api.notifications.outbox.smtplib.SMTP", RejectingSmtp)
    ok, detail = _deliver(TransientEmail("a@example.test", "Reset", "secret-reset-link"))
    assert ok is False
    assert detail == "SMTPException:rejected"
    assert "secret-reset-link" not in detail


def test_legacy_reset_outbox_is_scrubbed_and_never_retried(client, SessionLocal, monkeypatch):
    register(client, "reset-legacy@booker.test")
    with SessionLocal() as db:
        db.add(EmailOutbox(
            idempotency_key="legacy-reset-1",
            recipient_email="reset-legacy@booker.test",
            subject="Old link",
            body="secret-old-reset-link",
            template="auth.password_reset",
            entity_type="user",
            entity_id="legacy",
            status="failed",
        ))
        db.commit()
    monkeypatch.setattr("booker_api.notifications.outbox._deliver", lambda row: (_ for _ in ()).throw(
        AssertionError("historical reset message was sent")))
    with SessionLocal() as db:
        result = retry_pending_outbox(db)
        assert result["processed"] == 0
        row = db.query(EmailOutbox).filter_by(idempotency_key="legacy-reset-1").one()
        assert row.body == ""
        assert row.status == "cancelled"
        assert row.attempts == 0


def test_outbox_rejects_new_persisted_authentication_proofs(SessionLocal):
    with SessionLocal() as db:
        for template in ("auth.password_reset", "auth.admin_totp_proof", "auth.email_verification"):
            try:
                enqueue_email(
                    db, idempotency_key=f"proof-{template}", recipient_email="a@example.test",
                    subject="Proof", body="secret", template=template,
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"{template} outbox write was accepted")
            assert db.query(EmailOutbox).filter_by(template=template).count() == 0


def test_admin_bootstrap_with_enforced_2fa_needs_password_mail_and_live_code(
    client, SessionLocal, monkeypatch,
):
    messages = _capture_admin_proofs(monkeypatch)
    admin = _promote_admin(client, "totp-bootstrap@booker.test")
    ordinary = register(client, "totp-ordinary@booker.test")
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    headers = auth_header(admin["token"])
    assert client.post("/auth/login", json={
        "email": "totp-bootstrap@booker.test", "password": "password1",
    }).status_code == 403
    assert client.get("/admin/metrics", headers=headers).status_code == 403
    challenge = "/auth/admin-totp/challenge"
    wrong = client.post(challenge, json={
        "email": "totp-bootstrap@booker.test", "password": "wrong-password",
    })
    non_admin = client.post(challenge, json={
        "email": "totp-ordinary@booker.test", "password": "password1",
    })
    assert wrong.json() == non_admin.json() == {"ok": True}
    assert messages == []
    assert client.post(challenge, json={
        "email": "totp-bootstrap@booker.test", "password": "password1",
    }).json() == {"ok": True}
    assert len(messages) == 1
    assert messages[0].recipient_email == "totp-bootstrap@booker.test"
    proof = _admin_proof(messages[0])
    assert client.post("/auth/recover/confirm", json={
        "token": proof, "password": "attacker-password123",
    }).status_code == 400
    assert client.get("/admin/metrics", headers=headers).status_code == 403
    with SessionLocal() as db:
        from booker_api.routers.identity import _admin_totp_proof_hash

        assert db.get(PasswordResetToken, _admin_totp_proof_hash(proof))
        assert db.query(EmailOutbox).filter_by(template="auth.admin_totp_proof").count() == 0
        assert all(proof not in row.payload for row in db.query(AuditLog).all())
    confirm = "/auth/admin-totp/confirm"
    body = {
        "email": "totp-bootstrap@booker.test", "password": "password1",
        "proof": proof, "secret": BOOTSTRAP_TOTP_SECRET,
        "code": totp_code(BOOTSTRAP_TOTP_SECRET),
    }
    assert client.post(confirm, json={**body, "password": "wrong-password"}).status_code == 403
    assert client.post(confirm, json={**body, "proof": "a" * 43}).status_code == 403
    assert client.post(confirm, json={**body, "code": "000000"}).status_code == 403
    assert client.post(confirm, json={**body, "secret": TEST_TOTP_SECRET}).status_code == 422
    assert client.post(confirm, json={**body, "secret": "a" * 32}).status_code == 400
    assert client.post(confirm, json={**body, "secret": "A" * 32}).status_code == 400
    with SessionLocal() as db:
        assert db.get(User, admin["user_id"]).totp_enabled is False
        assert db.get(User, ordinary["user_id"]).totp_enabled is False
    enrolled = client.post(confirm, json=body)
    assert enrolled.status_code == 200
    assert enrolled.json()["totp_enabled"] is True
    assert len(set(enrolled.json()["recovery_codes"])) == 10
    assert client.get("/me", headers=headers).status_code == 401
    assert client.post(confirm, json=body).status_code == 403
    logged_in = client.post("/auth/login", json={
        "email": "totp-bootstrap@booker.test", "password": "password1",
        "totp": totp_code(BOOTSTRAP_TOTP_SECRET),
    })
    assert logged_in.status_code == 200
    assert client.get(
        "/admin/metrics", headers=auth_header(logged_in.json()["token"]),
    ).status_code == 200
    with SessionLocal() as db:
        assert all(BOOTSTRAP_TOTP_SECRET not in row.payload for row in db.query(AuditLog).all())
        assert all(BOOTSTRAP_TOTP_SECRET not in row.body for row in db.query(EmailOutbox).all())


def test_admin_rotation_requires_current_totp_and_revokes_all_sessions(client, monkeypatch):
    messages = _capture_admin_proofs(monkeypatch)
    admin = _promote_admin(client, "totp-recover@booker.test", totp=BOOTSTRAP_TOTP_SECRET)
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    logged_in = client.post("/auth/login", json={
        "email": "totp-recover@booker.test", "password": "password1",
        "totp": totp_code(BOOTSTRAP_TOTP_SECRET),
    })
    assert logged_in.status_code == 200
    session = logged_in.json()["token"]
    assert client.get("/admin/metrics", headers=auth_header(session)).status_code == 200
    assert client.post("/auth/admin-totp/challenge", json={
        "email": "totp-recover@booker.test", "password": "password1",
    }).json() == {"ok": True}
    assert messages == []
    body = {
        "email": "totp-recover@booker.test", "password": "password1",
        "totp": totp_code(BOOTSTRAP_TOTP_SECRET),
        "secret": NEW_TOTP_SECRET, "code": totp_code(NEW_TOTP_SECRET),
    }
    assert client.post("/auth/admin-totp/rotate", json={
        **body, "totp": "000000",
    }).status_code == 403
    assert client.post("/auth/admin-totp/rotate", json={
        **body, "secret": BOOTSTRAP_TOTP_SECRET,
        "code": totp_code(BOOTSTRAP_TOTP_SECRET),
    }).status_code == 400
    assert client.post("/auth/admin-totp/rotate", json={
        **body, "secret": "A" * 32,
    }).status_code == 400
    assert client.post("/auth/admin-totp/rotate", json=body).status_code == 200
    assert client.get("/me", headers=auth_header(admin["token"])).status_code == 401
    assert client.get("/me", headers=auth_header(session)).status_code == 401
    assert client.post("/auth/admin-totp/rotate", json=body).status_code == 403
    assert client.post("/auth/login", json={
        "email": "totp-recover@booker.test", "password": "password1",
        "totp": totp_code(BOOTSTRAP_TOTP_SECRET),
    }).status_code == 401
    assert client.post("/auth/login", json={
        "email": "totp-recover@booker.test", "password": "password1",
        "totp": totp_code(NEW_TOTP_SECRET),
    }).status_code == 200


def test_mailbox_and_password_cannot_replace_enabled_admin_totp(
    client, SessionLocal, monkeypatch,
):
    from booker_api.routers.identity import _admin_totp_proof_hash

    messages = _capture_admin_proofs(monkeypatch)
    admin = _promote_admin(client, "totp-mailbox-compromised@booker.test", totp=TEST_TOTP_SECRET)
    assert client.post("/auth/admin-totp/challenge", json={
        "email": "totp-mailbox-compromised@booker.test", "password": "password1",
    }).json() == {"ok": True}
    assert messages == []
    proof = "a" * 43
    with SessionLocal() as db:
        db.add(PasswordResetToken(
            token_hash=_admin_totp_proof_hash(proof),
            user_id=admin["user_id"],
            expires_at=now() + timedelta(minutes=10),
        ))
        db.commit()
    assert client.post("/auth/admin-totp/confirm", json={
        "email": "totp-mailbox-compromised@booker.test", "password": "password1",
        "proof": proof, "secret": NEW_TOTP_SECRET, "code": totp_code(NEW_TOTP_SECRET),
    }).status_code == 403
    assert client.post("/auth/admin-totp/rotate", json={
        "email": "totp-mailbox-compromised@booker.test", "password": "password1",
        "totp": "000000", "secret": NEW_TOTP_SECRET, "code": totp_code(NEW_TOTP_SECRET),
    }).status_code == 403
    with SessionLocal() as db:
        row = db.get(User, admin["user_id"])
        assert row.totp_secret == TEST_TOTP_SECRET
        assert row.totp_enabled is True


def test_admin_proof_is_bound_to_account_and_expires(client, SessionLocal, monkeypatch):
    from booker_api.routers.identity import _admin_totp_proof_hash

    messages = _capture_admin_proofs(monkeypatch)
    _promote_admin(client, "totp-proof-a@booker.test")
    _promote_admin(client, "totp-proof-b@booker.test")
    assert client.post("/auth/admin-totp/challenge", json={
        "email": "totp-proof-a@booker.test", "password": "password1",
    }).status_code == 200
    proof = _admin_proof(messages[-1])
    body = {
        "email": "totp-proof-b@booker.test", "password": "password1",
        "proof": proof, "secret": BOOTSTRAP_TOTP_SECRET,
        "code": totp_code(BOOTSTRAP_TOTP_SECRET),
    }
    assert client.post("/auth/admin-totp/confirm", json=body).status_code == 403
    with SessionLocal() as db:
        row = db.get(PasswordResetToken, _admin_totp_proof_hash(proof))
        row.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.post("/auth/admin-totp/confirm", json={
        **body, "email": "totp-proof-a@booker.test",
    }).status_code == 403


def test_admin_challenge_fails_closed_without_smtp(client, monkeypatch, SessionLocal):
    admin = _promote_admin(client, "totp-no-mail@booker.test")
    monkeypatch.setattr(settings, "email_provider", "disabled")
    monkeypatch.setattr(settings, "email_smtp_host", "")
    assert client.post("/auth/admin-totp/challenge", json={
        "email": "totp-no-mail@booker.test", "password": "password1",
    }).json() == {"ok": True}
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).filter_by(user_id=admin["user_id"]).count() == 0
        assert db.get(User, admin["user_id"]).totp_enabled is False


def test_admin_email_password_reset_requires_existing_totp(client, monkeypatch, SessionLocal):
    messages = _capture_admin_proofs(monkeypatch)
    unenrolled = _promote_admin(client, "totp-no-reset@booker.test")
    assert client.post("/auth/recover", json={
        "email": "totp-no-reset@booker.test",
    }).status_code == 200
    assert messages == []
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).filter_by(user_id=unenrolled["user_id"]).count() == 0

    _promote_admin(client, "totp-reset@booker.test", totp=TEST_TOTP_SECRET)
    assert client.post("/auth/recover", json={"email": "totp-reset@booker.test"}).status_code == 200
    reset_token = _reset_token(messages[-1])
    reset = {"token": reset_token, "password": "new-password123"}
    assert client.post("/auth/recover/confirm", json=reset).status_code == 403
    assert client.post("/auth/recover/confirm", json={**reset, "totp": "000000"}).status_code == 403
    assert client.post("/auth/recover/confirm", json={**reset, "totp": totp_code()}).status_code == 200
    assert client.post("/auth/login", json={
        "email": "totp-reset@booker.test", "password": "new-password123", "totp": totp_code(),
    }).status_code == 200


def test_api_startup_scrubs_legacy_plaintext_reset_outbox(SessionLocal, engine, monkeypatch):
    from booker_api import main
    from booker_api.routers import identity

    with SessionLocal() as db:
        db.add(EmailOutbox(
            idempotency_key="startup-legacy-reset",
            recipient_email="legacy@booker.test",
            subject="Old link",
            body="plaintext-reset-secret",
            template="auth.password_reset",
            entity_type="user",
            entity_id="legacy",
            status="sent",
        ))
        db.commit()
    monkeypatch.setattr(identity, "SessionLocal", SessionLocal)
    monkeypatch.setattr(main, "SessionLocal", SessionLocal)
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app), SessionLocal() as db:
        row = db.query(EmailOutbox).filter_by(idempotency_key="startup-legacy-reset").one()
        assert row.body == ""
        assert row.status == "sent"
