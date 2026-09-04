import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 CLI not installed")
def test_restore_drill_script_smoke_with_uploads():
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "restore-drill.sh"
    assert script.is_file()
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "stage"
        staging.mkdir()
        db = staging / "booker.db"
        uploads = staging / "uploads"
        uploads.mkdir()
        (uploads / "sample.txt").write_text("attachment", encoding="utf-8")
        subprocess.run(
            ["sqlite3", str(db), "CREATE TABLE users (id TEXT); INSERT INTO users VALUES ('1');"],
            check=True,
        )
        backup = Path(tmp) / "booker-backup.tar.gz"
        with tarfile.open(backup, "w:gz") as archive:
            archive.add(db, arcname="booker.db")
            archive.add(uploads, arcname="uploads")
        out = subprocess.run(
            ["bash", str(script), str(backup), str(Path(tmp) / "restore")],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "restore drill OK" in out.stdout
        assert (Path(tmp) / "restore" / "uploads" / "sample.txt").is_file()


def test_pg_dump_url_strips_psycopg_driver():
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "backup-booker.sh"
    text = script.read_text(encoding="utf-8")
    assert "postgresql+psycopg/postgresql" in text
    assert 'pg_dump "$(pg_url_for_libpq' in text


@pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 CLI not installed")
def test_backup_includes_upload_dir(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "backup-booker.sh"
    db_path = tmp_path / "booker.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "file.bin").write_bytes(b"payload")
    backup_root = tmp_path / "backups"
    subprocess.run(
        ["sqlite3", str(db_path), "CREATE TABLE users (id TEXT); INSERT INTO users VALUES ('1');"],
        check=True,
    )
    env = {
        **dict(__import__("os").environ),
        "BOOKER_DATABASE_URL": f"sqlite:///{db_path}",
        "BOOKER_UPLOAD_DIR": str(upload_dir),
        "BOOKER_BACKUP_DIR": str(backup_root),
    }
    subprocess.run(["bash", str(script)], check=True, env=env)
    archives = list(backup_root.glob("booker-*.tar.gz"))
    assert archives
    with tarfile.open(archives[0], "r:gz") as archive:
        names = archive.getnames()
    assert "booker.db" in names
    assert any(name.startswith("uploads/") for name in names)
