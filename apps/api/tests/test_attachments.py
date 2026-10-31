from tests.conftest import auth_header
from tests.test_admin import _promote_admin
from tests.test_payments import _awaiting_payment

MINIMAL_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


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
    room = client.get(f"/deal-room/{booking_id}", headers=auth_header(customer["token"]))
    assert room.status_code == 200
    kinds = [d["kind"] for d in room.json()["documents"]]
    assert "attachment" in kinds


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
