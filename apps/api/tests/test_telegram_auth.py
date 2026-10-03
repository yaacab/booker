"""Telegram proof is one-use and cannot skip Booker registration or staff TOTP."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pyotp

from booker_api.config import settings
from booker_api.models import ConsentEvent, PendingExternalAuth, SessionToken, User, UserIdentity

BOT_FIXTURE = "fixture-telegram-token-not-a-real-secret"


def _signed_data(user_id: int = 4711, *, query_id: str | None = None) -> str:
    fields = {
        "auth_date": str(int(datetime.now(timezone.utc).timestamp())),
        "user": json.dumps({"id": user_id, "first_name": "Ирина"},
                           ensure_ascii=False, separators=(",", ":")),
    }
    if query_id is not None:
        fields["query_id"] = query_id
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_FIXTURE.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def _legal_body(client) -> dict:
    pack = client.get("/legal/pack").json()
    required = [row for row in pack["documents"] if row["key"] in
                {"offer", "privacy", "consent_texts"}]
    return {
        "accept_offer": True, "accept_privacy": True, "accept_processing": True,
        "draft_test_acknowledgement": pack["acceptance_effect"] == "test_acknowledgement",
        "accepted_documents": [
            {key: row[key] for key in ("key", "version", "content_hash")}
            for row in required
        ],
    }


def test_telegram_requires_server_bot_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    assert client.post("/auth/telegram/prepare", json={"init_data": _signed_data()}).status_code == 503
    assert client.post("/auth/telegram/complete", json={"pending_token": "0" * 64}).status_code == 503


def test_first_login_requires_exact_legal_pack_then_consumes_once(client, SessionLocal, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    raw = _signed_data()
    prepared = client.post("/auth/telegram/prepare", json={"init_data": raw})
    assert prepared.status_code == 200, prepared.text
    pending_token = prepared.json()["pending_token"]
    assert "token" not in prepared.json()
    assert client.post("/auth/telegram/prepare", json={"init_data": raw}).json()[
        "pending_token"] == pending_token
    with SessionLocal() as db:
        assert db.query(SessionToken).count() == 0
        assert db.query(User).count() == 0
    missing = client.post("/auth/telegram/complete", json={"pending_token": pending_token})
    assert missing.status_code == 422
    stale = _legal_body(client)
    stale["accepted_documents"][0]["content_hash"] = "a" * 64
    assert client.post("/auth/telegram/complete", json={"pending_token": pending_token,
                                                         **stale}).status_code == 409
    completed = client.post("/auth/telegram/complete", json={"pending_token": pending_token,
                                                             **_legal_body(client)})
    assert completed.status_code == 200, completed.text
    assert completed.json()["onboarding_required"] is True
    assert completed.json()["token"]
    assert client.post("/auth/telegram/complete", json={"pending_token": pending_token,
                                                        **_legal_body(client)}).status_code == 409
    assert client.post("/auth/telegram/prepare", json={"init_data": raw}).status_code == 409
    with SessionLocal() as db:
        assert db.query(User).count() == 1
        user = db.query(User).one()
        assert user.email is None and user.password_hash is None
        assert db.query(UserIdentity).filter_by(provider="telegram", user_id=user.id).count() == 1
        assert {row.kind for row in db.query(ConsentEvent).all()} == {
            "offer", "privacy", "processing"
        }
        assert db.query(SessionToken).count() == 1
        pending = db.query(PendingExternalAuth).one()
        assert pending.consumed_at is not None
        assert raw not in repr(pending.__dict__)
        assert BOT_FIXTURE not in repr(pending.__dict__)


def test_existing_telegram_identity_login_does_not_create_second_user(
    client, SessionLocal, monkeypatch,
):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    first = client.post("/auth/telegram/prepare", json={"init_data": _signed_data()}).json()
    registered = client.post("/auth/telegram/complete", json={
        "pending_token": first["pending_token"], **_legal_body(client),
    }).json()
    second = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(query_id="fresh-proof"),
    })
    assert second.status_code == 200, second.text
    logged = client.post("/auth/telegram/complete", json={
        "pending_token": second.json()["pending_token"],
    })
    assert logged.status_code == 200, logged.text
    assert logged.json()["user_id"] == registered["user_id"]
    assert logged.json()["onboarding_required"] is False
    with SessionLocal() as db:
        assert db.query(User).count() == 1
        assert db.query(UserIdentity).count() == 1
        assert db.query(User).one().id == registered["user_id"]


def test_staff_identity_requires_booker_totp_before_session(client, SessionLocal, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    secret = pyotp.random_base32()
    with SessionLocal() as db:
        user = User(full_name="Оператор", email="operator@example.test",
                    password_hash=None, is_support_operator=True,
                    totp_enabled=True, totp_secret=secret,
                    email_verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()
        db.add(UserIdentity(user_id=user.id, provider="telegram", provider_subject="4711",
                            link_origin="explicit_link"))
        db.commit()
        user_id = user.id
    pending_token = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(),
    }).json()["pending_token"]
    assert client.post("/auth/telegram/complete", json={
        "pending_token": pending_token,
    }).status_code == 401
    with SessionLocal() as db:
        assert db.query(SessionToken).count() == 0
        assert db.query(PendingExternalAuth).one().consumed_at is None
    logged = client.post("/auth/telegram/complete", json={
        "pending_token": pending_token, "totp": pyotp.TOTP(secret).now(),
    })
    assert logged.status_code == 200, logged.text
    assert logged.json()["user_id"] == user_id
    assert logged.json()["is_support_operator"] is True
    with SessionLocal() as db:
        assert db.query(SessionToken).count() == 1
        assert db.query(SessionToken).one().admin_2fa_verified_at is not None


def test_expired_pending_proof_cannot_create_a_user(client, SessionLocal, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    pending_token = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(),
    }).json()["pending_token"]
    with SessionLocal() as db:
        row = db.query(PendingExternalAuth).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    result = client.post("/auth/telegram/complete", json={
        "pending_token": pending_token, **_legal_body(client),
    })
    assert result.status_code == 409
    with SessionLocal() as db:
        assert db.query(User).count() == 0
        assert db.query(SessionToken).count() == 0


def test_telegram_does_not_merge_with_existing_email_account(client, SessionLocal, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    with SessionLocal() as db:
        existing = User(full_name="Ирина", email="irina@example.test",
                        password_hash="local-hash")
        db.add(existing)
        db.commit()
        existing_id = existing.id
    pending_token = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(),
    }).json()["pending_token"]
    result = client.post("/auth/telegram/complete", json={
        "pending_token": pending_token, **_legal_body(client),
    })
    assert result.status_code == 200, result.text
    assert result.json()["user_id"] != existing_id
    with SessionLocal() as db:
        assert db.query(User).count() == 2
