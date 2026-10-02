"""Fail-closed schema release inventory and copy-only migration checks."""

import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "infra"))
from schema_rehearsal import _snapshot, rehearse_sqlite
from schema_release import (
    SchemaReleaseError,
    classify_upgrade,
    draft_manifest,
    inventory,
    sqlite_state,
    verify_manifest,
)


def _hash(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _version(path: Path, revision: str, parent: str | None, operation: str) -> None:
    path.write_text(
        f"revision = {revision!r}\ndown_revision = {parent!r}\n"
        f"def upgrade():\n    {operation}\n",
        encoding="utf-8",
    )


def test_real_chain_is_single_head_and_draft_is_blocked():
    versions = ROOT / "apps/api/alembic/versions"
    chain = inventory(versions)
    assert len(chain) == 46
    assert chain[9]["revision"] == "c8d9e0f1a2b3"
    assert chain[-1]["revision"] == "a06f78d90e12"
    assert any(entry["classification"] == "manual_block" for entry in chain[10:])
    draft = json.loads((ROOT / "infra/schema-release-manifest.v1.json").read_text())
    assert draft == draft_manifest(versions, baseline="c8d9e0f1a2b3")
    with pytest.raises(SchemaReleaseError, match="manual/destructive"):
        verify_manifest(draft, versions, exact_manifest_sha256=_hash(draft),
                        source_state="c8d9e0f1a2b3", actual_state="c8d9e0f1a2b3",
                        rehearsal_sha256="a" * 64, backup_sha256="b" * 64)


def test_chain_gap_and_two_heads_block(tmp_path):
    _version(tmp_path / "a.py", "aaaaaaaaaaaa", None, "op.create_table('a')")
    _version(tmp_path / "b.py", "bbbbbbbbbbbb", "aaaaaaaaaaaa", "op.create_index('b')")
    assert [x["revision"] for x in inventory(tmp_path)] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    _version(tmp_path / "c.py", "cccccccccccc", "aaaaaaaaaaaa", "op.create_table('c')")
    with pytest.raises(SchemaReleaseError, match="single-root single-head"):
        inventory(tmp_path)
    (tmp_path / "c.py").unlink()
    _version(tmp_path / "b.py", "bbbbbbbbbbbb", "dddddddddddd", "op.create_index('b')")
    with pytest.raises(SchemaReleaseError, match="no gaps"):
        inventory(tmp_path)


def test_exact_reviewed_synthetic_manifest_and_tampering(tmp_path):
    _version(tmp_path / "a.py", "aaaaaaaaaaaa", None, "op.create_table('a')")
    _version(tmp_path / "b.py", "bbbbbbbbbbbb", "aaaaaaaaaaaa", "op.create_index('b')")
    manifest = draft_manifest(tmp_path, baseline="aaaaaaaaaaaa")
    manifest["review"] = {"status": "approved", "owner": "fixture-reviewer",
                          "rehearsal_evidence_sha256": "a" * 64,
                          "data_backup_sha256": "b" * 64}
    args = {"exact_manifest_sha256": _hash(manifest), "source_state": "aaaaaaaaaaaa",
            "actual_state": "aaaaaaaaaaaa", "rehearsal_sha256": "a" * 64,
            "backup_sha256": "b" * 64}
    verify_manifest(manifest, tmp_path, **args)
    with pytest.raises(SchemaReleaseError, match="source revision"):
        verify_manifest(manifest, tmp_path, **{**args, "actual_state": "unversioned"})
    tampered = copy.deepcopy(manifest)
    tampered["review"]["owner"] = "attacker"
    with pytest.raises(SchemaReleaseError, match="manifest hash"):
        verify_manifest(tampered, tmp_path, **args)
    (tmp_path / "b.py").write_text((tmp_path / "b.py").read_text() + "# altered\n")
    with pytest.raises(SchemaReleaseError, match="inventory/hash"):
        verify_manifest(manifest, tmp_path, **args)


def test_destructive_and_unknown_calls_block(tmp_path):
    import ast

    for operation in ("op.drop_table('users')", "op.execute('DELETE FROM users')",
                      "op.add_column('users', sa.Column('x', nullable=False))",
                      "op.alter_column('users', 'x', type_=sa.Integer())"):
        result = classify_upgrade(ast.parse(f"def upgrade():\n    {operation}\n"))
        assert result["classification"] == "manual_block"


def test_unversioned_legacy_is_not_guessed_from_tables(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE users (id TEXT)")
    assert sqlite_state(path) == "unversioned"
    assert sqlite_state(tmp_path / "missing.db") == "unknown"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE alembic_version (version_num TEXT)")
        db.executemany("INSERT INTO alembic_version VALUES (?)", [("a",), ("b",)])
    assert sqlite_state(path) == "unknown"


def test_available_c8_baseline_copy_upgrades_without_touching_original(tmp_path):
    original = tmp_path / "baseline.db"
    cfg = Config(str(ROOT / "apps/api/alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{original}")
    command.upgrade(cfg, "c8d9e0f1a2b3")
    with sqlite3.connect(original) as db:
        db.execute("INSERT INTO organizations VALUES ('org', 'Тест', 'customer', 'Москва', CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,totp_enabled,created_at) "
                   "VALUES ('user','test@example.invalid','Тест','hash',0,0,CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO support_tickets "
                   "(id,author_user_id,category,subject,body,status,created_at) "
                   "VALUES ('ticket','user','other','Тест','Сохранить','open',CURRENT_TIMESTAMP)")
    old_bytes = original.read_bytes()
    candidate = tmp_path / "candidate.db"
    with sqlite3.connect(original) as source, sqlite3.connect(candidate) as target:
        source.backup(target)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{candidate}")
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    assert original.read_bytes() == old_bytes
    assert sqlite_state(original) == "c8d9e0f1a2b3"
    assert sqlite_state(candidate) == "a06f78d90e12"
    with sqlite3.connect(candidate) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT id,body FROM support_tickets").fetchone() == ("ticket", "Сохранить")


def test_v2_sealed_backup_restore_then_copy_rehearsal(tmp_path, monkeypatch):
    source = tmp_path / "baseline.db"
    cfg = Config(str(ROOT / "apps/api/alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{source}")
    command.upgrade(cfg, "c8d9e0f1a2b3")
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO organizations VALUES ('org', 'Тест', 'customer', 'Москва', CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO organizations VALUES ('supplier', 'Поставщик', 'artist', 'Москва', CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,totp_enabled,created_at) "
                   "VALUES ('user','backup@example.invalid','Тест','hash',0,0,CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO events (id,organization_id,title,city,event_date,guest_count,notes,status) "
                   "VALUES ('event','org','Событие','Москва','2026-12-01',20,'','Draft')")
        db.execute("INSERT INTO availability_slots "
                   "(id,resource_type,resource_id,starts_at,ends_at,status,buffer_before_min,buffer_after_min) "
                   "VALUES ('slot','artist','resource','2026-12-01 12:00:00','2026-12-01 13:00:00','open',0,0)")
        db.execute("INSERT INTO requests (id,event_id,resource_type,resource_id,supplier_org_id,status,created_at) "
                   "VALUES ('request','event','artist','resource','supplier','RequestSent',CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO offers (id,request_id,created_at) "
                   "VALUES ('offer','request',CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO offer_versions "
                   "(id,offer_id,honorarium_rub,commission_rate,commission_rub,total_rub,currency,terms,"
                   "customer_ack,supplier_ack,created_at) VALUES "
                   "('version','offer',1000,10,100,1100,'RUB','{}',1,1,CURRENT_TIMESTAMP)")
        db.execute("UPDATE offers SET active_version_id='version' WHERE id='offer'")
        db.execute("INSERT INTO bookings "
                   "(id,event_id,offer_id,slot_id,status,payout_pending,created_at) VALUES "
                   "('booking','event','offer','slot','Confirmed',0,CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO payments "
                   "(id,booking_id,amount_rub,status,provider,idempotency_key,created_at) VALUES "
                   "('payment','booking',1100,'succeeded','stub','schema-test',CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO support_tickets "
                   "(id,author_user_id,category,subject,body,status,created_at) "
                   "VALUES ('ticket','user','other','Тест','Сохранить','open',CURRENT_TIMESTAMP)")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "sample.txt").write_text("synthetic upload")
    key = tmp_path / "key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    backups = tmp_path / "backups"
    env = {**os.environ, "BOOKER_DATABASE_URL": f"sqlite:///{source}",
           "BOOKER_UPLOAD_DIR": str(uploads), "BOOKER_BACKUP_DIR": str(backups),
           "BOOKER_BACKUP_FORMAT": "sealed", "BOOKER_BACKUP_KEY_FILE": str(key),
           "BOOKER_PYTHON": sys.executable}
    subprocess.run(["bash", str(ROOT / "infra/backup-booker.sh")], env=env, check=True,
                   capture_output=True)
    archives = list(backups.glob("*.bke"))
    assert len(archives) == 1
    archive = archives[0]
    restored = tmp_path / "restored"
    subprocess.run(["bash", str(ROOT / "infra/run-booker-ops-restore-drill.sh"),
                    str(archive), str(restored)], env=env, check=True, capture_output=True)
    before_restore = (restored / "booker.db").read_bytes()
    result = rehearse_sqlite(
        restored / "booker.db", tmp_path / "candidate.db",
        source_revision="c8d9e0f1a2b3", target_head="ffbc123cd4e6", archive=archive,
        backup_evidence=Path(str(archive) + ".evidence.json"),
        restore_evidence=backups / ".ops-restore.json",
        alembic_ini=ROOT / "apps/api/alembic.ini",
    )
    assert result["status"] == "local_rehearsed"
    assert result["critical"]["support_tickets"]["count"] == 1
    assert result["critical"]["bookings"]["count"] == 1
    assert result["critical"]["payments"]["count"] == 1
    assert (restored / "booker.db").read_bytes() == before_restore
    assert sqlite_state(tmp_path / "candidate.db") == "ffbc123cd4e6"
    with sqlite3.connect(tmp_path / "candidate.db") as db:
        assert db.execute("SELECT total_rub, advance_rub, balance_rub FROM offer_versions "
                          "WHERE id='version'").fetchone() == (1100, 1100, 0)
        assert db.execute("SELECT amount_rub, status FROM payments WHERE id='payment'").fetchone() == (
            1100, "succeeded"
        )
        assert db.execute("SELECT amount_rub, kind FROM money_movements WHERE payment_id='payment'").fetchone() == (
            1100, "capture"
        )
        assert db.execute("SELECT body FROM support_tickets WHERE id='ticket'").fetchone() == (
            "Сохранить",
        )
    with sqlite3.connect(tmp_path / "candidate.db") as db:
        db.execute("UPDATE payments SET status='failed' WHERE id='payment'")
    assert _snapshot(restored / "booker.db") != _snapshot(tmp_path / "candidate.db")
    forged = tmp_path / "forged-restored"
    forged.mkdir()
    (forged / "booker.db").write_bytes(before_restore)
    (forged / "backup-manifest.json").write_bytes((restored / "backup-manifest.json").read_bytes())
    with sqlite3.connect(forged / "booker.db") as db:
        db.execute("UPDATE payments SET amount_rub=1 WHERE id='payment'")
    with pytest.raises(SchemaReleaseError, match="differs from restored archive"):
        rehearse_sqlite(
            forged / "booker.db", tmp_path / "forged-output.db",
            source_revision="c8d9e0f1a2b3", target_head="ffbc123cd4e6", archive=archive,
            backup_evidence=Path(str(archive) + ".evidence.json"),
            restore_evidence=backups / ".ops-restore.json",
            alembic_ini=ROOT / "apps/api/alembic.ini",
        )
    wal_source = tmp_path / "wal-restored"
    wal_source.mkdir()
    (wal_source / "booker.db").write_bytes(before_restore)
    (wal_source / "backup-manifest.json").write_bytes(
        (restored / "backup-manifest.json").read_bytes()
    )
    (wal_source / "booker.db-wal").write_bytes(b"untrusted WAL state")
    with pytest.raises(SchemaReleaseError, match="sidecar state"):
        rehearse_sqlite(
            wal_source / "booker.db", tmp_path / "wal-output.db",
            source_revision="c8d9e0f1a2b3", target_head="ffbc123cd4e6", archive=archive,
            backup_evidence=Path(str(archive) + ".evidence.json"),
            restore_evidence=backups / ".ops-restore.json",
            alembic_ini=ROOT / "apps/api/alembic.ini",
        )
    failed = tmp_path / "candidate-fail.db"

    def failed_upgrade(_config, _revision):
        with sqlite3.connect(failed) as db:
            db.execute("DELETE FROM support_tickets")
        raise RuntimeError("synthetic migration failure")

    monkeypatch.setattr(command, "upgrade", failed_upgrade)
    with pytest.raises(RuntimeError, match="synthetic migration failure"):
        rehearse_sqlite(
            restored / "booker.db", failed, source_revision="c8d9e0f1a2b3",
            target_head="ffbc123cd4e6", archive=archive,
            backup_evidence=Path(str(archive) + ".evidence.json"),
            restore_evidence=backups / ".ops-restore.json",
            alembic_ini=ROOT / "apps/api/alembic.ini",
        )
    assert not failed.exists()
    assert (restored / "booker.db").read_bytes() == before_restore


@pytest.mark.postgres_integration
def test_postgres_c8_to_head_in_disposable_schema():
    from sqlalchemy import text

    from tests.postgres_harness import isolated_postgres_schema

    dsn = os.environ.get("TEST_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN absent: PostgreSQL schema rehearsal unverified")
    with isolated_postgres_schema(dsn) as (engine, config, _schema):
        command.upgrade(config, "c8d9e0f1a2b3")
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,"
                "totp_enabled,created_at) VALUES "
                "('pg-user','schema@booker.test','PG User','hash',false,false,CURRENT_TIMESTAMP)"
            ))
            connection.execute(text(
                "INSERT INTO support_tickets "
                "(id,author_user_id,category,subject,body,status,created_at) "
                "VALUES ('pg-ticket','pg-user','other','Тест','Сохранить','open',CURRENT_TIMESTAMP)"
            ))
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "a06f78d90e12"
            )
            assert connection.execute(text(
                "SELECT body FROM support_tickets WHERE id='pg-ticket'"
            )).scalar_one() == "Сохранить"
