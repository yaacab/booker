"""Optional authenticated, encrypted wrapper for Booker backup archives."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from contextlib import nullcontext
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path

MAGIC = b"BOOKER-SEALED-v1\0"
NONCE_BYTES = 12
KEY_ID_BYTES = 8
TAG_BYTES = 16
CHUNK_BYTES = 1024 * 1024
DEFAULT_MAX_BYTES = 20 * 1024 * 1024 * 1024


def _crypto():
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise RuntimeError("sealed backups require Python package cryptography") from exc
    return Cipher, algorithms, modes


def _key(path: Path) -> bytes:
    canonical = path.resolve()
    for variable in ("BOOKER_BACKUP_DIR", "BOOKER_UPLOAD_DIR"):
        if configured := os.environ.get(variable):
            root = Path(configured).resolve()
            if canonical == root or root in canonical.parents:
                raise RuntimeError(f"backup key must be outside {variable}")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise RuntimeError("backup key must be a regular file with mode 0600 or stricter")
        if metadata.st_uid != os.geteuid():
            raise RuntimeError("backup key must be owned by the backup process user")
        key = source.read(33)
    if len(key) != 32:
        raise RuntimeError("backup key must contain exactly 32 raw bytes")
    return key


def _max_bytes() -> int:
    raw = os.environ.get("BOOKER_BACKUP_MAX_RESTORE_BYTES", str(DEFAULT_MAX_BYTES))
    if not raw.isdecimal() or int(raw) < 1024:
        raise RuntimeError("BOOKER_BACKUP_MAX_RESTORE_BYTES must be an integer >= 1024")
    return int(raw)


def detect_format(source: Path) -> str:
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as data:
        prefix = data.read(len(MAGIC))
    if prefix == MAGIC or (len(prefix) >= 4 and MAGIC.startswith(prefix)):
        return "sealed"
    if prefix.startswith(b"\x1f\x8b"):
        return "legacy"
    raise RuntimeError("unknown backup format")


def archive_key_id(source: Path) -> str:
    if detect_format(source) != "sealed":
        raise RuntimeError("archive is not sealed")
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as data:
        header = data.read(len(MAGIC) + KEY_ID_BYTES)
    if len(header) != len(MAGIC) + KEY_ID_BYTES:
        raise RuntimeError("sealed archive header is incomplete")
    return header[len(MAGIC) :].hex()


def seal_archive(source: Path, key_file: Path, target: Path) -> None:
    Cipher, algorithms, modes = _crypto()
    key = _key(key_file)
    nonce = os.urandom(NONCE_BYTES)
    header = MAGIC + sha256(key).digest()[:KEY_ID_BYTES] + nonce
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    try:
        source_context = nullcontext(sys.stdin.buffer) if str(source) == "-" else source.open("rb")
        with source_context as original:
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(descriptor, "wb") as sealed:
                os.fchmod(sealed.fileno(), 0o600)
                sealed.write(header)
                total = 0
                while chunk := original.read(CHUNK_BYTES):
                    total += len(chunk)
                    if total + len(header) + TAG_BYTES > _max_bytes():
                        raise RuntimeError("sealed archive exceeds restore size limit")
                    sealed.write(encryptor.update(chunk))
                sealed.write(encryptor.finalize())
                sealed.write(encryptor.tag)
                sealed.flush()
                os.fsync(sealed.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise


def unseal_archive(source: Path, key_file: Path, target: Path) -> None:
    Cipher, algorithms, modes = _crypto()
    archive_root = source.resolve().parent
    key_location = key_file.resolve()
    if archive_root == key_location or archive_root in key_location.parents:
        raise RuntimeError("backup key must be outside the archive directory")
    key = _key(key_file)
    header_size = len(MAGIC) + KEY_ID_BYTES + NONCE_BYTES
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as sealed:
        size = os.fstat(sealed.fileno()).st_size
        if size > _max_bytes():
            raise RuntimeError("sealed archive exceeds restore size limit")
        if size < header_size + TAG_BYTES:
            raise RuntimeError("sealed archive is incomplete")
        header = sealed.read(header_size)
        if not header.startswith(MAGIC):
            raise RuntimeError("unsupported sealed archive header")
        key_id = header[len(MAGIC) : len(MAGIC) + KEY_ID_BYTES]
        if not compare_digest(key_id, sha256(key).digest()[:KEY_ID_BYTES]):
            raise RuntimeError("backup key does not match archive key id")
        nonce = header[-NONCE_BYTES:]
        sealed.seek(size - TAG_BYTES)
        tag = sealed.read(TAG_BYTES)
        sealed.seek(header_size)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(header)
        remaining = size - header_size - TAG_BYTES
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as plain:
                while remaining:
                    chunk = sealed.read(min(CHUNK_BYTES, remaining))
                    if not chunk:
                        raise RuntimeError("sealed archive is truncated")
                    remaining -= len(chunk)
                    plain.write(decryptor.update(chunk))
                plain.write(decryptor.finalize())
                plain.flush()
                os.fsync(plain.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise


def verify_sealed(source: Path, key_file: Path) -> None:
    from backup_support import verify_archive

    with tempfile.TemporaryDirectory(prefix="booker-sealed-verify-") as directory:
        plain = Path(directory) / "archive.tar.gz"
        unseal_archive(source, key_file, plain)
        verify_archive(plain)


def main() -> None:
    command, *args = sys.argv[1:]
    if command == "check-key" and len(args) == 1:
        _crypto()
        _key(Path(args[0]))
    elif command == "seal" and len(args) == 3:
        seal_archive(Path(args[0]), Path(args[1]), Path(args[2]))
    elif command == "unseal" and len(args) == 3:
        unseal_archive(Path(args[0]), Path(args[1]), Path(args[2]))
    elif command == "verify" and len(args) == 2:
        verify_sealed(Path(args[0]), Path(args[1]))
    elif command == "detect" and len(args) == 1:
        print(detect_format(Path(args[0])))
    elif command == "key-id" and len(args) == 1:
        print(sha256(_key(Path(args[0]))).digest()[:KEY_ID_BYTES].hex())
    elif command == "archive-key-id" and len(args) == 1:
        print(archive_key_id(Path(args[0])))
    else:
        raise SystemExit("invalid backup_crypto command")


if __name__ == "__main__":
    main()
