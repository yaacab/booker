from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from booker_api.db import Base, get_db
from booker_api.main import app
from booker_api.rate_limit import auth_limiter, webhook_limiter


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
    yield
    auth_limiter.reset()
    webhook_limiter.reset()


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
