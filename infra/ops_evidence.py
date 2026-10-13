"""Write tiny, private backup/restore outcome markers without paths or PII."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def record(path: Path, kind: str, status: str, *, at: datetime | None = None) -> None:
    if kind not in {"backup", "restore"} or status not in {"ok", "failed"}:
        raise ValueError("invalid operations evidence")
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise ValueError("evidence path must be absolute and must not be a symlink")
    moment = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = {"version": 1, "kind": kind, "status": status, "at": moment.isoformat()}
    descriptor, temp_name = tempfile.mkstemp(prefix=".ops-evidence-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, separators=(",", ":"), sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: ops_evidence.py <absolute-file> <backup|restore> <ok|failed>")
    try:
        record(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    except (OSError, ValueError):
        raise SystemExit("ops evidence write failed") from None


if __name__ == "__main__":
    main()
