import pytest
from fastapi import HTTPException

from booker_api.file_scan import scan_upload

MINIMAL_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n"


def test_scan_upload_accepts_pdf():
    name = scan_upload(MINIMAL_PDF, "rider.pdf", max_bytes=1024 * 1024)
    assert name == "rider.pdf"


def test_scan_upload_rejects_executable():
    with pytest.raises(HTTPException) as exc:
        scan_upload(b"MZ" + b"\x00" * 64, "evil.pdf", max_bytes=1024 * 1024)
    assert exc.value.status_code == 400


def test_scan_upload_rejects_mismatch():
    with pytest.raises(HTTPException):
        scan_upload(MINIMAL_PDF, "photo.png", max_bytes=1024 * 1024)
