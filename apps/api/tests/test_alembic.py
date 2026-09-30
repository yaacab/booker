from pathlib import Path

from sqlalchemy import create_engine, inspect

import booker_api.models  # noqa: F401
from booker_api.db import Base, run_migrations


def test_alembic_baseline_matches_models(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'migrate.db'}"
    run_migrations(db_url)
    run_migrations(db_url)  # idempotent

    eng = create_engine(db_url)
    inspector = inspect(eng)
    actual = set(inspector.get_table_names()) - {"alembic_version"}
    assert actual == set(Base.metadata.tables.keys())


def test_alembic_session_token_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'migrate.db'}"
    run_migrations(db_url)

    eng = create_engine(db_url)
    cols = {c["name"] for c in inspect(eng).get_columns("session_tokens")}
    assert {"token", "user_id", "created_at", "admin_2fa_verified_at", "expires_at"} <= cols


def test_alembic_baseline_revision_exists():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    files = list(versions.glob("*_baseline.py"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "def upgrade()" in text
    assert "users" in text


def test_commercial_migration_preserves_historic_offer_and_guards_price(tmp_path):
    import pytest
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    url = f"sqlite:///{tmp_path / 'historic.db'}"
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "c8d9e0f1a2b3")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO offer_versions (id, offer_id, honorarium_rub, "
                "commission_rate, commission_rub, total_rub, currency, terms, "
                "customer_ack, supplier_ack, created_at) VALUES "
                "('old', 'old-offer', 1000, 0.1, 100, 1100, 'RUB', 'historic', "
                "0, 0, CURRENT_TIMESTAMP)"
            )
        )
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        old = conn.execute(
            text(
                "SELECT total_rub, supplier_service_fee_rub, "
                "commercial_policy_version FROM offer_versions WHERE id='old'"
            )
        ).one()
        assert old == (1100, None, None)
        conn.execute(text("UPDATE offer_versions SET customer_ack=1 WHERE id='old'"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("UPDATE offer_versions SET total_rub=1060 WHERE id='old'"))
    command.downgrade(cfg, "c8d9e0f1a2b3")
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT total_rub FROM offer_versions WHERE id='old'")).scalar()
            == 1100
        )
    command.upgrade(cfg, "head")
