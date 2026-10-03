"""One-time offline recovery codes for privileged Booker accounts."""

from __future__ import annotations

import hashlib
import re
import secrets

from sqlalchemy import delete
from sqlalchemy.orm import Session

from booker_api.models import StaffRecoveryCode

RECOVERY_CODE_COUNT = 10
_CODE_RE = re.compile(r"[0-9a-f]{24}")


def _hash_normalized(value: str) -> str:
    return hashlib.sha256(b"booker.staff-recovery.v1\0" + value.encode()).hexdigest()


def recovery_code_hash(raw: str) -> str | None:
    normalized = raw.strip().replace("-", "").replace(" ", "").lower()
    if not _CODE_RE.fullmatch(normalized):
        return None
    return _hash_normalized(normalized)


def replace_recovery_codes(db: Session, user_id: str) -> list[str]:
    """Invalidate the old kit and return a new kit to the caller exactly once."""

    db.execute(delete(StaffRecoveryCode).where(StaffRecoveryCode.user_id == user_id))
    codes: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        value = secrets.token_hex(12)
        codes.append("-".join(value[index:index + 4] for index in range(0, 24, 4)))
        db.add(StaffRecoveryCode(code_hash=_hash_normalized(value), user_id=user_id))
    db.flush()
    return codes
