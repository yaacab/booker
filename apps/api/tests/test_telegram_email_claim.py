"""An external-only Telegram account earns organization access after mailbox proof."""

import re
from datetime import timedelta

from booker_api.config import settings
from booker_api.models import EmailOutbox, EmailVerificationChallenge, SessionToken, User
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_telegram_auth import BOT_FIXTURE, _legal_body, _signed_data


def _telegram_user(client, monkeypatch, *, user_id: int = 4711) -> tuple[str, str]:
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    pending = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(user_id),
    }).json()["pending_token"]
    result = client.post("/auth/telegram/complete", json={
        "pending_token": pending, **_legal_body(client),
    })
    assert result.status_code == 200, result.text
    return result.json()["token"], result.json()["user_id"]


def _mail_sink(monkeypatch) -> list[str]:
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.example.test")
    delivered: list[str] = []

    def capture(message):
        match = re.search(r"/verify-email#verify=([A-Za-z0-9_-]+)", message.body)
        assert match
        delivered.append(match.group(1))
        return True, "sent"

    monkeypatch.setattr("booker_api.notifications.transports.smtp._deliver", capture)
    return delivered


def test_verified_telegram_mailbox_unlocks_org_without_password(
    client, SessionLocal, monkeypatch,
):
    token, user_id = _telegram_user(client, monkeypatch)
    delivered = _mail_sink(monkeypatch)
    # Exercise the staging email policy without changing the separate
    # production rate-limit backend requirements of this local TestClient.
    monkeypatch.setattr("booker_api.routers.identity._email_gate_enabled", lambda: True)
    headers = auth_header(token)
    body = {"name": "Моя организация", "kind": "customer"}
    assert client.post("/orgs", headers=headers, json=body).status_code == 403
    claim = {"email": "telegram-owner@booker.test", "init_data": _signed_data()}
    requested = client.post("/me/email/telegram/request", headers=headers, json=claim)
    assert requested.status_code == 200, requested.text
    assert requested.json()["delivery"] == "sent"
    assert len(delivered) == 1
    assert client.post("/orgs", headers=headers, json=body).status_code == 403
    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user.email == claim["email"] and user.password_hash is None
        assert user.email_verified_at is None
        assert db.query(EmailOutbox).filter_by(template="auth.email_verification").count() == 0
        row = db.query(EmailVerificationChallenge).one()
        assert row.token_hash != delivered[0]
        sessions_before = db.query(SessionToken).count()
    confirmed = client.post("/auth/email-verification/external-confirm", json={
        "token": delivered[0],
    })
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"email_verified": True, "idempotent": False}
    with SessionLocal() as db:
        assert db.query(SessionToken).count() == sessions_before
    assert client.post("/auth/email-verification/external-confirm", json={
        "token": delivered[0],
    }).json() == {"email_verified": True, "idempotent": True}
    assert client.post("/orgs", headers=headers, json=body).status_code == 200
    assert client.post("/auth/login", json={
        "email": claim["email"], "password": "guessed",
    }).status_code == 401


def test_claim_requires_matching_telegram_and_never_merges_email(
    client, SessionLocal, monkeypatch,
):
    token, user_id = _telegram_user(client, monkeypatch)
    _mail_sink(monkeypatch)
    existing = register(client, "existing@booker.test")
    with SessionLocal() as db:
        # Historical addresses may have mixed case; never link by a case variant.
        db.get(User, existing["user_id"]).email = "Existing@Booker.Test"
        db.commit()
    headers = auth_header(token)
    endpoint = "/me/email/telegram/request"
    assert client.post(endpoint, headers=headers, json={
        "email": "new@booker.test", "init_data": _signed_data(9999),
    }).status_code == 403
    bad = _signed_data().replace("4711", "4712")
    assert client.post(endpoint, headers=headers, json={
        "email": "new@booker.test", "init_data": bad,
    }).status_code == 401
    assert client.post(endpoint, headers=headers, json={
        "email": "existing@booker.test", "init_data": _signed_data(),
    }).status_code == 409
    with SessionLocal() as db:
        assert db.get(User, user_id).email is None


def test_reissued_address_invalidates_old_mailbox_proof(
    client, SessionLocal, monkeypatch,
):
    token, user_id = _telegram_user(client, monkeypatch)
    delivered = _mail_sink(monkeypatch)
    headers = auth_header(token)
    endpoint = "/me/email/telegram/request"
    for address in ("first@booker.test", "second@booker.test"):
        result = client.post(endpoint, headers=headers, json={
            "email": address, "init_data": _signed_data(),
        })
        assert result.status_code == 200, result.text
    assert len(delivered) == 2 and delivered[0] != delivered[1]
    assert client.post("/auth/email-verification/external-confirm", json={
        "token": delivered[0],
    }).status_code == 409
    with SessionLocal() as db:
        assert db.get(User, user_id).email_verified_at is None
    assert client.post("/auth/email-verification/external-confirm", json={
        "token": delivered[1],
    }).status_code == 200
    assert client.post(endpoint, headers=headers, json={
        "email": "third@booker.test", "init_data": _signed_data(),
    }).status_code == 403


def test_expired_link_and_disabled_delivery_fail_closed(client, SessionLocal, monkeypatch):
    token, user_id = _telegram_user(client, monkeypatch)
    endpoint = "/me/email/telegram/request"
    headers = auth_header(token)
    claim = {"email": "owner@booker.test", "init_data": _signed_data()}
    assert client.post(endpoint, headers=headers, json=claim).status_code == 503
    with SessionLocal() as db:
        assert db.get(User, user_id).email is None
    delivered = _mail_sink(monkeypatch)
    assert client.post(endpoint, headers=headers, json=claim).status_code == 200
    with SessionLocal() as db:
        challenge = db.query(EmailVerificationChallenge).one()
        challenge.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.post("/auth/email-verification/external-confirm", json={
        "token": delivered[0],
    }).status_code == 409
    with SessionLocal() as db:
        assert db.get(User, user_id).email_verified_at is None
