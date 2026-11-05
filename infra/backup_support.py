"""Safe helpers shared by Booker backup and restore scripts."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import uuid4


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"symlink is not allowed in backup input: {path}")
        if path.is_file() and path != root / "backup-manifest.json":
            files.append(path)
    return files


def sqlite_backup(source: Path, destination: Path) -> None:
    if not source.is_file() or not os.access(source, os.R_OK):
        raise RuntimeError(f"SQLite source is missing or unreadable: {source}")
    source_uri = f"file:{source.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as src:
        if src.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite source quick_check failed")
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite backup quick_check failed")


def snapshot_uploads(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f"upload directory is missing: {source}")
    before = {
        str(path.relative_to(source)): (_sha256(path), path.stat().st_size, path.stat().st_mtime_ns)
        for path in _files(source)
    }
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    after = {
        str(path.relative_to(source)): (_sha256(path), path.stat().st_size, path.stat().st_mtime_ns)
        for path in _files(source)
    }
    copied = {
        str(path.relative_to(destination)): (_sha256(path), path.stat().st_size)
        for path in _files(destination)
    }
    expected = {name: (digest, size) for name, (digest, size, _mtime) in before.items()}
    if before != after or copied != expected:
        raise RuntimeError("uploads changed while the backup snapshot was being created")


def write_manifest(staging: Path) -> None:
    entries = [
        {
            "path": str(path.relative_to(staging)),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in _files(staging)
    ]
    database = "sqlite" if (staging / "booker.db").is_file() else "postgresql"
    if database == "postgresql" and not (staging / "booker.dump").is_file():
        raise RuntimeError("backup staging has no supported database snapshot")
    schema_revision = "unknown"
    if database == "sqlite":
        with sqlite3.connect(f"file:{(staging / 'booker.db').resolve()}?mode=ro", uri=True) as db:
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone():
                revisions = [row[0] for row in db.execute("SELECT version_num FROM alembic_version")]
                schema_revision = ",".join(sorted(revisions)) if revisions else "unknown"
    uploads = [entry for entry in entries if entry["path"].startswith("uploads/")]
    upload_identity = hashlib.sha256(
        json.dumps(uploads, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    source_environment = os.environ.get("BOOKER_RUNTIME_ENV", "unknown")
    if source_environment not in {"local", "test", "staging", "production"}:
        source_environment = "unknown"
    manifest = {
        "version": 2, "archive_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_engine": database, "schema_revision": schema_revision,
        "source_environment": source_environment,
        "encryption": "sealed-aes-256-gcm-v1" if os.environ.get("BOOKER_BACKUP_FORMAT") == "sealed" else "none",
        "attachments": {"count": len(uploads), "bytes": sum(entry["size"] for entry in uploads),
                        "identity_sha256": upload_identity},
        "files": entries,
    }
    (staging / "backup-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    for member in archive:
        members.append(member)
        if len(members) > 100_000:
            raise RuntimeError("backup archive has too many members")
    raw_limit = os.environ.get("BOOKER_BACKUP_MAX_RESTORE_BYTES", str(20 * 1024 * 1024 * 1024))
    if not raw_limit.isdecimal() or int(raw_limit) < 1024:
        raise RuntimeError("BOOKER_BACKUP_MAX_RESTORE_BYTES must be an integer >= 1024")
    if sum(member.size for member in members if member.isfile()) > int(raw_limit):
        raise RuntimeError("backup contents exceed restore size limit")
    names = set()
    for member in members:
        path = PurePosixPath(member.name)
        name = member.name.rstrip("/")
        if (
            path.is_absolute()
            or ".." in path.parts
            or (not member.isfile() and not member.isdir())
            or name in names
        ):
            raise RuntimeError(f"unsafe archive member: {member.name}")
        names.add(name)
    if (
        not ({"booker.db", "booker.dump"} & names)
        or "uploads" not in names
        or "backup-manifest.json" not in names
    ):
        raise RuntimeError("archive must contain a database, uploads and backup-manifest.json")
    if not any(member.name.rstrip("/") == "uploads" and member.isdir() for member in members):
        raise RuntimeError("uploads must be a directory")
    return members


def verify_archive(archive_path: Path) -> None:
    """Detect accidental archive corruption; this is not an authenticity signature."""
    raw_limit = os.environ.get("BOOKER_BACKUP_MAX_RESTORE_BYTES", str(20 * 1024 * 1024 * 1024))
    if not raw_limit.isdecimal() or int(raw_limit) < 1024:
        raise RuntimeError("BOOKER_BACKUP_MAX_RESTORE_BYTES must be an integer >= 1024")
    if archive_path.stat().st_size > int(raw_limit):
        raise RuntimeError("backup archive exceeds restore size limit")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = _safe_members(archive)
        by_name = {member.name.rstrip("/"): member for member in members}
        manifest_member = by_name["backup-manifest.json"]
        if not manifest_member.isfile() or manifest_member.size > 4 * 1024 * 1024:
            raise RuntimeError("invalid backup manifest")
        source = archive.extractfile(manifest_member)
        if source is None:
            raise RuntimeError("backup manifest is unreadable")
        manifest = json.load(source)
        if manifest.get("version") not in {1, 2} or not isinstance(manifest.get("files"), list):
            raise RuntimeError("unsupported backup manifest")
        expected: dict[str, dict] = {}
        for entry in manifest["files"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise TypeError("invalid backup manifest entry")
            name = entry["path"]
            relative = PurePosixPath(name)
            if (
                not name
                or relative.is_absolute()
                or ".." in relative.parts
                or name in expected
                or name == "backup-manifest.json"
            ):
                raise RuntimeError("unsafe path in backup manifest")
            expected[name] = entry
        actual = {name for name, member in by_name.items() if member.isfile()}
        if actual - {"backup-manifest.json"} != set(expected):
            raise RuntimeError("archive files do not match backup manifest")
        if manifest["version"] == 2:
            engine = "sqlite" if "booker.db" in expected else "postgresql"
            if manifest.get("db_engine") != engine or not isinstance(manifest.get("archive_id"), str):
                raise RuntimeError("backup manifest database identity mismatch")
            uploads = [entry for entry in manifest["files"] if entry["path"].startswith("uploads/")]
            digest = hashlib.sha256(
                json.dumps(uploads, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if manifest.get("attachments") != {
                "count": len(uploads), "bytes": sum(entry["size"] for entry in uploads),
                "identity_sha256": digest,
            }:
                raise RuntimeError("backup manifest attachment identity mismatch")
        for name, entry in expected.items():
            member = by_name[name]
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"archive file is unreadable: {name}")
            digest = hashlib.sha256()
            size = 0
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
            if size != entry.get("size") or digest.hexdigest() != entry.get("sha256"):
                raise RuntimeError(f"archive checksum mismatch: {name}")


def extract_and_verify(archive_path: Path, target: Path) -> None:
    if target.exists():
        raise RuntimeError(f"restore target must not exist: {target}")
    verify_archive(archive_path)
    target.mkdir(parents=True, mode=0o700)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = _safe_members(archive)
            if "booker.db" not in {member.name.rstrip("/") for member in members}:
                raise RuntimeError("SQLite restore archive has no booker.db")
            archive.extractall(target, members=members, filter="data")
        manifest_path = target / "backup-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("version") not in {1, 2} or not isinstance(manifest.get("files"), list):
            raise RuntimeError("unsupported backup manifest")
        for entry in manifest["files"]:
            relative = PurePosixPath(str(entry["path"]))
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("unsafe path in backup manifest")
            restored = target.joinpath(*relative.parts)
            if not restored.is_file():
                raise RuntimeError(f"restored file is missing: {relative}")
            if restored.stat().st_size != int(entry["size"]) or _sha256(restored) != entry["sha256"]:
                raise RuntimeError(f"restored file checksum mismatch: {relative}")
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def verify_sqlite_restore(path: Path) -> None:
    source_uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("restored SQLite integrity_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("restored SQLite foreign_key_check failed")
        connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()


def write_pg_service(destination: Path) -> None:
    raw = os.environ.get("BOOKER_DATABASE_URL", "")
    normalized = raw.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgres+psycopg://", "postgresql://", 1
    )
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname or not parsed.path[1:]:
        raise RuntimeError("invalid PostgreSQL BOOKER_DATABASE_URL")
    values = {
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": unquote(parsed.path[1:]),
    }
    allowed_query = {"sslmode", "sslrootcert", "sslcert", "sslkey", "connect_timeout"}
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key in allowed_query:
            values[key] = value
    if not values["user"]:
        raise RuntimeError("PostgreSQL user is required")
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise RuntimeError(f"newline is not allowed in PostgreSQL service field: {key}")
    content = ["[booker_backup]", *(f"{key}={value}" for key, value in values.items())]
    destination.write_text("\n".join(content) + "\n", encoding="utf-8")
    destination.chmod(0o600)


def read_environment_value(path: Path, key: str) -> str:
    if not path.is_file():
        raise RuntimeError(f"environment file is missing: {path}")
    found: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, raw_value = line.partition("=")
        if separator and name.strip() == key:
            parts = shlex.split(raw_value.strip(), posix=True)
            if len(parts) != 1:
                raise RuntimeError(f"invalid value for {key} in {path}")
            found = parts[0]
    if not found:
        raise RuntimeError(f"{key} is missing from {path}")
    return found


def validate_restore_target(target: Path) -> Path:
    canonical = target.resolve(strict=False)
    tmp_root = Path("/tmp").resolve()
    if canonical == tmp_root or tmp_root not in canonical.parents:
        raise RuntimeError("restore target must resolve under /tmp")
    production = Path("/opt/booker/data").resolve(strict=False)
    if canonical == production or production in canonical.parents:
        raise RuntimeError("production data path cannot be a restore target")
    if canonical.exists():
        raise RuntimeError(f"restore target must not exist: {canonical}")
    return canonical


def main() -> None:
    command, *args = sys.argv[1:]
    if command == "sqlite-backup" and len(args) == 2:
        sqlite_backup(Path(args[0]), Path(args[1]))
    elif command == "snapshot-uploads" and len(args) == 2:
        snapshot_uploads(Path(args[0]), Path(args[1]))
    elif command == "manifest" and len(args) == 1:
        write_manifest(Path(args[0]))
    elif command == "extract-verify" and len(args) == 2:
        extract_and_verify(Path(args[0]), Path(args[1]))
    elif command == "verify-archive" and len(args) == 1:
        verify_archive(Path(args[0]))
    elif command == "sqlite-verify" and len(args) == 1:
        verify_sqlite_restore(Path(args[0]))
    elif command == "pg-service" and len(args) == 1:
        write_pg_service(Path(args[0]))
    elif command == "env-value" and len(args) == 2:
        print(read_environment_value(Path(args[0]), args[1]))
    elif command == "validate-restore-target" and len(args) == 1:
        print(validate_restore_target(Path(args[0])))
    else:
        raise SystemExit("invalid backup_support command")


if __name__ == "__main__":
    main()
