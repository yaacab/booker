"""Bounded clamd INSTREAM client; transport failures never mean a clean file."""

from __future__ import annotations

import socket
import struct
import time


class AVScanError(Exception):
    """The scanner did not return a trustworthy verdict."""


def scan_clamd(content: bytes, *, socket_path: str, timeout_seconds: float) -> str:
    """Return clean/blocked from a local clamd Unix socket using INSTREAM."""
    if not socket_path or timeout_seconds <= 0:
        raise AVScanError("invalid scanner configuration")
    deadline = time.monotonic() + timeout_seconds

    def remaining(connection: socket.socket) -> None:
        left = deadline - time.monotonic()
        if left <= 0:
            raise AVScanError("scanner deadline exceeded")
        connection.settimeout(left)

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            remaining(connection)
            connection.connect(socket_path)
            remaining(connection)
            connection.sendall(b"zINSTREAM\0")
            for offset in range(0, len(content), 65_536):
                chunk = content[offset : offset + 65_536]
                remaining(connection)
                connection.sendall(struct.pack(">I", len(chunk)))
                remaining(connection)
                connection.sendall(chunk)
            remaining(connection)
            connection.sendall(struct.pack(">I", 0))
            reply = bytearray()
            while b"\0" not in reply and len(reply) < 4_096:
                remaining(connection)
                part = connection.recv(min(4_096 - len(reply), 4_096))
                if not part:
                    break
                reply.extend(part)
    except (OSError, ValueError) as exc:
        raise AVScanError("scanner unavailable") from exc
    if b"\0" not in reply:
        raise AVScanError("incomplete scanner reply")
    record = bytes(reply).split(b"\0", 1)[0]
    if record == b"stream: OK":
        return "clean"
    if record.startswith(b"stream: ") and record.endswith(b" FOUND"):
        return "blocked"
    raise AVScanError("unrecognized scanner reply")
