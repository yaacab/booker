from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from booker_api.db import Base, get_db
from booker_api.main import app
from booker_api.rate_limit import (
    admin_sensitive_limiter,
    analytics_limiter,
    auth_limiter,
    messaging_limiter,
    upload_limiter,
    webhook_limiter,
)


@pytest.fixture(autouse=True)
def explicit_test_payment_provider(monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "payment_provider", "stub")
    monkeypatch.setattr(settings, "payment_allow_stub", True)


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    from booker_api.db import ensure_sqlite_columns

    ensure_sqlite_columns(eng)
    return eng


@pytest.fixture()
def SessionLocal(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    auth_limiter.reset()
    webhook_limiter.reset()
    analytics_limiter.reset()
    upload_limiter.reset()
    admin_sensitive_limiter.reset()
    messaging_limiter.reset()
    yield
    auth_limiter.reset()
    webhook_limiter.reset()
    analytics_limiter.reset()
    upload_limiter.reset()
    admin_sensitive_limiter.reset()
    messaging_limiter.reset()


@pytest.fixture()
def client(SessionLocal) -> Generator[TestClient, None, None]:
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


def contract_otps(SessionLocal, contract_id: str) -> dict[str, str]:
    """OTP codes are server-side only; tests read them from DB."""
    from booker_api.models import Contract

    db = SessionLocal()
    try:
        row = db.get(Contract, contract_id)
        assert row is not None
        return {"otp_customer": row.otp_customer, "otp_supplier": row.otp_supplier}
    finally:
        db.close()


def register(client: TestClient, email: str, name: str = "User") -> dict:
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password1",
            "full_name": name,
            "phone": "+79000000000",
            "accept_offer": True,
            "accept_privacy": True,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def activate_venue(client: TestClient, venue_id: str, *, tariff_rub: int = 100_000) -> None:
    """Make an owner-created venue satisfy the contractual publication gate.

    Tests that exercise public discovery, matching, comparison or compatibility
    must opt into a complete active profile instead of relying on the old
    implicit ``published`` default.
    """
    from datetime import timedelta

    from booker_api.models import (
        AvailabilitySlot,
        Venue,
        VenueHall,
        VenuePhoto,
        VenueTariff,
    )
    from booker_api.security import now

    db = client.app.state.SessionLocal()
    try:
        venue = db.get(Venue, venue_id)
        assert venue is not None
        venue.moderation_status = "published"
        venue.is_claimed = True
        venue.verified = True
        venue.partnership_status = "verified"
        venue.availability_mode = "owner"
        venue.listing_origin = "owner"
        venue.source_type = "owner_submission"
        venue.verified_at = venue.verified_at or now()
        venue.last_verified_at = venue.last_verified_at or now()

        if db.query(VenueTariff).filter(VenueTariff.venue_id == venue_id).first() is None:
            db.add(
                VenueTariff(
                    venue_id=venue_id,
                    title="Тестовый тариф",
                    honorarium_rub=tariff_rub,
                )
            )

        if db.query(VenuePhoto).filter(VenuePhoto.venue_id == venue_id).first() is None:
            photo_url = f"/test-fixtures/venues/{venue_id}.jpg"
            db.add(
                VenuePhoto(
                    venue_id=venue_id,
                    photo_url=photo_url,
                    photo_source_url=f"https://bukergo.ru{photo_url}",
                    photo_rights_status="official_permission",
                )
            )

        hall = db.query(VenueHall).filter(VenueHall.venue_id == venue_id).first()
        assert hall is not None
        coverage_end = now() + timedelta(days=35)
        latest = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_type == "hall",
                AvailabilitySlot.resource_id == hall.id,
            )
            .order_by(AvailabilitySlot.ends_at.desc())
            .first()
        )
        if latest is None or latest.ends_at < coverage_end:
            db.add(
                AvailabilitySlot(
                    resource_type="hall",
                    resource_id=hall.id,
                    starts_at=coverage_end - timedelta(hours=4),
                    ends_at=coverage_end,
                    status="open",
                )
            )
        db.commit()
    finally:
        db.close()


def grant_team_plan(client, org_id):
    """Existing team/RBAC scenarios run on the paid tier that permits their team.

    Use only in scenarios whose subject is access control rather than plan capacity.
    Capacity tests must exercise the real default plan without this fixture helper.
    """
    from datetime import timedelta

    from booker_api.models import Organization, Subscription
    from booker_api.security import now

    session = client.app.dependency_overrides[get_db]()
    db = next(session)
    try:
        org = db.get(Organization, org_id)
        row = db.query(Subscription).filter_by(organization_id=org_id).one_or_none()
        if row is None:
            row = Subscription(organization_id=org_id)
            db.add(row)
        row.plan_code = 'customer_business' if org.kind == 'customer' else f'{org.kind}_premium'
        row.billing_period = 'monthly'; row.status = 'active'; row.starts_at = now()-timedelta(days=1)
        row.current_period_end = now()+timedelta(days=30)
        db.commit()
    finally:
        session.close()
