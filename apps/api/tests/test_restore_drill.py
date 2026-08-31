import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 CLI not installed")
def test_restore_drill_script_smoke():
    root = Path(__file__).resolve().parents[3]
    script = root / "infra" / "restore-drill.sh"
    assert script.is_file()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "booker.db"
        subprocess.run(
            ["sqlite3", str(db), "CREATE TABLE users (id TEXT); INSERT INTO users VALUES ('1');"],
            check=True,
        )
        backup_plain = Path(tmp) / "booker-backup.db"
        subprocess.run(["sqlite3", str(db), f".backup '{backup_plain}'"], check=True)
        backup = Path(tmp) / "booker-backup.db.gz"
        subprocess.run(["gzip", "-c", str(backup_plain)], stdout=backup.open("wb"), check=True)
        out = subprocess.run(
            ["bash", str(script), str(backup), str(Path(tmp) / "restore")],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "restore drill OK" in out.stdout
