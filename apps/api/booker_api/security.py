from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.db import get_db
from booker_api.models import AuditLog, SessionToken, TeamMember, User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return hmac.compare_digest(check, digest)


def issue_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessionToken(token=token, user_id=user.id))
    db.flush()
    return token


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
    row = db.get(SessionToken, creds.credentials)
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия недействительна")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")
    return user


def membership(db: Session, user_id: str, org_id: str) -> TeamMember | None:
    return (
        db.query(TeamMember)
        .filter(TeamMember.user_id == user_id, TeamMember.organization_id == org_id)
        .one_or_none()
    )


def require_org_member(db: Session, user: User, org_id: str) -> TeamMember:
    member = membership(db, user.id, org_id)
    if not member and not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к организации")
    if member:
        return member
    fake = TeamMember(
        user_id=user.id,
        organization_id=org_id,
        role="admin",
        can_confirm_offer=True,
    )
    return fake


def require_org_writer(db: Session, user: User, org_id: str) -> TeamMember:
    member = require_org_member(db, user, org_id)
    if user.is_platform_admin:
        return member
    if member.role not in {"owner", "admin", "manager"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только просмотр: нужна роль менеджера")
    return member


def ensure_admin_2fa_configured(user: User) -> None:
    if settings.require_admin_2fa_enforced and not user.totp_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Администратору нужен включённый второй фактор (TOTP)",
        )


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только администратор платформы")
    ensure_admin_2fa_configured(user)
    return user


def require_admin_2fa(user: User, code: str | None) -> None:
    if not user.totp_enabled:
        return
    if not code or code != user.totp_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужен второй фактор")


def audit(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=json.dumps(payload or {}, ensure_ascii=False),
        )
    )


def aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def now() -> datetime:
    return datetime.now(timezone.utc)


def hold_deadline() -> datetime:
    return now() + timedelta(hours=settings.hold_ttl_hours)


def verify_webhook_signature(payload: str, signature: str) -> bool:
    expected = hmac.new(
        settings.webhook_secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
