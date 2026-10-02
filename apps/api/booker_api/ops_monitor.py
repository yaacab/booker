"""Local, read-only operations detector. No network alert transport."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import (
    EmailOutbox,
    ReconciliationDiscrepancy,
    ReconciliationRun,
    SupportMessage,
    SupportTicket,
)
from booker_api.ops_http import PREFIX
from booker_api.support_sla import support_response_due_at

MAX_HTTP_EVENTS = 20_000
MAX_ROUTE_LABELS = 128
MAX_STATE_BYTES = 65_536


@dataclass(frozen=True)
class Signal:
    key: str
    severity: str
    value: int


def _age_seconds(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((now - value.astimezone(timezone.utc)).total_seconds()))


def http_signals(lines: list[str], allowed_routes: set[str]) -> list[Signal]:
    errors: Counter[str] = Counter()
    slow: Counter[str] = Counter()
    threshold_ms = settings.ops_slow_request_ms
    for line in lines[-MAX_HTTP_EVENTS:]:
        if not line.startswith(PREFIX):
            continue
        try:
            event = json.loads(line[len(PREFIX):])
            route = event["route"]
            status = int(event["status"])
            latency = int(event["latency_ms"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        if route not in allowed_routes and route != "unmatched":
            continue
        if len(errors.keys() | slow.keys()) >= MAX_ROUTE_LABELS - 1 and route not in errors and route not in slow:
            route = "other"
        if 500 <= status <= 599:
            errors[route] += 1
        if latency >= threshold_ms:
            slow[route] += 1
    found = []
    for route, count in errors.items():
        if count >= settings.ops_http_5xx_threshold:
            found.append(Signal(f"http_5xx:{route}", "critical", count))
    for route, count in slow.items():
        if count >= settings.ops_slow_count_threshold:
            found.append(Signal(f"http_slow:{route}", "warning", count))
    return found


def database_snapshot(db: Session, now: datetime) -> dict[str, int | None]:
    pending = db.query(func.count(EmailOutbox.id)).filter(
        EmailOutbox.status.in_(("pending", "failed", "sending"))
    ).scalar() or 0
    oldest = db.query(func.min(EmailOutbox.created_at)).filter(
        EmailOutbox.status.in_(("pending", "failed", "sending"))
    ).scalar()
    repeat_failures = db.query(func.count(EmailOutbox.id)).filter(
        EmailOutbox.status == "failed",
        EmailOutbox.attempts >= settings.ops_outbox_terminal_attempts,
    ).scalar() or 0
    support_email_uncertain = db.query(func.count(EmailOutbox.id)).filter(
        EmailOutbox.template == "support.first_response_overdue",
        EmailOutbox.status == "uncertain",
    ).scalar() or 0
    open_discrepancies = db.query(func.count(ReconciliationDiscrepancy.id)).filter(
        ReconciliationDiscrepancy.status == "open"
    ).scalar() or 0
    latest_attempt = db.query(ReconciliationRun.status).order_by(
        ReconciliationRun.received_at.desc(), ReconciliationRun.id.desc()
    ).first()
    latest_run = db.query(func.max(ReconciliationRun.completed_at)).scalar()
    operator_responded = db.query(SupportMessage.id).filter(
        SupportMessage.ticket_id == SupportTicket.id,
        SupportMessage.author_kind == "operator",
    ).exists()
    support_overdue = db.query(func.count(SupportTicket.id)).filter(
        SupportTicket.response_due_at.is_not(None),
        SupportTicket.response_due_at <= now,
        SupportTicket.status.notin_(("closed", "resolved")),
        ~operator_responded,
    ).scalar() or 0
    calendar_ok = all(
        support_response_due_at(code, minutes, started_at=now) is not None
        for code, minutes in (("event_day_no_show", 30), ("paid_not_confirmed", 120))
    )
    return {
        "outbox_backlog": int(pending),
        "outbox_oldest_seconds": _age_seconds(oldest, now),
        "outbox_repeat_failures": int(repeat_failures),
        "support_email_uncertain": int(support_email_uncertain),
        "reconciliation_open": int(open_discrepancies),
        "reconciliation_failed_runs": int(bool(latest_attempt and latest_attempt[0] == "failed")),
        "reconciliation_last_completed_age_seconds": _age_seconds(latest_run, now),
        "support_overdue_unanswered": int(support_overdue),
        "support_sla_calendar_unavailable": int(not calendar_ok),
    }


def _read_evidence(path: Path, kind: str) -> tuple[str, datetime | None, dict]:
    if path.is_symlink():
        return "invalid", None, {}
    if not path.exists():
        return "missing", None, {}
    if not path.is_file() or path.stat().st_size > 8192:
        return "invalid", None, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("kind") != kind or payload.get("version") not in {1, 2}:
            return "invalid", None, {}
        status = payload["status"]
        at = datetime.fromisoformat(payload["at"])
        if status not in {"ok", "failed", "unknown"} or at.tzinfo is None:
            return "invalid", None, {}
        if payload["version"] == 1 and status == "ok":
            status = "unknown"
        return status, at.astimezone(timezone.utc), payload
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return "invalid", None, {}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_snapshot(backup_dir: Path, now: datetime) -> dict[str, int | str | None]:
    backup_status, backup_at, backup = _read_evidence(backup_dir / ".ops-backup.json", "backup")
    restore_status, restore_at, restore = _read_evidence(backup_dir / ".ops-restore.json", "restore")
    archives = [
        path
        for pattern in ("booker-*.bke", "booker-*.tar.gz")
        for path in backup_dir.glob(pattern)
        if path.is_file() and not path.is_symlink()
    ] if backup_dir.is_dir() else []
    latest_archive = max(archives, key=lambda path: path.stat().st_mtime_ns, default=None)
    archive_age = _age_seconds(
        datetime.fromtimestamp(latest_archive.stat().st_mtime, timezone.utc) if latest_archive else None,
        now,
    )
    backup_binding = "unknown"
    unbound_archive = False
    if backup_status == "ok" and backup.get("version") == 2:
        name = backup.get("archive")
        if not isinstance(name, str) or not name.startswith("booker-") or Path(name).name != name:
            backup_binding = "mismatch"
        else:
            archive = backup_dir / name
            if (
                archive.is_symlink() or not archive.is_file()
                or archive.stat().st_size != backup.get("archive_bytes")
                or _digest(archive) != backup.get("archive_sha256")
            ):
                backup_binding = "mismatch"
            else:
                backup_binding = "ok"
                bound_time = datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc)
                archive_age = _age_seconds(bound_time, now)
                sidecar_status, _sidecar_at, sidecar = _read_evidence(
                    archive.with_name(archive.name + ".evidence.json"), "backup"
                )
                if sidecar_status != "ok" or sidecar != backup:
                    backup_binding = "mismatch"
                unbound_archive = any(
                    other != archive and other.stat().st_mtime_ns >= archive.stat().st_mtime_ns
                    for other in archives
                )
    configured_engine = "postgresql" if settings.database_url.startswith("postgres") else "sqlite"
    engine_mismatch = bool(
        backup_status == "ok" and backup.get("db_engine") != configured_engine
    )
    restore_mismatch = bool(
        backup_status == "ok" and restore_status == "ok" and (
            backup.get("archive_id") != restore.get("archive_id")
            or backup.get("archive_sha256") != restore.get("archive_sha256")
            or backup.get("db_engine") != restore.get("db_engine")
            or restore.get("verifier_version") != "booker-restore-v2"
        )
    )
    return {
        "backup_status": backup_status,
        "backup_last_attempt_age_seconds": _age_seconds(backup_at, now),
        "backup_archive_age_seconds": archive_age,
        "backup_binding": backup_binding,
        "backup_unbound_archive": int(unbound_archive),
        "db_engine_mismatch": int(engine_mismatch),
        "restore_status": restore_status,
        "restore_age_seconds": _age_seconds(restore_at, now),
        "restore_mismatch": int(restore_mismatch),
        "backup_not_restored": int(backup_status == "ok" and (restore_status != "ok" or restore_mismatch)),
    }


def snapshot_signals(snapshot: dict[str, int | str | None]) -> list[Signal]:
    signals: list[Signal] = []
    if snapshot.get("backup_status") in {"failed", "invalid"}:
        signals.append(Signal("backup_failed", "critical", 1))
    if snapshot.get("backup_status") == "missing":
        signals.append(Signal("backup_evidence_missing", "warning", 1))
    if snapshot.get("backup_status") == "unknown":
        signals.append(Signal("backup_evidence_legacy", "warning", 1))
    if snapshot.get("backup_binding") == "mismatch":
        signals.append(Signal("backup_archive_mismatch", "critical", 1))
    if int(snapshot.get("backup_unbound_archive") or 0):
        signals.append(Signal("backup_unbound_archive", "warning", 1))
    if int(snapshot.get("db_engine_mismatch") or 0):
        signals.append(Signal("db_engine_mismatch", "critical", 1))
    backup_age = snapshot.get("backup_archive_age_seconds")
    if backup_age is None or int(backup_age) > settings.ops_backup_max_age_hours * 3600:
        signals.append(Signal("backup_stale", "critical", int(backup_age or -1)))
    if snapshot.get("restore_status") in {"failed", "invalid"}:
        signals.append(Signal("restore_failed", "critical", 1))
    if snapshot.get("restore_status") == "unknown":
        signals.append(Signal("restore_evidence_legacy", "warning", 1))
    if int(snapshot.get("restore_mismatch") or 0):
        signals.append(Signal("restore_mismatch", "critical", 1))
    if int(snapshot.get("backup_not_restored") or 0):
        signals.append(Signal("backup_not_restored", "warning", 1))
    restore_age = snapshot.get("restore_age_seconds")
    if restore_age is None or int(restore_age) > settings.ops_restore_max_age_days * 86400:
        signals.append(Signal("restore_stale", "warning", int(restore_age or -1)))
    backlog = int(snapshot.get("outbox_backlog") or 0)
    if backlog >= settings.ops_outbox_backlog_threshold:
        signals.append(Signal("outbox_backlog", "warning", backlog))
    oldest = snapshot.get("outbox_oldest_seconds")
    if oldest is not None and int(oldest) > settings.ops_outbox_oldest_minutes * 60:
        signals.append(Signal("outbox_oldest", "warning", int(oldest)))
    failures = int(snapshot.get("outbox_repeat_failures") or 0)
    if failures:
        signals.append(Signal("outbox_repeat_failure", "critical", failures))
    uncertain_support_email = int(snapshot.get("support_email_uncertain") or 0)
    if uncertain_support_email:
        signals.append(Signal("support_email_uncertain", "warning", uncertain_support_email))
    mismatches = int(snapshot.get("reconciliation_open") or 0)
    if mismatches:
        signals.append(Signal("reconciliation_mismatch", "critical", mismatches))
    failed_runs = int(snapshot.get("reconciliation_failed_runs") or 0)
    if failed_runs:
        signals.append(Signal("reconciliation_run_failed", "critical", failed_runs))
    last_age = snapshot.get("reconciliation_last_completed_age_seconds")
    if settings.ops_expect_reconciliation and (
        last_age is None or int(last_age) > settings.ops_reconciliation_max_age_hours * 3600
    ):
        signals.append(Signal("reconciliation_stale", "warning", int(last_age or -1)))
    support_overdue = int(snapshot.get("support_overdue_unanswered") or 0)
    if support_overdue:
        signals.append(Signal("support_overdue_unanswered", "warning", support_overdue))
    if int(snapshot.get("support_sla_calendar_unavailable") or 0):
        signals.append(Signal("support_sla_calendar_unavailable", "warning", 1))
    return signals


def transitions(
    active: list[Signal], state: dict, now: datetime, cooldown_seconds: int
) -> tuple[list[dict], dict]:
    epoch = int(now.timestamp())
    current = {signal.key: signal for signal in active}
    previous = state.get("alerts", {}) if isinstance(state, dict) else {}
    if not isinstance(previous, dict):
        previous = {}
    events = []
    next_state = {}
    for key, signal in sorted(current.items()):
        prior = previous.get(key, {})
        last = int(prior.get("last_emitted", 0)) if isinstance(prior, dict) else 0
        action = "firing" if not isinstance(prior, dict) or not prior.get("active") else "reminder"
        if action == "firing" or epoch - last >= cooldown_seconds:
            events.append({"key": key, "severity": signal.severity, "state": action,
                           "value": signal.value, "at": epoch})
            last = epoch
        next_state[key] = {"active": True, "last_emitted": last, "seen": epoch}
    for key, prior in previous.items():
        if key in current or not isinstance(prior, dict):
            continue
        if prior.get("active"):
            events.append({"key": key, "severity": "info", "state": "recovered",
                           "value": 0, "at": epoch})
        previous_seen = int(prior.get("seen", 0))
        if epoch - previous_seen < 7 * 86400:
            next_state[key] = {"active": False, "last_emitted": epoch, "seen": previous_seen}
    trimmed = dict(sorted(next_state.items(), key=lambda item: item[1]["seen"], reverse=True)[:256])
    return events, {"version": 1, "alerts": trimmed}


def run_cycle(
    signals: list[Signal], *, state_file: Path, now: datetime,
    transport: str = "disabled", test_sink: Path | None = None,
) -> list[dict]:
    if transport not in {"disabled", "test_file"}:
        raise ValueError("unsupported alert transport")
    if settings.runtime_env == "production" and transport != "disabled":
        raise ValueError("production alert transport has not been approved")
    if not state_file.is_absolute() or state_file.parent.is_symlink():
        raise ValueError("operations state path must be absolute and private")
    state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_file = state_file.with_suffix(state_file.suffix + ".lock")
    descriptor = os.open(lock_file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if state_file.is_symlink() or (state_file.exists() and state_file.stat().st_size > MAX_STATE_BYTES):
            raise ValueError("unsafe operations state")
        state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
        events, next_state = transitions(
            signals, state, now, settings.ops_alert_cooldown_minutes * 60
        )
        if transport == "test_file":
            if test_sink is None or not test_sink.is_absolute() or test_sink.is_symlink():
                raise ValueError("test sink must be an absolute regular path")
            sink_fd = os.open(test_sink, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            try:
                for event in events:
                    os.write(sink_fd, (json.dumps(event, separators=(",", ":")) + "\n").encode())
            finally:
                os.close(sink_fd)
        fd, temporary = tempfile.mkstemp(prefix=".ops-state-", dir=state_file.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(next_state, output, separators=(",", ":"), sort_keys=True)
            os.replace(temporary, state_file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return events
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _journal_lines(now: datetime) -> list[str]:
    since = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S UTC")
    result = subprocess.run(
        ["journalctl", "--unit=booker-api", "--since", since, "--output=cat",
         "--no-pager", "-n", str(MAX_HTTP_EVENTS)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    return result.stdout.splitlines()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Booker operations checker")
    parser.add_argument("--backup-dir", type=Path, default=Path("/var/backups/booker"))
    parser.add_argument("--state-file", type=Path, default=Path("/var/lib/booker/ops-alert-state.json"))
    parser.add_argument("--journal-file", type=Path)
    parser.add_argument("--test-sink", type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    from booker_api.db import SessionLocal
    from booker_api.main import app

    allowed_routes = {route.path for route in app.routes if hasattr(route, "path")}
    source_failed = False
    try:
        lines = (
            args.journal_file.read_text(encoding="utf-8").splitlines()[-MAX_HTTP_EVENTS:]
            if args.journal_file else _journal_lines(now)
        )
    except (OSError, subprocess.SubprocessError):
        lines = []
        source_failed = True
    signals = http_signals(lines, allowed_routes)
    if source_failed:
        signals.append(Signal("monitor_http_source_failed", "critical", 1))
    if not args.journal_file:
        if len(lines) >= MAX_HTTP_EVENTS:
            signals.append(Signal("monitor_http_sample_saturated", "warning", len(lines)))
        try:
            service = subprocess.run(
                ["systemctl", "is-active", "--quiet", "booker-api.service"],
                check=False, timeout=5,
            )
            if service.returncode != 0:
                signals.append(Signal("api_service_inactive", "critical", 1))
        except (OSError, subprocess.SubprocessError):
            signals.append(Signal("monitor_service_source_failed", "critical", 1))
    try:
        with SessionLocal() as db:
            snapshot = database_snapshot(db, now)
    except (OSError, SQLAlchemyError, ValueError):
        snapshot = {}
        signals.append(Signal("monitor_database_failed", "critical", 1))
    try:
        snapshot.update(evidence_snapshot(args.backup_dir, now))
    except OSError:
        signals.append(Signal("monitor_backup_source_failed", "critical", 1))
    signals.extend(snapshot_signals(snapshot))
    events = run_cycle(
        signals, state_file=args.state_file, now=now,
        transport=settings.ops_alert_transport, test_sink=args.test_sink,
    )
    print(json.dumps({"active": len(signals), "transitions": len(events)}, sort_keys=True))


if __name__ == "__main__":
    main()
