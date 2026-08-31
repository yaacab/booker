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


def test_alembic_baseline_revision_exists():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    files = list(versions.glob("*_baseline.py"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "def upgrade()" in text
    assert "users" in text
