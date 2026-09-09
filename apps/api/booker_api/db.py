from collections.abc import Generator
from pathlib import Path

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
    _add_column_if_missing(
        bind, "availability_slots", "external_uid", "external_uid VARCHAR(255)"
    )
    _add_column_if_missing(bind, "requests", "requirement_id", "requirement_id VARCHAR(36)")
    ts_type = "TIMESTAMPTZ" if dialect == "postgresql" else "DATETIME"
    _add_column_if_missing(
        bind,
        "session_tokens",
        "admin_2fa_verified_at",
        f"admin_2fa_verified_at {ts_type}",
    )
    _add_column_if_missing(
        bind,
        "session_tokens",
        "expires_at",
        f"expires_at {ts_type}",
    )
    _add_column_if_missing(bind, "venues", "address", "address VARCHAR(512) DEFAULT ''")
    _add_column_if_missing(bind, "venues", "district", "district VARCHAR(128) DEFAULT ''")
    _add_column_if_missing(bind, "venues", "metro", "metro VARCHAR(128) DEFAULT ''")
    _add_column_if_missing(bind, "venues", "description", "description TEXT DEFAULT ''")
    _add_column_if_missing(bind, "venues", "source_url", "source_url VARCHAR(512) DEFAULT ''")
    _add_column_if_missing(
        bind, "venues", "source_attribution", "source_attribution VARCHAR(128) DEFAULT ''"
    )
    _add_column_if_missing(
        bind, "venues", "listing_origin", "listing_origin VARCHAR(32) DEFAULT 'owner'"
    )
    _add_column_if_missing(
        bind, "venues", "availability_mode", "availability_mode VARCHAR(32) DEFAULT 'owner'"
    )
    _add_column_if_missing(bind, "venues", "venue_type", "venue_type VARCHAR(64) DEFAULT ''")
    _add_column_if_missing(
        bind,
        "venues",
        "administrative_district",
        "administrative_district VARCHAR(32) DEFAULT ''",
    )
    _add_column_if_missing(bind, "venues", "latitude", "latitude FLOAT")
    _add_column_if_missing(bind, "venues", "longitude", "longitude FLOAT")
    _add_column_if_missing(bind, "venues", "phone", "phone VARCHAR(64) DEFAULT ''")
    _add_column_if_missing(bind, "venues", "email", "email VARCHAR(255) DEFAULT ''")
    _add_column_if_missing(
        bind, "venues", "official_website", "official_website VARCHAR(512) DEFAULT ''"
    )
    _add_column_if_missing(
        bind, "venues", "source_type", "source_type VARCHAR(32) DEFAULT 'owner_submission'"
    )
    _add_column_if_missing(
        bind, "venues", "partnership_status", "partnership_status VARCHAR(32) DEFAULT 'claimed'"
    )
    _add_column_if_missing(bind, "venues", "is_partner", "is_partner BOOLEAN DEFAULT 0")
    _add_column_if_missing(bind, "venues", "is_claimed", "is_claimed BOOLEAN DEFAULT 1")
    _add_column_if_missing(
        bind, "venues", "moderation_status", "moderation_status VARCHAR(32) DEFAULT 'published'"
    )
    _add_column_if_missing(
        bind, "venues", "completeness_score", "completeness_score INTEGER DEFAULT 0"
    )
    _add_column_if_missing(bind, "venues", "details_json", "details_json TEXT DEFAULT '{}'")
    _add_column_if_missing(bind, "venues", "verified_at", f"verified_at {ts_type}")
    _add_column_if_missing(bind, "venues", "verified_by", "verified_by VARCHAR(36)")
    _add_column_if_missing(
        bind, "venues", "partnership_started_at", f"partnership_started_at {ts_type}"
    )
    _add_column_if_missing(bind, "venues", "status_changed_at", f"status_changed_at {ts_type}")
    _add_column_if_missing(bind, "venues", "last_verified_at", f"last_verified_at {ts_type}")
    _add_column_if_missing(bind, "venues", "last_crawled_at", f"last_crawled_at {ts_type}")
    _add_column_if_missing(
        bind,
        "venues",
        "data_freshness_status",
        "data_freshness_status VARCHAR(32) DEFAULT 'needs_review'",
    )


def ensure_sqlite_columns(bind) -> None:
    ensure_missing_columns(bind)


def make_engine(url: str | None = None):
    db_url = url or settings.database_url
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, connect_args=connect_args, future=True)


def run_migrations(url: str | None = None) -> None:
    """Apply Alembic revisions (Postgres prod path)."""
    from alembic.config import Config

    from alembic import command

    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", url or settings.database_url)
    command.upgrade(cfg, "head")


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_schema(bind=None) -> None:
    target = bind or engine
    if target.dialect.name == "postgresql":
        run_migrations(str(target.url))
        return
    Base.metadata.create_all(bind=target)
    ensure_missing_columns(target)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
