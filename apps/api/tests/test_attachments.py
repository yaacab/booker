from tests.conftest import auth_header
from tests.test_admin import _promote_admin
from tests.test_payments import _awaiting_payment
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code

MINIMAL_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


def test_oversized_declared_attachment_is_rejected_before_multipart_parse(
    client, monkeypatch
):
    from starlette.formparsers import MultiPartParser

    from booker_api.config import settings

    ctx = _awaiting_payment(client)
    monkeypatch.setattr(settings, "max_upload_bytes", 32)

    async def unexpected_parse(_self):
        raise AssertionError("multipart parser must not run for oversized request")

    monkeypatch.setattr(MultiPartParser, "parse", unexpected_parse)
    response = client.post(
        f"/bookings/{ctx['booking_id']}/attachments",
        files={"file": ("large.pdf", b"%PDF" + b"x" * 100_000, "application/pdf")},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert response.status_code == 413


def test_oversized_chunked_attachment_is_rejected_before_multipart_parse(
    client, monkeypatch
):
    from starlette.formparsers import MultiPartParser

    from booker_api.config import settings

    ctx = _awaiting_payment(client)
    monkeypatch.setattr(settings, "max_upload_bytes", 32)

    async def unexpected_parse(_self):
        raise AssertionError("multipart parser must not run for oversized request")

    monkeypatch.setattr(MultiPartParser, "parse", unexpected_parse)
    body = (
        b"--boundary\r\nContent-Disposition: form-data; name=\"file\"; "
        b"filename=\"large.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
        + b"%PDF" + b"x" * 100_000
        + b"\r\n--boundary--\r\n"
    )
    response = client.post(
        f"/bookings/{ctx['booking_id']}/attachments",
        content=iter((body[:200], body[200:])),
        headers={**auth_header(ctx["customer"]["token"]),
                 "Content-Type": "multipart/form-data; boundary=boundary"},
    )
    assert response.status_code == 413


def test_attachment_body_limit_ignores_understated_content_length(client, monkeypatch):
    from starlette.formparsers import MultiPartParser

    from booker_api.config import settings

    ctx = _awaiting_payment(client)
    monkeypatch.setattr(settings, "max_upload_bytes", 32)

    async def unexpected_parse(_self):
        raise AssertionError("multipart parser must not run for oversized request")

    monkeypatch.setattr(MultiPartParser, "parse", unexpected_parse)
    response = client.post(
        f"/bookings/{ctx['booking_id']}/attachments",
        content=b"x" * 100_000,
        headers={**auth_header(ctx["customer"]["token"]),
                 "Content-Type": "multipart/form-data; boundary=boundary",
                 "Content-Length": "1"},
    )
    assert response.status_code == 413


def test_attachment_at_file_size_limit_allows_multipart_overhead(client, tmp_path, monkeypatch):
    from booker_api.config import settings

    ctx = _awaiting_payment(client)
    content = MINIMAL_PDF + b"x" * (128 - len(MINIMAL_PDF))
    monkeypatch.setattr(settings, "max_upload_bytes", len(content))
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    response = client.post(
        f"/bookings/{ctx['booking_id']}/attachments",
        files={"file": ("limit.pdf", content, "application/pdf")},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["size_bytes"] == len(content)


def test_admin_requires_totp_when_enforced(client, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    admin = _promote_admin(client, "2fa-enforced@booker.test")
    res = client.get("/admin/metrics", headers=auth_header(admin["token"]))
    assert res.status_code == 403
    assert "второй фактор" in res.json()["detail"]


def test_admin_with_totp_when_enforced(client, monkeypatch):
    from booker_api.config import settings
    from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers

    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    admin = _promote_admin(client, "2fa-ok@booker.test", totp=TEST_TOTP_SECRET)
    res = client.get("/admin/metrics", headers=admin_totp_headers(admin["token"]))
    assert res.status_code == 200


def test_upload_attachment_scanned_and_listed(client, tmp_path, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    customer = ctx["customer"]
    files = {"file": ("brief.pdf", MINIMAL_PDF, "application/pdf")}
    up = client.post(
        f"/bookings/{booking_id}/attachments",
        files=files,
        headers=auth_header(customer["token"]),
    )
    assert up.status_code == 200
    body = up.json()
    assert body["filename"] == "brief.pdf"
    assert body["scan_status"] == "quarantined"
    assert body["downloadable"] is False
    room = client.get(f"/deal-room/{booking_id}", headers=auth_header(customer["token"]))
    assert room.status_code == 200
    docs = room.json()["documents"]
    kinds = [d["kind"] for d in docs]
    assert "attachment" in kinds
    attachment = next(d for d in docs if d["kind"] == "attachment")
    assert attachment["scan_status"] == "quarantined"
    assert attachment["downloadable"] is False
    blocked_download = client.get(
        f"/bookings/{booking_id}/attachments/{body['id']}/download",
        headers=auth_header(customer["token"]),
    )
    assert blocked_download.status_code == 409
    admin = _promote_admin(client, "scan-admin@booker.test", totp=TEST_TOTP_SECRET)
    scan = client.post(
        f"/admin/attachments/{body['id']}/scan-decision",
        json={"scan_status": "clean", "note": "local signature check", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert scan.status_code == 200
    assert scan.json()["scan_status"] == "clean"
    ok_download = client.get(
        f"/bookings/{booking_id}/attachments/{body['id']}/download",
        headers=auth_header(customer["token"]),
    )
    assert ok_download.status_code == 200
    assert ok_download.content == MINIMAL_PDF


def test_upload_rejects_executable(client, tmp_path, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    files = {"file": ("bad.pdf", b"MZ" + b"\x00" * 32, "application/pdf")}
    res = client.post(
        f"/bookings/{ctx['booking_id']}/attachments",
        files=files,
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert res.status_code == 400


def test_download_rejects_file_changed_after_scan(client, tmp_path, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    customer = ctx["customer"]
    up = client.post(
        f"/bookings/{booking_id}/attachments",
        files={"file": ("brief.pdf", MINIMAL_PDF, "application/pdf")},
        headers=auth_header(customer["token"]),
    )
    assert up.status_code == 200
    attachment_id = up.json()["id"]
    admin = _promote_admin(client, "integrity-admin@booker.test", totp=TEST_TOTP_SECRET)
    scan = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "checked", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert scan.status_code == 200
    stored = list((tmp_path / booking_id).iterdir())
    assert len(stored) == 1
    stored[0].write_bytes(MINIMAL_PDF + b"tampered")

    download = client.get(
        f"/bookings/{booking_id}/attachments/{attachment_id}/download",
        headers=auth_header(customer["token"]),
    )
    assert download.status_code == 409
    assert "Целостность" in download.json()["detail"]


def test_same_attachment_bytes_use_distinct_storage_objects(client, tmp_path, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    headers = auth_header(ctx["customer"]["token"])
    for name in ("first.pdf", "second.pdf"):
        response = client.post(
            f"/bookings/{booking_id}/attachments",
            files={"file": (name, MINIMAL_PDF, "application/pdf")},
            headers=headers,
        )
        assert response.status_code == 200

    stored = list((tmp_path / booking_id).iterdir())
    assert len(stored) == 2
    assert all(path.read_bytes() == MINIMAL_PDF for path in stored)


def test_admin_cannot_mark_changed_attachment_clean(client, tmp_path, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    up = client.post(
        f"/bookings/{booking_id}/attachments",
        files={"file": ("brief.pdf", MINIMAL_PDF, "application/pdf")},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert up.status_code == 200
    stored = next((tmp_path / booking_id).iterdir())
    stored.write_bytes(MINIMAL_PDF + b"changed-before-scan")
    admin = _promote_admin(client, "prescan-admin@booker.test", totp=TEST_TOTP_SECRET)

    scan = client.post(
        f"/admin/attachments/{up.json()['id']}/scan-decision",
        json={"scan_status": "clean", "note": "checked", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert scan.status_code == 409
    assert "Целостность" in scan.json()["detail"]


def test_admin_clean_replay_rechecks_attachment_integrity(client, tmp_path, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    up = client.post(
        f"/bookings/{booking_id}/attachments",
        files={"file": ("brief.pdf", MINIMAL_PDF, "application/pdf")},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert up.status_code == 200
    attachment_id = up.json()["id"]
    admin = _promote_admin(client, "replay-admin@booker.test", totp=TEST_TOTP_SECRET)
    scan_url = f"/admin/attachments/{attachment_id}/scan-decision"
    decision = {"scan_status": "clean", "note": "checked", "totp": totp_code()}
    assert client.post(scan_url, json=decision, headers=auth_header(admin["token"])).status_code == 200
    stored = next((tmp_path / booking_id).iterdir())
    stored.write_bytes(MINIMAL_PDF + b"changed-after-scan")
    replay = client.post(scan_url, json=decision, headers=auth_header(admin["token"]))
    assert replay.status_code == 409
    assert "Целостность" in replay.json()["detail"]


def test_attachment_download_uses_verified_type_and_denies_outsider(client, tmp_path, monkeypatch):
    from booker_api.config import settings
    from tests.conftest import register

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    customer = ctx["customer"]
    outsider = register(client, "attachment-outsider@booker.test", "Outsider")
    files = {"file": ("contract.pdf", MINIMAL_PDF, "text/html")}
    upload = client.post(
        f"/bookings/{booking_id}/attachments",
        files=files, headers=auth_header(customer["token"]),
    )
    assert upload.status_code == 200
    attachment_id = upload.json()["id"]
    outsider_upload = client.post(
        f"/bookings/{booking_id}/attachments",
        files=files, headers=auth_header(outsider["token"]),
    )
    assert outsider_upload.status_code in {403, 404}
    admin = _promote_admin(client, "type-admin@booker.test", totp=TEST_TOTP_SECRET)
    decision = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "test verdict", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert decision.status_code == 200
    path = f"/bookings/{booking_id}/attachments/{attachment_id}/download"
    assert client.get(path).status_code == 401
    denied = client.get(path, headers=auth_header(outsider["token"]))
    assert denied.status_code in {403, 404}
    download = client.get(path, headers=auth_header(customer["token"]))
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/pdf")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-disposition"].startswith("attachment;")


def test_clean_attachment_cannot_be_downloaded_through_another_accessible_booking(
    client, tmp_path, monkeypatch
):
    from booker_api.config import settings
    from booker_api.models import Booking

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    headers = auth_header(ctx["customer"]["token"])
    uploaded = client.post(
        f"/bookings/{booking_id}/attachments",
        files={"file": ("evidence.pdf", MINIMAL_PDF, "application/pdf")},
        headers=headers,
    )
    assert uploaded.status_code == 200
    attachment_id = uploaded.json()["id"]
    admin = _promote_admin(client, "binding-admin@booker.test", totp=TEST_TOTP_SECRET)
    scanned = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "checked", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert scanned.status_code == 200
    with client.app.state.SessionLocal() as db:
        original = db.get(Booking, booking_id)
        other = Booking(event_id=original.event_id, offer_id=original.offer_id, slot_id=original.slot_id)
        db.add(other)
        db.commit()
        other_id = other.id
    denied = client.get(
        f"/bookings/{other_id}/attachments/{attachment_id}/download", headers=headers
    )
    assert denied.status_code == 404
    assert MINIMAL_PDF not in denied.content


def test_admin_needs_step_up_for_cross_org_attachment_access(client, tmp_path, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    customer = ctx["customer"]
    upload = client.post(
        f"/bookings/{booking_id}/attachments",
        files={"file": ("brief.pdf", MINIMAL_PDF, "application/pdf")},
        headers=auth_header(customer["token"]),
    )
    assert upload.status_code == 200
    attachment_id = upload.json()["id"]
    admin = _promote_admin(client, "attachment-stepup@booker.test", totp=TEST_TOTP_SECRET)
    decision = client.post(
        f"/admin/attachments/{attachment_id}/scan-decision",
        json={"scan_status": "clean", "note": "test", "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert decision.status_code == 200
    path = f"/bookings/{booking_id}/attachments/{attachment_id}/download"
    assert client.get(path, headers=auth_header(admin["pre_promotion_token"])).status_code == 403
    assert client.post(
        f"/bookings/{booking_id}/attachments",
        files={"file": ("other.pdf", MINIMAL_PDF, "application/pdf")},
        headers=auth_header(admin["pre_promotion_token"]),
    ).status_code == 403
