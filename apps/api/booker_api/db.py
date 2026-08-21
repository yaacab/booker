from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from booker_api.config import settings


class Base(DeclarativeBase):
    pass


def ensure_sqlite_columns(bind) -> None:
    if not str(bind.url).startswith("sqlite"):
        return
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "active_organization_id" not in cols:
            with bind.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN active_organization_id VARCHAR(36)"))
    if "availability_slots" in tables:
        slot_cols = {c["name"] for c in inspector.get_columns("availability_slots")}
        if "buffer_before_min" not in slot_cols:
            with bind.begin() as conn:
                conn.execute(text("ALTER TABLE availability_slots ADD COLUMN buffer_before_min INTEGER DEFAULT 0"))
        if "buffer_after_min" not in slot_cols:
            with bind.begin() as conn:
                conn.execute(text("ALTER TABLE availability_slots ADD COLUMN buffer_after_min INTEGER DEFAULT 0"))
    if "requests" in tables:
        request_cols = {c["name"] for c in inspector.get_columns("requests")}
        if "requirement_id" not in request_cols:
            with bind.begin() as conn:
                conn.execute(text("ALTER TABLE requests ADD COLUMN requirement_id VARCHAR(36)"))


def make_engine(url: str | None = None):
    db_url = url or settings.database_url
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, connect_args=connect_args, future=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_schema(bind=None) -> None:
    target = bind or engine
    Base.metadata.create_all(bind=target)
    ensure_sqlite_columns(target)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
