"""Aggregate local diagnostics, privacy, and alert state transitions."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from booker_api.config import settings
from booker_api.models import (
    EmailOutbox,
    ReconciliationDiscrepancy,
    ReconciliationRun,
    SupportMessage,
    SupportTicket,
    User,
)
from booker_api.ops_http import OpsHttpMiddleware, metric_line
from booker_api.ops_monitor import (
    Signal,
    database_snapshot,
    evidence_snapshot,
    http_signals,
    run_cycle,
    snapshot_signals,
)


def test_http_metric_uses_route_template_and_does_not_change_response(monkeypatch):
    app = FastAPI()
    app.add_middleware(OpsHttpMiddleware)

    @app.get("/items/{item_id}")
    def item(item_id: str):
        return PlainTextResponse("ok")

    recorded = []
    monkeypatch.setattr("booker_api.ops_http.logger.info", recorded.append)
    with TestClient(app) as client:
        response = client.get("/items/secret-123?email=private@example.org")
    assert response.status_code == 200
    assert len(recorded) == 1
    assert json.loads(recorded[0].split(" ", 1)[1])["route"] == "/items/{item_id}"
    assert "secret-123" not in recorded[0]
    assert "private@example.org" not in recorded[0]

    monkeypatch.setattr("booker_api.ops_http.logger.info", lambda _line: 1 / 0)
    with TestClient(app) as client:
        assert client.get("/items/another-secret").status_code == 200


def test_http_thresholds_and_untrusted_route_labels(monkeypatch):
    monkeypatch.setattr("booker_api.ops_monitor.settings.ops_http_5xx_threshold", 2)
    monkeypatch.setattr("booker_api.ops_monitor.settings.ops_slow_count_threshold", 2)
    allowed = {"/items/{item_id}"}
    line = metric_line({"route": SimpleNamespace(path="/items/{item_id}"), "method": "GET"}, 503, 2100)
    malicious = 'BOOKER_HTTP_METRIC {"route":"/items/private-id","status":503,"latency_ms":3000}'
    signals = http_signals([line, line, malicious], allowed)
    assert {signal.key for signal in signals} == {
        "http_5xx:/items/{item_id}", "http_slow:/items/{item_id}"
    }
    assert all("private-id" not in signal.key for signal in signals)


def test_outbox_and_reconciliation_are_aggregate_only(SessionLocal):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        run = ReconciliationRun(
            provider="test", merchant="private-merchant", report_id="private-report",
            content_sha256="a" * 64, period_start=now - timedelta(days=1), period_end=now,
            status="failed", received_at=now - timedelta(hours=1),
        )
        db.add(run)
        db.flush()
        db.add(ReconciliationDiscrepancy(run_id=run.id, fingerprint="b" * 64, kind="amount", status="open"))
        db.add(EmailOutbox(
            idempotency_key="private-key", recipient_email="private@example.org",
            subject="Private subject", body="Private body", status="failed", attempts=3,
            created_at=now - timedelta(hours=2),
        ))
        db.commit()
        snapshot = database_snapshot(db, now)
    assert snapshot["outbox_backlog"] == 1
    assert snapshot["outbox_repeat_failures"] == 1
    assert snapshot["reconciliation_open"] == 1
    assert snapshot["reconciliation_failed_runs"] == 1
    serialized = json.dumps(snapshot)
    assert "private" not in serialized


def test_support_overdue_monitor_aggregates_without_ticket_data(SessionLocal, monkeypatch):
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        user = User(email="private-support@example.org", full_name="Private Owner",
                    password_hash="test")
        db.add(user)
        db.flush()
        overdue = SupportTicket(author_user_id=user.id, category="incident",
                                subject="Private incident", body="Private details", status="open",
                                priority="urgent", urgency_code="event_day_no_show",
                                response_due_at=now - timedelta(minutes=1))
        answered = SupportTicket(author_user_id=user.id, category="incident",
                                 subject="Answered", body="Private details", status="open",
                                 priority="urgent", urgency_code="event_day_no_show",
                                 response_due_at=now - timedelta(minutes=2))
        db.add_all([overdue, answered])
        db.flush()
        db.add(SupportMessage(ticket_id=answered.id, author_user_id=user.id,
                              author_kind="operator", body="Private reply",
                              idempotency_key_hash="a" * 64, request_fingerprint="b" * 64,
                              created_at=now - timedelta(minutes=1)))
        db.commit()
        snapshot = database_snapshot(db, now)
    assert snapshot["support_overdue_unanswered"] == 1
    assert snapshot["support_sla_calendar_unavailable"] == 0
    assert Signal("support_overdue_unanswered", "warning", 1) in snapshot_signals(snapshot)
    assert "private" not in json.dumps(snapshot).lower()

    monkeypatch.setattr(settings, "support_sla_schedule_json", "")
    with SessionLocal() as db:
        bad_snapshot = database_snapshot(db, now)
    assert bad_snapshot["support_sla_calendar_unavailable"] == 1
    assert Signal("support_sla_calendar_unavailable", "warning", 1) in snapshot_signals(bad_snapshot)


def test_evidence_age_and_state_cooldown_recovery(tmp_path):
    now = datetime.now(timezone.utc)
    archive = tmp_path / "booker-example.tar.gz"
    archive.write_bytes(b"example")
    old = (now - timedelta(days=31)).timestamp()
    os.utime(archive, (old, old))
    snapshot = evidence_snapshot(tmp_path, now)
    keys = {signal.key for signal in snapshot_signals(snapshot)}
    assert {"backup_evidence_missing", "backup_stale", "restore_stale"} <= keys
    state = tmp_path / "ops-state.json"
    signal = [Signal("backup_stale", "critical", 1)]
    first = run_cycle(signal, state_file=state, now=now)
    second = run_cycle(signal, state_file=state, now=now + timedelta(minutes=1))
    recovered = run_cycle([], state_file=state, now=now + timedelta(minutes=2))
    assert [event["state"] for event in first] == ["firing"]
    assert second == []
    assert [event["state"] for event in recovered] == ["recovered"]
    assert state.stat().st_mode & 0o777 == 0o600


def test_test_sink_is_local_only_and_no_public_ops_route(client, tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    sink = tmp_path / "alerts.jsonl"
    events = run_cycle(
        [Signal("outbox_backlog", "warning", 50)],
        state_file=tmp_path / "state.json", now=now,
        transport="test_file", test_sink=sink,
    )
    assert len(events) == 1
    assert json.loads(sink.read_text().splitlines()[0])["key"] == "outbox_backlog"
    assert sink.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr("booker_api.ops_monitor.settings.runtime_env", "production")
    try:
        import pytest

        with pytest.raises(ValueError, match="production alert transport"):
            run_cycle([], state_file=tmp_path / "production.json", now=now,
                      transport="test_file", test_sink=sink)
    finally:
        monkeypatch.setattr("booker_api.ops_monitor.settings.runtime_env", "local")
    assert client.get("/ops/metrics").status_code == 404


def test_failed_backup_wrapper_records_private_failure(tmp_path):
    root = Path(__file__).resolve().parents[3]
    backup_dir = tmp_path / "backups"
    result = subprocess.run(
        [str(root / "infra" / "run-booker-ops-backup.sh")],
        env={
            **os.environ,
            "BOOKER_BACKUP_DIR": str(backup_dir),
            "BOOKER_DATABASE_URL": "sqlite:////tmp/booker-nonexistent.db",
            "BOOKER_BACKUP_FORMAT": "sealed",
            "BOOKER_BACKUP_KEY_FILE": "",
        },
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    marker = backup_dir / ".ops-backup.json"
    assert json.loads(marker.read_text())["status"] == "failed"
    assert marker.stat().st_mode & 0o777 == 0o600
    assert "booker-nonexistent" not in marker.read_text()
