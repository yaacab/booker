"""Upload validation: size, extension, magic bytes. ClamAV — при появлении prod storage."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, status

ALLOWED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".webp"})
BLOCKED_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "executable"),
    (b"\x7fELF", "elf"),
    (b"%PDF", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"RIFF", "riff"),
)
SAFE_FILENAME = re.compile(r"^[\w.\- ()\u0400-\u04FF]+$", re.UNICODE)


def sanitize_filename(name: str) -> str:
    base = Path(name).name.strip()
    if not base or len(base) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимое имя файла")
    if not SAFE_FILENAME.match(base):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимые символы в имени файла")
    ext = Path(base).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Разрешены PDF и изображения")
    return base


def detect_kind(header: bytes) -> str | None:
    if header.startswith(b"%PDF"):
        return "pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
        return "webp"
    return None


def scan_upload(content: bytes, filename: str, *, max_bytes: int) -> str:
    if len(content) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл слишком большой")
    if len(content) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")
    head = content[:16]
    if head.startswith((b"MZ", b"\x7fELF")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Исполняемые файлы запрещены")
    safe_name = sanitize_filename(filename)
    ext = Path(safe_name).suffix.lower()
    kind = detect_kind(head)
    if kind is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Тип файла не распознан")
    if ext == ".pdf" and kind != "pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Содержимое не соответствует PDF")
    if ext in {".png"} and kind != "png":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Содержимое не соответствует PNG")
    if ext in {".jpg", ".jpeg"} and kind != "jpeg":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Содержимое не соответствует JPEG")
    if ext == ".webp" and kind != "webp":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Содержимое не соответствует WEBP")
    return safe_name
