from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from alembic import command


def test_reconciliation_migration_roundtrip_and_db_immutability(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'reconciliation-migration.db'}"
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "f38f901ab2c3")
    engine = create_engine(db_url)
    assert "reconciliation_runs" not in inspect(engine).get_table_names()

    command.upgrade(config, "f49a012bc3d4")
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO reconciliation_runs "
            "(id, provider, merchant, report_id, content_sha256, period_start, period_end, "
            "status, failure_reason, received_at) VALUES "
            "('run-1', 'stub', 'merchant', 'report', 'hash', CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP, 'completed', '', CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO reconciliation_entries "
            "(id, run_id, provider, merchant, line_no, provider_operation_id, "
            "provider_reference, operation_kind, amount_rub, currency, provider_status, "
            "occurred_at, created_at) VALUES "
            "('entry-1', 'run-1', 'stub', 'merchant', 1, 'op-1', 'ref-1', "
            "'capture', 100, 'RUB', 'succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("UPDATE reconciliation_entries SET amount_rub = 101"))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("UPDATE reconciliation_runs SET report_id = 'changed'"))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("DELETE FROM reconciliation_runs WHERE id = 'run-1'"))

    command.downgrade(config, "f38f901ab2c3")
    inspector = inspect(engine)
    assert "reconciliation_runs" not in inspector.get_table_names()
    assert "provider_merchant" not in {column["name"] for column in inspector.get_columns("payments")}
    command.upgrade(config, "f49a012bc3d4")
    assert "reconciliation_runs" in inspect(engine).get_table_names()
