from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from booker_api.db import Base, enable_sqlite_foreign_keys, get_db
from booker_api.main import app
from booker_api.rate_limit import (
    admin_sensitive_limiter,
    analytics_limiter,
    auth_limiter,
    claim_limiter,
    messaging_limiter,
    otp_limiter,
    request_creation_limiter,
    support_agent_limiter,
    support_creation_limiter,
    upload_limiter,
    webhook_limiter,
)


@pytest.fixture()
def engine():
    eng = enable_sqlite_foreign_keys(
        create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
    )
    Base.metadata.create_all(bind=eng)
    from booker_api.db import ensure_sqlite_columns
    from booker_api.legal_registry import seed_draft_versions

    ensure_sqlite_columns(eng)
    with sessionmaker(bind=eng, future=True)() as db:
        seed_draft_versions(db)
        db.commit()
    return eng


@pytest.fixture()
def SessionLocal(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    auth_limiter.reset()
    claim_limiter.reset()
    webhook_limiter.reset()
    analytics_limiter.reset()
    upload_limiter.reset()
    admin_sensitive_limiter.reset()
    messaging_limiter.reset()
    otp_limiter.reset()
    request_creation_limiter.reset()
    support_agent_limiter.reset()
    support_creation_limiter.reset()
    yield
    auth_limiter.reset()
    claim_limiter.reset()
    webhook_limiter.reset()
    analytics_limiter.reset()
    upload_limiter.reset()
    admin_sensitive_limiter.reset()
    messaging_limiter.reset()
    otp_limiter.reset()
    request_creation_limiter.reset()
    support_agent_limiter.reset()
    support_creation_limiter.reset()


@pytest.fixture()
def client(SessionLocal, monkeypatch) -> Generator[TestClient, None, None]:
    from booker_api import contract_ack
    from booker_api.routers import payments

    original_challenge = contract_ack.new_challenge
    issued_test_codes: dict[str, str] = {}
    SessionLocal._issued_contract_codes = issued_test_codes

    def capture_challenge():
        code, digest, expires_at = original_challenge()
        issued_test_codes[digest] = code
        return code, digest, expires_at

    monkeypatch.setattr(payments, "new_challenge", capture_challenge)
    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    app.state.SessionLocal = SessionLocal
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def contract_otps(
    SessionLocal,
    contract_id: str,
    *,
    actor_user_id: str | None = None,
) -> dict[str, str]:
    """Read only test-captured codes; the database stores salted hashes."""
    from booker_api.models import ContractChallenge

    db = SessionLocal()
    try:
        rows = (
            db.query(ContractChallenge)
            .filter_by(contract_id=contract_id)
            .order_by(ContractChallenge.expires_at, ContractChallenge.id)
            .all()
        )
        captured = getattr(SessionLocal, "_issued_contract_codes", {})
        result: dict[str, str] = {}
        for row in rows:
            if actor_user_id is not None and row.actor_user_id != actor_user_id:
                continue
            if row.otp_hash in captured:
                result[f"otp_{row.side}"] = captured[row.otp_hash]
        return result
    finally:
        db.close()


def register(client: TestClient, email: str, name: str = "User") -> dict:
    pack = client.get("/legal/pack").json()
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password1",
            "full_name": name,
            "phone": "+79000000000",
            "accept_offer": True,
            "accept_privacy": True,
            "accept_processing": True,
            "accepted_documents": [
                {k: doc[k] for k in ("key", "version", "content_hash")}
                for doc in pack["documents"] if doc["required"]
            ],
            "draft_test_acknowledgement": pack["acceptance_effect"] == "test_acknowledgement",
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def publish_artist(client: TestClient, owner: dict, artist_id: str, *, add_tariff: bool = True) -> None:
    """Complete explicit publication evidence for a fictional test artist."""
    from booker_api.models import Artist

    db = client.app.state.SessionLocal()
    try:
        row = db.get(Artist, artist_id)
        assert row is not None
        row.verified = True
        row.verified_status = "approved"
        db.commit()
    finally:
        db.close()
    headers = auth_header(owner["token"])
    if add_tariff:
        res = client.post(
            f"/artists/{artist_id}/tariffs",
            json={"title": "Тестовый тариф", "honorarium_rub": 100000, "hours": 2},
            headers=headers,
        )
        assert res.status_code == 200, res.text
    through = datetime.now(timezone.utc) + timedelta(days=90)
    evidence = client.put(
        f"/artists/{artist_id}/publication-evidence",
        json={
            "media_url": "/design/puzzle-dj.png",
            "media_source_url": "/design/puzzle-dj.png",
            "media_rights_status": "owned",
            "rights_attested": True,
            "calendar_confirmed_through": through.isoformat(),
        },
        headers=headers,
    )
    assert evidence.status_code == 200, evidence.text
    enabled = client.put(
        f"/artists/{artist_id}/publication",
        json={"enabled": True, "state_version": 0},
        headers=headers,
    )
    assert enabled.status_code == 200, enabled.text


def publish_venue(client: TestClient, owner: dict, venue_id: str, *, add_tariff: bool = True) -> None:
    """Complete explicit publication evidence for a fictional test venue."""
    from booker_api.models import Venue

    db = client.app.state.SessionLocal()
    try:
        row = db.get(Venue, venue_id)
        assert row is not None
        row.verified = True
        row.verified_status = "approved"
        row.moderation_status = "published"
        row.is_claimed = True
        db.commit()
    finally:
        db.close()
    headers = auth_header(owner["token"])
    if add_tariff:
        res = client.post(
            f"/venues/{venue_id}/tariffs",
            json={"title": "Тестовая аренда", "honorarium_rub": 200000, "hours": 4},
            headers=headers,
        )
        assert res.status_code == 200, res.text
    photo = client.put(
        f"/venues/{venue_id}/photos",
        json={
            "photo_url": "/design/puzzle-venue.png",
            "photo_source_url": "/design/puzzle-venue.png",
            "photo_rights_status": "owned",
            "rights_attested": True,
            "sort_order": 0,
        },
        headers=headers,
    )
    assert photo.status_code == 200, photo.text
    through = datetime.now(timezone.utc) + timedelta(days=90)
    evidence = client.put(
        f"/venues/{venue_id}/publication-evidence",
        json={"calendar_confirmed_through": through.isoformat()},
        headers=headers,
    )
    assert evidence.status_code == 200, evidence.text
    enabled = client.put(
        f"/venues/{venue_id}/publication",
        json={"enabled": True, "state_version": 0},
        headers=headers,
    )
    assert enabled.status_code == 200, enabled.text
