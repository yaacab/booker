from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from booker_api.config import settings


class Base(DeclarativeBase):
    pass


def _add_column_if_missing(bind, table: str, column: str, ddl: str) -> None:
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column in cols:
        return
    with bind.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def ensure_missing_columns(bind) -> None:
    """Backfill columns on existing SQLite or Postgres tables. create_all does not ALTER."""
    dialect = bind.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        return
    _add_column_if_missing(bind, "users", "active_organization_id", "active_organization_id VARCHAR(36)")
    _add_column_if_missing(
        bind, "availability_slots", "buffer_before_min", "buffer_before_min INTEGER DEFAULT 0"
    )
    _add_column_if_missing(
        bind, "availability_slots", "buffer_after_min", "buffer_after_min INTEGER DEFAULT 0"
    )
    _add_column_if_missing(bind, "requests", "requirement_id", "requirement_id VARCHAR(36)")


def ensure_sqlite_columns(bind) -> None:
    ensure_missing_columns(bind)


def make_engine(url: str | None = None):
    db_url = url or settings.database_url
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, connect_args=connect_args, future=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_schema(bind=None) -> None:
    target = bind or engine
    Base.metadata.create_all(bind=target)
    ensure_missing_columns(target)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
