"""Email proof is separate from legal acceptance, password reset, and TOTP."""

import re
import secrets
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from booker_api.config import settings
from booker_api.db import ensure_sqlite_columns
from booker_api.models import AuditLog, EmailOutbox, EmailVerificationChallenge, User
from booker_api.notifications.outbox import TransientEmail
from booker_api.routers.identity import _email_verification_hash
from booker_api.security import now
from tests.conftest import auth_header, register


def _capture(monkeypatch, *, success=True):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.example.test")
    monkeypatch.setattr("booker_api.routers.identity._email_gate_enabled", lambda: True)
    sent = []

    def deliver(message):
        assert isinstance(message, TransientEmail)
        sent.append(message)
        return success, "sent" if success else "unavailable"

    monkeypatch.setattr("booker_api.notifications.transports.smtp._deliver", deliver)
    return sent


def _token(message):
    found = re.search(r"[#]verify=([A-Za-z0-9_-]+)", message.body)
    assert found is not None
    return found.group(1)


def test_new_account_needs_mailbox_proof_for_new_org_and_membership(
    client, SessionLocal, monkeypatch,
):
    sent = _capture(monkeypatch)
    owner = register(client, "verify-owner@booker.test")
    target = register(client, "verify-member@booker.test")
    assert owner["email_verification_delivery"] == target["email_verification_delivery"] == "sent"
    assert len(sent) == 2
    owner_headers = auth_header(owner["token"])
    assert client.post("/orgs", json={"name": "Blocked", "kind": "artist"},
                       headers=owner_headers).status_code == 403
    with SessionLocal() as db:
        assert db.query(EmailOutbox).filter_by(template="auth.email_verification").count() == 0
        rows = db.query(EmailVerificationChallenge).all()
        assert len(rows) == 2
        assert {_email_verification_hash(_token(message)) for message in sent} == {
            row.token_hash for row in rows
        }
        assert all(_token(sent[0]) not in row.payload for row in db.query(AuditLog).all())
        assert all(_token(sent[1]) not in row.payload for row in db.query(AuditLog).all())
    confirmed = client.post(
        "/auth/email-verification/confirm", json={"token": _token(sent[0])},
        headers=owner_headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"email_verified": True, "idempotent": False}
    assert client.post(
        "/auth/email-verification/confirm", json={"token": _token(sent[0])},
        headers=owner_headers,
    ).json() == {"email_verified": True, "idempotent": True}
    org = client.post("/orgs", json={"name": "Verified", "kind": "artist"},
                      headers=owner_headers)
    assert org.status_code == 200, org.text
    assert client.post(
        f"/orgs/{org.json()['id']}/members",
        json={"user_id": target["user_id"], "role": "viewer"},
        headers=owner_headers,
    ).status_code == 403
    assert client.post(
        "/auth/email-verification/confirm", json={"token": _token(sent[1])},
        headers=owner_headers,
    ).status_code == 409
    assert client.post(
        "/auth/email-verification/confirm", json={"token": _token(sent[1])},
        headers=auth_header(target["token"]),
    ).status_code == 200
    assert client.post(
        f"/orgs/{org.json()['id']}/members",
        json={"user_id": target["user_id"], "role": "viewer"},
        headers=owner_headers,
    ).status_code == 200


def test_failed_delivery_reissue_revokes_old_token_and_keeps_generic_reply(
    client, SessionLocal, monkeypatch,
):
    sent = _capture(monkeypatch, success=False)
    user = register(client, "verify-retry@booker.test")
    assert user["email_verification_delivery"] == "error"
    first = _token(sent[0])
    assert client.post("/auth/email-verification/request", json={
        "email": "unknown@booker.test", "password": "password1",
    }).json() == {"ok": True}
    assert client.post("/auth/email-verification/request", json={
        "email": "verify-retry@booker.test", "password": "incorrect",
    }).json() == {"ok": True}
    assert len(sent) == 1
    assert client.post("/auth/email-verification/request", json={
        "email": "verify-retry@booker.test", "password": "password1",
    }).json() == {"ok": True}
    second = _token(sent[1])
    assert first != second
    headers = auth_header(user["token"])
    assert client.post("/auth/email-verification/confirm", json={"token": first},
                       headers=headers).status_code == 409
    assert client.post("/auth/email-verification/confirm", json={"token": second},
                       headers=headers).status_code == 200
    with SessionLocal() as db:
        assert db.get(EmailVerificationChallenge, _email_verification_hash(first)).revoked_at
        assert db.query(EmailOutbox).filter_by(template="auth.email_verification").count() == 0


def test_missing_smtp_blocks_registration_before_creating_pending_account(
    client, SessionLocal, monkeypatch,
):
    monkeypatch.setattr("booker_api.routers.identity._email_gate_enabled", lambda: True)
    monkeypatch.setattr(settings, "email_provider", "disabled")
    pack = client.get("/legal/pack").json()
    response = client.post("/auth/register", json={
        "email": "no-smtp@booker.test", "password": "password1", "full_name": "No SMTP",
        "accept_offer": True, "accept_privacy": True, "accept_processing": True,
        "accepted_documents": [
            {key: doc[key] for key in ("key", "version", "content_hash")}
            for doc in pack["documents"] if doc["required"]
        ],
        "draft_test_acknowledgement": True,
    })
    assert response.status_code == 503
    assert client.post("/auth/email-verification/request", json={
        "email": "no-smtp@booker.test", "password": "password1",
    }).status_code == 503
    with SessionLocal() as db:
        assert db.query(User).filter_by(email="no-smtp@booker.test").count() == 0


def test_expired_proof_rejected_and_admin_insert_guarded(client, SessionLocal, monkeypatch):
    sent = _capture(monkeypatch)
    user = register(client, "verify-expired@booker.test")
    with SessionLocal() as db:
        db.get(EmailVerificationChallenge, _email_verification_hash(_token(sent[0]))).expires_at = (
            now() - timedelta(seconds=1)
        )
        db.commit()
    assert client.post("/auth/email-verification/confirm", json={"token": _token(sent[0])},
                       headers=auth_header(user["token"])).status_code == 409
    with SessionLocal() as db:
        db.add(User(email="admin-insert@booker.test", full_name="Admin", password_hash="hash",
                    is_platform_admin=True, email_verification_required_at=now()))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_invitation_cannot_grant_unverified_new_account(client, monkeypatch):
    sent = _capture(monkeypatch)
    owner = register(client, "verified-inviter@booker.test")
    recipient = register(client, "pending-invitee@booker.test")
    assert client.post("/auth/email-verification/confirm", json={"token": _token(sent[0])},
                       headers=auth_header(owner["token"])).status_code == 200
    monkeypatch.setattr(settings, "email_provider", "dev")
    invite_token = secrets.token_urlsafe(32)
    monkeypatch.setattr("booker_api.routers.identity.issue_invitation_token", lambda: invite_token)
    org = client.post("/orgs", json={"name": "Invite proof", "kind": "artist"},
                      headers=auth_header(owner["token"]))
    assert org.status_code == 200
    created = client.post(f"/orgs/{org.json()['id']}/invitations", json={
        "email": "pending-invitee@booker.test", "role": "viewer",
        "idempotency_key": "proof-invite-once",
    }, headers=auth_header(owner["token"]))
    assert created.status_code == 200, created.text
    recipient_headers = auth_header(recipient["token"])
    assert client.post("/organization-invitations/accept", json={"token": invite_token},
                       headers=recipient_headers).status_code == 403
    assert client.post("/auth/email-verification/confirm", json={"token": _token(sent[1])},
                       headers=recipient_headers).status_code == 200
    assert client.post("/organization-invitations/accept", json={"token": invite_token},
                       headers=recipient_headers).status_code == 200


def test_runtime_replaces_older_admin_proof_trigger(engine):
    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER users_admin_verified_email"))
        connection.execute(text(
            "CREATE TRIGGER users_admin_verified_email BEFORE UPDATE OF is_platform_admin "
            "ON users BEGIN SELECT 1; END"
        ))
    ensure_sqlite_columns(engine)
    with engine.connect() as connection:
        sql = connection.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='users_admin_verified_email'"
        )).scalar_one()
    assert "email_verified_at" in sql
    assert "email_verification_required_at" in sql


def test_legacy_user_not_falsely_verified_and_new_admin_promotion_requires_proof(
    client, SessionLocal, monkeypatch,
):
    legacy = register(client, "legacy-mail@booker.test")
    with SessionLocal() as db:
        row = db.get(User, legacy["user_id"])
        assert row.email_verified_at is None
        assert row.email_verification_required_at is None
    sent = _capture(monkeypatch)
    assert client.get("/me", headers=auth_header(legacy["token"])).json()[
        "email_verification_required"
    ] is True
    assert client.post("/orgs", json={"name": "Legacy new grant", "kind": "artist"},
                       headers=auth_header(legacy["token"])).status_code == 403
    assert client.post("/auth/email-verification/request", json={
        "email": "legacy-mail@booker.test", "password": "password1",
    }).json() == {"ok": True}
    assert client.post("/auth/email-verification/confirm", json={"token": _token(sent[0])},
                       headers=auth_header(legacy["token"])).status_code == 200
    assert client.get("/me", headers=auth_header(legacy["token"])).json()[
        "email_verification_required"
    ] is False
    assert client.post("/orgs", json={"name": "Legacy proved", "kind": "artist"},
                       headers=auth_header(legacy["token"])).status_code == 200
    fresh = register(client, "new-admin-mail@booker.test")
    with SessionLocal() as db:
        row = db.get(User, fresh["user_id"])
        row.is_platform_admin = True
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    assert client.post("/auth/email-verification/confirm", json={"token": _token(sent[1])},
                       headers=auth_header(fresh["token"])).status_code == 200
    with SessionLocal() as db:
        row = db.get(User, fresh["user_id"])
        row.is_platform_admin = True
        db.commit()


def test_legacy_direct_admin_promotion_requires_proof_but_existing_admin_remains_usable(
    client, SessionLocal,
):
    legacy = register(client, "legacy-sql-admin@booker.test")
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE users SET is_platform_admin = 1 WHERE id = :id"),
                {"id": legacy["user_id"]},
            )
            db.commit()
        db.rollback()
        row = db.get(User, legacy["user_id"])
        assert row.is_platform_admin is False
        row.email_verified_at = now()
        row.is_platform_admin = True
        db.commit()
        row.full_name = "Existing verified admin"
        db.commit()


def test_existing_unverified_admin_survives_runtime_guard_adoption(client, SessionLocal):
    legacy = register(client, "legacy-existing-admin@booker.test")
    with SessionLocal() as db:
        # Simulate a pre-migration admin row on a disposable test database.
        db.execute(text("DROP TRIGGER users_admin_verified_email"))
        db.execute(
            text("UPDATE users SET is_platform_admin = 1 WHERE id = :id"),
            {"id": legacy["user_id"]},
        )
        db.commit()
        bind = db.get_bind()
    ensure_sqlite_columns(bind)
    with SessionLocal() as db:
        row = db.get(User, legacy["user_id"])
        assert row.email_verified_at is None
        assert row.email_verification_required_at is None
        assert row.is_platform_admin is True
        db.execute(
            text("UPDATE users SET is_platform_admin = 1 WHERE id = :id"),
            {"id": legacy["user_id"]},
        )
        db.commit()
