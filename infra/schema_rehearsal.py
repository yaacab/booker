"""Upgrade a disposable SQLite copy and record local, non-production evidence."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

from schema_release import SchemaReleaseError, digest, sqlite_state

CRITICAL = ("organizations", "users", "events", "offers", "offer_versions",
            "bookings", "payments", "support_tickets")
STABLE_FIELDS = {
    "organizations": "id,name,kind,city",
    "users": "id,email,full_name,is_platform_admin",
    "events": "id,organization_id,title,event_date,guest_count",
    "offers": "id,request_id,active_version_id",
    "offer_versions": "id,offer_id,honorarium_rub,commission_rate,commission_rub,total_rub,currency,terms",
    "bookings": "id,event_id,offer_id,slot_id,status",
    "payments": "id,booking_id,amount_rub,status,provider,idempotency_key",
    "support_tickets": "id,author_user_id,category,subject,body,status",
}


def _snapshot(path: Path) -> dict:
    with sqlite3.connect(path) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SchemaReleaseError("SQLite integrity failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise SchemaReleaseError("SQLite foreign key check failed")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        result = {}
        for table in CRITICAL:
            if table not in tables:
                raise SchemaReleaseError(f"missing critical table {table}")
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            ids = connection.execute(f"SELECT id FROM {table} ORDER BY id").fetchall()
            fingerprint = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
            rows = connection.execute(
                f"SELECT {STABLE_FIELDS[table]} FROM {table} ORDER BY id"
            ).fetchall()
            value_hash = hashlib.sha256(repr(rows).encode()).hexdigest()
            result[table] = {"count": count, "id_sha256": fingerprint,
                             "stable_values_sha256": value_hash}
        return result


def verify_backup_restore(archive: Path, backup_evidence: Path, restore_evidence: Path,
                          source: Path, source_revision: str) -> dict:
    from backup_contract import read_evidence, verify_binding

    backup = verify_binding(backup_evidence, archive, "sqlite")
    restored = read_evidence(restore_evidence, "restore")
    if (restored["status"] != "ok" or restored["archive_id"] != backup["archive_id"]
            or restored["archive_sha256"] != backup["archive_sha256"]
            or restored["schema_revision"] != source_revision
            or backup["schema_revision"] != source_revision):
        raise SchemaReleaseError("backup v2 and restore evidence do not match source revision")
    manifest_path = source.parent / "backup-manifest.json"
    if source.name != "booker.db" or not manifest_path.is_file() or manifest_path.is_symlink():
        raise SchemaReleaseError("source is not a restored Booker snapshot")
    if digest(manifest_path) != backup["manifest_sha256"]:
        raise SchemaReleaseError("restored manifest differs from bound archive")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    db_files = [item for item in manifest.get("files", []) if item.get("path") == "booker.db"]
    if (len(db_files) != 1 or db_files[0].get("sha256") != digest(source)
            or db_files[0].get("size") != source.stat().st_size):
        raise SchemaReleaseError("rehearsal DB differs from restored archive")
    return backup


def rehearse_sqlite(source: Path, output: Path, *, source_revision: str, target_head: str,
                    archive: Path, backup_evidence: Path, restore_evidence: Path,
                    alembic_ini: Path) -> dict:
    """Operate only on a restored synthetic/isolated DB and an output copy."""
    from alembic import command
    from alembic.config import Config

    if output.exists() or source.is_symlink() or source.resolve() == output.resolve():
        raise SchemaReleaseError("unsafe rehearsal path")
    sidecars = [Path(str(source) + suffix) for suffix in ("-wal", "-shm", "-journal")]
    if any(path.exists() or path.is_symlink() for path in sidecars):
        raise SchemaReleaseError("restored source has SQLite sidecar state")
    if sqlite_state(source) != source_revision:
        raise SchemaReleaseError("rehearsal source revision mismatch")
    backup = verify_backup_restore(archive, backup_evidence, restore_evidence,
                                   source, source_revision)
    before_file_hash = digest(source)
    before = _snapshot(source)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(output) as candidate_db:
        source_db.backup(candidate_db)
    if any(path.exists() or path.is_symlink() for path in sidecars):
        output.unlink(missing_ok=True)
        raise SchemaReleaseError("SQLite sidecar appeared during rehearsal copy")
    output.chmod(0o600)
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{output}")
    try:
        command.upgrade(config, target_head)
        if sqlite_state(output) != target_head:
            raise SchemaReleaseError("rehearsal did not reach target head")
        after = _snapshot(output)
        if after != before:
            raise SchemaReleaseError("critical row IDs/counts changed")
        first_hash = digest(output)
        command.upgrade(config, target_head)
        if digest(output) != first_hash:
            raise SchemaReleaseError("second upgrade changed DB bytes")
        if digest(source) != before_file_hash:
            raise SchemaReleaseError("original rehearsal source changed")
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return {"version": 1, "status": "local_rehearsed", "source_revision": source_revision,
            "target_head": target_head, "source_sha256": before_file_hash,
            "candidate_sha256": digest(output), "archive_sha256": backup["archive_sha256"],
            "critical": before, "rollback": "original restored copy unchanged"}


def write_evidence(path: Path, payload: dict) -> None:
    if path.exists() or path.is_symlink():
        raise SchemaReleaseError("evidence path already exists")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(payload, output, sort_keys=True, separators=(",", ":"))
        output.flush()
        os.fsync(output.fileno())
