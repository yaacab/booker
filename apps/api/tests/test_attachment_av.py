"""Real HTTP attachment lifecycle against a deterministic fake clamd Unix socket."""

from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from socketserver import BaseRequestHandler, UnixStreamServer
from struct import unpack
from threading import Thread

import pytest

from booker_api.config import settings
from booker_api.models import DealAttachment
from booker_api.security import now
from tests.conftest import auth_header
from tests.test_admin import _promote_admin
from tests.test_attachments import MINIMAL_PDF
from tests.test_payments import _awaiting_payment
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


@contextmanager
def fake_clamd(path: Path, reply: bytes):
    received: list[bytes] = []

    class Handler(BaseRequestHandler):
        def handle(self):
            command = self.request.recv(10)
            assert command == b"zINSTREAM\0"
            chunks = []
            while True:
                length = unpack(">I", self._read_exact(4))[0]
                if length == 0:
                    break
                chunks.append(self._read_exact(length))
            received.append(b"".join(chunks))
            self.request.sendall(reply)

        def _read_exact(self, size: int) -> bytes:
            data = bytearray()
            while len(data) < size:
                part = self.request.recv(size - len(data))
                if not part:
                    raise AssertionError("incomplete scanner stream")
                data.extend(part)
            return bytes(data)

    server = UnixStreamServer(str(path), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _uploaded(client, tmp_path, monkeypatch):
    ctx = _awaiting_payment(client)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    raw = MINIMAL_PDF + b"attachment-av-e2e"
    response = client.post(
        f"/bookings/{ctx['booking_id']}/attachments",
        files={"file": ("av.pdf", raw, "application/pdf")},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert response.status_code == 200, response.text
    admin = _promote_admin(client, "av-admin@booker.test", totp=TEST_TOTP_SECRET)
    return ctx, admin, response.json()["id"], raw


def _scan(client, attachment_id: str, token: str):
    return client.post(
        f"/admin/attachments/{attachment_id}/scan",
        json={"totp": totp_code()},
        headers=auth_header(token),
    )


def _download(client, ctx, attachment_id: str):
    return client.get(
        f"/bookings/{ctx['booking_id']}/attachments/{attachment_id}/download",
        headers=auth_header(ctx["customer"]["token"]),
    )


@pytest.mark.parametrize(
    ("reply", "expected_status", "expected_scan"),
    [
        (b"stream: OK\0", 200, "clean"),
        (b"stream: Eicar-Test-Signature FOUND\0", 200, "blocked"),
        (b"stream: size limit exceeded ERROR\0", 503, "quarantined"),
        (b"stream: OK", 503, "quarantined"),
    ],
)
def test_clamd_verdict_or_error_is_fail_closed(
    client, SessionLocal, tmp_path, monkeypatch, reply, expected_status, expected_scan
):
    ctx, admin, attachment_id, raw = _uploaded(client, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "av_provider", "clamd")
    socket_path = tmp_path / "clamd.sock"
    monkeypatch.setattr(settings, "av_clamd_socket", str(socket_path))
    with fake_clamd(socket_path, reply) as received:
        result = _scan(client, attachment_id, admin["token"])
    assert result.status_code == expected_status, result.text
    assert received == [raw]
    with SessionLocal() as db:
        row = db.get(DealAttachment, attachment_id)
        assert row.scan_status == expected_scan
        assert row.av_verdict_provider == ("clamd" if expected_status == 200 else None)
        assert row.av_verdict_sha256 == (row.sha256 if expected_status == 200 else None)
    download = _download(client, ctx, attachment_id)
    assert download.status_code == (200 if expected_scan == "clean" else 409)
    if expected_scan == "clean":
        assert download.content == raw
    if expected_scan == "blocked":
        override = client.post(
            f"/admin/attachments/{attachment_id}/scan-decision",
            json={"scan_status": "clean", "totp": totp_code()},
            headers=auth_header(admin["token"]),
        )
        assert override.status_code == 409


def test_missing_clamd_keeps_quarantine_and_manual_clean_is_disabled(
    client, SessionLocal, tmp_path, monkeypatch
):
    ctx, admin, attachment_id, _ = _uploaded(client, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "av_provider", "clamd")
    monkeypatch.setattr(settings, "av_clamd_socket", str(tmp_path / "missing.sock"))
    denied = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "override", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert denied.status_code == 409
    unavailable = _scan(client, attachment_id, admin["token"])
    assert unavailable.status_code == 503
    with SessionLocal() as db:
        assert db.get(DealAttachment, attachment_id).scan_status == "quarantined"
    assert _download(client, ctx, attachment_id).status_code == 409


def test_old_manual_clean_requires_rescan_after_clamd_enabled(
    client, SessionLocal, tmp_path, monkeypatch
):
    ctx, admin, attachment_id, raw = _uploaded(client, tmp_path, monkeypatch)
    manual = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "legacy manual", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert manual.status_code == 200
    assert _download(client, ctx, attachment_id).status_code == 200
    monkeypatch.setattr(settings, "av_provider", "clamd")
    assert _download(client, ctx, attachment_id).status_code == 409
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert room.status_code == 200
    assert any(
        item.get("id") == attachment_id and item["downloadable"] is False
        for item in room.json()["documents"]
    )
    socket_path = tmp_path / "clamd.sock"
    monkeypatch.setattr(settings, "av_clamd_socket", str(socket_path))
    with fake_clamd(socket_path, b"stream: OK\0"):
        result = _scan(client, attachment_id, admin["token"])
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        assert db.get(DealAttachment, attachment_id).av_verdict_provider == "clamd"
    assert _download(client, ctx, attachment_id).content == raw


def test_av_scan_requires_admin_and_totp(client, tmp_path, monkeypatch):
    ctx, admin, attachment_id, _ = _uploaded(client, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "av_provider", "clamd")
    path = f"/admin/attachments/{attachment_id}/scan"
    assert client.post(path, json={"totp": totp_code()}).status_code == 401
    assert client.post(
        path,
        json={"totp": totp_code()},
        headers=auth_header(ctx["customer"]["token"]),
    ).status_code == 403
    assert client.post(path, json={}, headers=auth_header(admin["token"])).status_code == 403


def test_failed_rescan_of_legacy_clean_remains_quarantined(
    client, SessionLocal, tmp_path, monkeypatch
):
    ctx, admin, attachment_id, _ = _uploaded(client, tmp_path, monkeypatch)
    manual = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "legacy", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert manual.status_code == 200
    monkeypatch.setattr(settings, "av_provider", "clamd")
    monkeypatch.setattr(settings, "av_clamd_socket", str(tmp_path / "missing.sock"))
    assert _scan(client, attachment_id, admin["token"]).status_code == 503
    with SessionLocal() as db:
        row = db.get(DealAttachment, attachment_id)
        assert row.scan_status == "quarantined"
        assert row.av_verdict_provider is None
    assert _download(client, ctx, attachment_id).status_code == 409


def test_manual_block_during_scan_cannot_be_overwritten(
    client, SessionLocal, tmp_path, monkeypatch
):
    from booker_api.routers import admin as admin_router

    ctx, admin, attachment_id, _ = _uploaded(client, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "av_provider", "clamd")

    def block_while_scanning(_raw, **_kwargs):
        blocked = client.post(
            f"/admin/attachments/{attachment_id}/scan-decision",
            json={"scan_status": "blocked", "totp": totp_code()},
            headers=auth_header(admin["token"]),
        )
        assert blocked.status_code == 200, blocked.text
        return "clean"

    monkeypatch.setattr(admin_router, "scan_clamd", block_while_scanning)
    result = _scan(client, attachment_id, admin["token"])
    assert result.status_code == 409
    with SessionLocal() as db:
        row = db.get(DealAttachment, attachment_id)
        assert row.scan_status == "blocked"
        assert row.av_scan_token is None
    assert _download(client, ctx, attachment_id).status_code == 409


def test_second_scan_cannot_finish_first_attempt(client, SessionLocal, tmp_path, monkeypatch):
    from booker_api.routers import admin as admin_router

    ctx, admin, attachment_id, _ = _uploaded(client, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "av_provider", "clamd")
    calls = 0

    def overlapping_scan(_raw, **_kwargs):
        nonlocal calls
        calls += 1
        duplicate = _scan(client, attachment_id, admin["token"])
        assert duplicate.status_code == 409, duplicate.text
        return "clean"

    monkeypatch.setattr(admin_router, "scan_clamd", overlapping_scan)
    result = _scan(client, attachment_id, admin["token"])
    assert result.status_code == 200, result.text
    assert calls == 1
    with SessionLocal() as db:
        row = db.get(DealAttachment, attachment_id)
        assert row.av_scan_token is None
        assert row.av_verdict_sha256 == row.sha256
    assert _download(client, ctx, attachment_id).status_code == 200


def test_stale_scan_attempt_can_be_reclaimed(client, SessionLocal, tmp_path, monkeypatch):
    ctx, admin, attachment_id, _ = _uploaded(client, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "av_provider", "clamd")
    with SessionLocal() as db:
        row = db.get(DealAttachment, attachment_id)
        row.av_scan_token = "abandoned-attempt"
        row.av_scan_started_at = now() - timedelta(minutes=2)
        db.commit()
    socket_path = tmp_path / "clamd.sock"
    monkeypatch.setattr(settings, "av_clamd_socket", str(socket_path))
    with fake_clamd(socket_path, b"stream: OK\0"):
        result = _scan(client, attachment_id, admin["token"])
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        row = db.get(DealAttachment, attachment_id)
        assert row.av_scan_token is None
        assert row.av_verdict_provider == "clamd"
    assert _download(client, ctx, attachment_id).status_code == 200
