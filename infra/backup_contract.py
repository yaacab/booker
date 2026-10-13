"""Private v2 evidence tying one verified backup to one restore drill."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

VERIFIER_VERSION = "booker-restore-v2"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_path(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise ValueError("evidence path must be absolute and not symlinked")


def _write(path: Path, payload: dict) -> None:
    _safe_path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".booker-evidence-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, separators=(",", ":"), sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish(temp: Path, destination: Path) -> None:
    if temp.parent != destination.parent or destination.exists() or temp.is_symlink():
        raise ValueError("unsafe archive publication")
    with temp.open("rb") as source:
        os.fsync(source.fileno())
    os.link(temp, destination)
    directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
        temp.unlink()
        os.fsync(directory)
    finally:
        os.close(directory)


def _manifest(path: Path) -> dict:
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("oversized backup manifest")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != 2:
        raise ValueError("legacy backup manifest is not v2 evidence")
    UUID(value["archive_id"])
    if value.get("db_engine") not in {"sqlite", "postgresql"}:
        raise ValueError("invalid manifest database engine")
    created_at = datetime.fromisoformat(value["created_at"])
    if created_at.tzinfo is None or created_at.utcoffset().total_seconds() != 0:
        raise ValueError("backup manifest timestamp must be UTC")
    return value


def record_backup(evidence: Path, archive: Path, manifest_path: Path) -> dict:
    if archive.is_symlink() or not archive.is_file() or archive.name != archive.as_posix().split("/")[-1]:
        raise ValueError("unsafe archive")
    manifest = _manifest(manifest_path)
    encrypted = manifest["encryption"] == "sealed-aes-256-gcm-v1"
    if encrypted != (archive.suffix == ".bke"):
        raise ValueError("backup encryption/extension mismatch")
    key_id = None
    if encrypted:
        from backup_crypto import KEY_ID_BYTES, MAGIC

        with archive.open("rb") as source:
            header = source.read(len(MAGIC) + KEY_ID_BYTES)
        if not header.startswith(MAGIC) or len(header) != len(MAGIC) + KEY_ID_BYTES:
            raise ValueError("invalid sealed archive header")
        key_id = header[len(MAGIC):].hex()
    payload = {
        "version": 2, "kind": "backup", "status": "ok", "at": _now(),
        "archive_id": manifest["archive_id"], "archive": archive.name,
        "archive_sha256": sha256(archive), "archive_bytes": archive.stat().st_size,
        "manifest_sha256": sha256(manifest_path), "created_at": manifest["created_at"],
        "db_engine": manifest["db_engine"], "schema_revision": manifest["schema_revision"],
        "source_environment": manifest["source_environment"],
        "encryption": manifest["encryption"], "attachments": manifest["attachments"],
        "encryption_key_id": key_id,
    }
    _write(archive.with_name(archive.name + ".evidence.json"), payload)
    _write(evidence, payload)
    return payload


def read_evidence(path: Path, kind: str) -> dict:
    _safe_path(path)
    if not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("missing or oversized evidence")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("kind") != kind or payload.get("version") != 2:
        raise ValueError("legacy or mismatched evidence")
    if payload.get("status") not in {"ok", "failed", "unknown"}:
        raise ValueError("invalid evidence status")
    return payload


def verify_binding(evidence: Path, archive: Path, expected_engine: str | None = None) -> dict:
    marker = read_evidence(evidence, "backup")
    if marker["status"] != "ok":
        raise ValueError("backup evidence is not successful")
    UUID(marker["archive_id"])
    if archive.is_symlink() or not archive.is_file() or archive.name != marker["archive"]:
        raise ValueError("archive identity mismatch")
    if archive.stat().st_size != marker["archive_bytes"] or sha256(archive) != marker["archive_sha256"]:
        raise ValueError("archive checksum mismatch")
    if not HEX64.fullmatch(marker["archive_sha256"]) or not HEX64.fullmatch(marker["manifest_sha256"]):
        raise ValueError("invalid evidence digest")
    if expected_engine and marker["db_engine"] != expected_engine:
        raise ValueError("database engine mismatch")
    return marker


def record_restore(
    evidence: Path, backup_evidence: Path, archive: Path, restored: Path, started_at: str,
) -> dict:
    started = datetime.fromisoformat(started_at)
    if started.tzinfo is None or started.utcoffset().total_seconds() != 0:
        raise ValueError("restore start timestamp must be UTC")
    marker = verify_binding(backup_evidence, archive, "sqlite")
    manifest_path = restored / "backup-manifest.json"
    manifest = _manifest(manifest_path)
    if (
        manifest["archive_id"] != marker["archive_id"]
        or sha256(manifest_path) != marker["manifest_sha256"]
        or manifest["db_engine"] != marker["db_engine"]
        or manifest["schema_revision"] != marker["schema_revision"]
        or manifest["attachments"] != marker["attachments"]
    ):
        raise ValueError("restored snapshot identity mismatch")
    with sqlite3.connect(f"file:{(restored / 'booker.db').resolve()}?mode=ro", uri=True) as db:
        present = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        revisions = [row[0] for row in db.execute("SELECT version_num FROM alembic_version")] if present else []
    actual_revision = ",".join(sorted(revisions)) if revisions else "unknown"
    if actual_revision != marker["schema_revision"]:
        raise ValueError("restored schema revision mismatch")
    payload = {
        "version": 2, "kind": "restore", "status": "ok", "at": _now(),
        "started_at": started_at, "finished_at": _now(),
        "archive_id": marker["archive_id"], "archive_sha256": marker["archive_sha256"],
        "db_engine": marker["db_engine"], "schema_revision": marker["schema_revision"],
        "attachments": marker["attachments"], "verifier_version": VERIFIER_VERSION,
    }
    _write(evidence, payload)
    return payload


def record_failure(evidence: Path, kind: str, started_at: str) -> None:
    if kind not in {"backup", "restore"}:
        raise ValueError("invalid evidence kind")
    _write(evidence, {
        "version": 2, "kind": kind, "status": "failed", "at": _now(),
        "started_at": started_at, "finished_at": _now(),
    })


def record_unknown(evidence: Path, started_at: str, reason: str = "legacy_evidence_or_archive") -> None:
    if reason not in {"legacy_evidence_or_archive", "postgresql_restore_unverified"}:
        raise ValueError("invalid unknown reason")
    _write(evidence, {
        "version": 2, "kind": "restore", "status": "unknown", "at": _now(),
        "started_at": started_at, "finished_at": _now(),
        "reason": reason,
    })


def classify(evidence: Path) -> str:
    try:
        _safe_path(evidence)
        if not evidence.is_file() or evidence.stat().st_size > 8192:
            return "legacy"
        value = json.loads(evidence.read_text(encoding="utf-8"))
        if value.get("version") == 2 and value.get("kind") == "backup":
            return "v2"
        if value.get("version") == 1 and value.get("kind") == "backup":
            return "legacy"
        return "invalid"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return "invalid"


def main() -> None:
    command, *args = sys.argv[1:]
    if command == "publish" and len(args) == 2:
        publish(Path(args[0]), Path(args[1]))
    elif command == "backup" and len(args) == 3:
        record_backup(Path(args[0]), Path(args[1]), Path(args[2]))
    elif command == "verify" and len(args) in {2, 3}:
        verify_binding(Path(args[0]), Path(args[1]), args[2] if len(args) == 3 else None)
    elif command == "restore" and len(args) == 5:
        record_restore(Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3]), args[4])
    elif command == "failure" and len(args) == 3:
        record_failure(Path(args[0]), args[1], args[2])
    elif command == "unknown" and len(args) in {2, 3}:
        record_unknown(Path(args[0]), args[1], args[2] if len(args) == 3 else "legacy_evidence_or_archive")
    elif command == "classify" and len(args) == 1:
        print(classify(Path(args[0])))
    else:
        raise SystemExit("invalid backup contract command")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise SystemExit("backup evidence verification failed") from None
