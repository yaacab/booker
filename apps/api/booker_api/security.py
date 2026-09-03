from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.db import get_db
from booker_api.models import AuditLog, SessionToken, TeamMember, User
from booker_api.totp import verify_totp_code

bearer = HTTPBearer(auto_error=False)


class AuthContext(NamedTuple):
    user: User
    session: SessionToken


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return hmac.compare_digest(check, digest)


SESSION_TTL_DAYS = 30


def issue_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        SessionToken(
            token=token,
            user_id=user.id,
            expires_at=now() + timedelta(days=SESSION_TTL_DAYS),
        )
    )
    db.flush()
    return token


def authenticate_token(db: Session, raw: str) -> tuple[User, SessionToken]:
    row = db.get(SessionToken, raw)
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия недействительна")
    if row.expires_at is not None and aware(row.expires_at) <= now():
        db.delete(row)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")
    return user, row


def auth_context(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
    user, row = authenticate_token(db, creds.credentials)
    return AuthContext(user, row)


def current_user(ctx: AuthContext = Depends(auth_context)) -> User:
    return ctx.user


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


def _totp_from_request(request: Request | None, code: str | None) -> str | None:
    if code:
        return code.strip()
    if request is None:
        return None
    header = request.headers.get("x-booker-totp") or request.headers.get("X-Booker-TOTP")
    return header.strip() if header else None


def require_admin_2fa(user: User, code: str | None, request: Request | None = None) -> None:
    """Step-up: always verify a fresh TOTP code for sensitive admin mutations."""
    if not user.totp_enabled:
        if settings.require_admin_2fa_enforced:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужен включённый второй фактор")
        return
    totp = _totp_from_request(request, code)
    if not verify_totp_code(user.totp_secret, totp):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужен второй фактор")


def ensure_admin_2fa_session(
    request: Request,
    db: Session,
    user: User,
    session: SessionToken,
) -> None:
    """When 2FA is enforced, admin reads/writes need a verified step-up session or header."""
    ensure_admin_2fa_configured(user)
    if not settings.require_admin_2fa_enforced:
        return
    header_code = _totp_from_request(request, None)
    if header_code and verify_totp_code(user.totp_secret, header_code):
        session.admin_2fa_verified_at = now()
        db.commit()
        return
    verified_at = session.admin_2fa_verified_at
    if verified_at is not None:
        age = (now() - aware(verified_at)).total_seconds()
        if age <= settings.admin_2fa_step_up_minutes * 60:
            return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Нужен код второго фактора (X-Booker-TOTP или вход с TOTP)",
    )


def require_admin(
    request: Request,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> User:
    user = ctx.user
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только администратор платформы")
    ensure_admin_2fa_session(request, db, user, ctx.session)
    return user


def mark_admin_2fa_verified(db: Session, token: str) -> None:
    row = db.get(SessionToken, token)
    if row:
        row.admin_2fa_verified_at = now()


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
