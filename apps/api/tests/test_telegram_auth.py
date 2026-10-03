"""Telegram proof is one-use and cannot skip Booker registration or staff TOTP."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pyotp

from booker_api.config import settings
from booker_api.models import (
    ConsentEvent,
    PendingExternalAuth,
    SessionToken,
    User,
    UserIdentity,
    UserNotification,
)
from booker_api.security import hash_password, issue_token
from tests.conftest import auth_header

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


def _password_account(SessionLocal, *, staff: bool = False) -> tuple[str, str, str | None]:
    secret = pyotp.random_base32() if staff else None
    with SessionLocal() as db:
        user = User(full_name="Владелец", email="owner@example.test",
                    password_hash=hash_password("correct-password"),
                    is_support_operator=staff, totp_enabled=staff, totp_secret=secret,
                    email_verified_at=datetime.now(timezone.utc) if staff else None)
        db.add(user)
        db.flush()
        token = issue_token(db, user)
        db.commit()
        return user.id, token, secret


def test_explicit_link_requires_password_and_never_replaces_existing_user(
    client, SessionLocal, monkeypatch,
):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    user_id, token, _ = _password_account(SessionLocal)
    pending = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(),
    }).json()["pending_token"]
    link_url = "/me/identities/telegram/link"
    assert client.post(link_url, json={"pending_token": pending,
                                       "password": "correct-password"}).status_code == 401
    denied = client.post(link_url, headers=auth_header(token), json={
        "pending_token": pending, "password": "wrong-password",
    })
    assert denied.status_code == 403
    with SessionLocal() as db:
        assert db.query(PendingExternalAuth).one().consumed_at is None
    linked = client.post(link_url, headers=auth_header(token), json={
        "pending_token": pending, "password": "correct-password",
    })
    assert linked.status_code == 200, linked.text
    listing = client.get("/me/identities", headers=auth_header(token))
    assert listing.status_code == 200
    assert listing.json()["identities"][0]["provider"] == "telegram"
    assert "provider_subject" not in listing.text
    with SessionLocal() as db:
        assert db.query(User).count() == 1
        identity = db.query(UserIdentity).one()
        assert identity.user_id == user_id and identity.link_origin == "explicit_link"
        assert db.query(UserNotification).filter_by(template="security.identity_linked").count() == 1
    new_proof = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(query_id="after-link"),
    }).json()["pending_token"]
    logged = client.post("/auth/telegram/complete", json={"pending_token": new_proof})
    assert logged.status_code == 200 and logged.json()["user_id"] == user_id
    assert logged.json()["onboarding_required"] is False


def test_unlink_requires_remaining_password_login_and_revokes_other_sessions(
    client, SessionLocal, monkeypatch,
):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    user_id, token, _ = _password_account(SessionLocal)
    with SessionLocal() as db:
        db.add(UserIdentity(user_id=user_id, provider="telegram",
                            provider_subject="4711", link_origin="explicit_link"))
        another = issue_token(db, db.get(User, user_id))
        db.commit()
    url = "/me/identities/telegram/unlink"
    assert client.post(url, headers=auth_header(token), json={
        "password": "wrong-password",
    }).status_code == 403
    result = client.post(url, headers=auth_header(token), json={
        "password": "correct-password",
    })
    assert result.status_code == 200, result.text
    assert client.get("/me", headers=auth_header(another)).status_code == 401
    assert client.get("/me", headers=auth_header(token)).status_code == 200
    with SessionLocal() as db:
        assert db.query(UserIdentity).count() == 0
        assert db.query(UserNotification).filter_by(template="security.identity_unlinked").count() == 1
    # The old Telegram subject cannot reenter the former account implicitly.
    next_proof = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(query_id="after-unlink"),
    }).json()["pending_token"]
    assert client.post("/auth/telegram/complete", json={
        "pending_token": next_proof,
    }).status_code == 422


def test_external_only_account_cannot_unlink_its_last_working_login(
    client, SessionLocal, monkeypatch,
):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    pending = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(),
    }).json()["pending_token"]
    token = client.post("/auth/telegram/complete", json={
        "pending_token": pending, **_legal_body(client),
    }).json()["token"]
    result = client.post("/me/identities/telegram/unlink", headers=auth_header(token),
                         json={"password": "anything"})
    assert result.status_code == 403
    with SessionLocal() as db:
        assert db.query(UserIdentity).count() == 1


def test_staff_link_requires_booker_totp_and_operator_allowlist(
    client, SessionLocal, monkeypatch,
):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    user_id, token, secret = _password_account(SessionLocal, staff=True)
    pending = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(),
    }).json()["pending_token"]
    headers = auth_header(token)
    assert client.get("/me/identities", headers=headers).status_code == 200
    assert client.post("/me/identities/telegram/link", headers=headers, json={
        "pending_token": pending, "password": "correct-password",
    }).status_code == 403
    linked = client.post("/me/identities/telegram/link", headers=headers, json={
        "pending_token": pending, "password": "correct-password",
        "totp": pyotp.TOTP(secret).now(),
    })
    assert linked.status_code == 200, linked.text
    with SessionLocal() as db:
        assert db.query(UserIdentity).one().user_id == user_id


def test_link_rejects_telegram_subject_owned_by_another_account(
    client, SessionLocal, monkeypatch,
):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    first_id, _first_token, _ = _password_account(SessionLocal)
    with SessionLocal() as db:
        db.add(UserIdentity(user_id=first_id, provider="telegram",
                            provider_subject="4711", link_origin="explicit_link"))
        db.commit()
    with SessionLocal() as db:
        second = User(full_name="Другой", email="other@example.test",
                      password_hash=hash_password("second-password"))
        db.add(second)
        db.flush()
        second_token = issue_token(db, second)
        db.commit()
        second_id = second.id
    pending = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(),
    }).json()["pending_token"]
    response = client.post("/me/identities/telegram/link",
                           headers=auth_header(second_token), json={
                               "pending_token": pending, "password": "second-password",
                           })
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.query(UserIdentity).count() == 1
        assert db.query(UserIdentity).one().user_id == first_id
        assert db.query(User).count() == 2
        assert db.query(User).filter_by(id=second_id).one().email == "other@example.test"
        assert db.query(PendingExternalAuth).one().consumed_at is None


def test_link_rejects_second_telegram_identity_for_same_account(
    client, SessionLocal, monkeypatch,
):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_FIXTURE)
    user_id, token, _ = _password_account(SessionLocal)
    with SessionLocal() as db:
        db.add(UserIdentity(user_id=user_id, provider="telegram",
                            provider_subject="other-telegram-id", link_origin="explicit_link"))
        db.commit()
    pending = client.post("/auth/telegram/prepare", json={
        "init_data": _signed_data(),
    }).json()["pending_token"]
    response = client.post("/me/identities/telegram/link", headers=auth_header(token), json={
        "pending_token": pending, "password": "correct-password",
    })
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.query(UserIdentity).count() == 1
        assert db.query(PendingExternalAuth).one().consumed_at is None
