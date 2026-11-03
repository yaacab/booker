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
from booker_api.rate_limit import otp_limiter
from booker_api.totp import verify_totp_code

bearer = HTTPBearer(auto_error=False)


class AuthContext(NamedTuple):
    user: User
    session: SessionToken


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    """An external-only account has no local password to verify."""
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    if not salt or not digest:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return hmac.compare_digest(check, digest)


SESSION_TTL_DAYS = 30
_SESSION_TOUCH_MIN_SECONDS = 60


def sanitize_user_agent(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = "".join(ch for ch in raw.strip() if ch.isprintable())
    if not cleaned:
        return None
    return cleaned[:512]


def request_client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    from booker_api.rate_limit import client_key

    # Reuse trusted-proxy parsing; strip the rate-limit prefix.
    key = client_key(request, "session")
    ip = key.split(":", 1)[-1].strip()
    return ip[:64] if ip and ip != "unknown" else None


def issue_token(db: Session, user: User, *, request: Request | None = None) -> str:
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    stamped = now()
    db.add(
        SessionToken(
            token=token_hash,
            user_id=user.id,
            expires_at=stamped + timedelta(days=SESSION_TTL_DAYS),
            user_agent=sanitize_user_agent(
                request.headers.get("user-agent") if request is not None else None
            ),
            client_ip=request_client_ip(request),
            last_seen_at=stamped,
        )
    )
    db.flush()
    return raw


def authenticate_token(db: Session, raw: str) -> tuple[User, SessionToken]:
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = db.get(SessionToken, token_hash) or db.get(SessionToken, raw)
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


def touch_session(db: Session, row: SessionToken, request: Request | None = None) -> None:
    stamped = now()
    if row.last_seen_at is not None:
        age = (stamped - aware(row.last_seen_at)).total_seconds()
        if age < _SESSION_TOUCH_MIN_SECONDS:
            return
    row.last_seen_at = stamped
    if request is not None:
        ua = sanitize_user_agent(request.headers.get("user-agent"))
        if ua:
            row.user_agent = ua
        ip = request_client_ip(request)
        if ip:
            row.client_ip = ip
    db.add(row)
    # Separate commit so request work can still roll back; refresh avoids stale expires.
    db.commit()
    db.refresh(row)


def _support_operator_route_allowed(request: Request) -> bool:
    """A staff bearer cannot inherit unrelated marketplace permissions."""
    path = request.url.path
    method = request.method
    if (path, method) in {("/me", "GET"), ("/notifications", "GET"),
                          ("/me/identities", "GET"),
                          ("/me/identities/telegram/link", "POST"),
                          ("/me/identities/telegram/unlink", "POST"),
                          ("/me/sessions", "GET"),
                          ("/me/sessions/revoke-others", "POST"),
                          ("/auth/logout", "POST"),
                          ("/auth/admin-totp/recovery-codes/count", "GET"),
                          ("/admin/support/tickets", "GET"),
                          ("/admin/support/staff", "GET")}:
        return True
    if path.startswith("/me/sessions/") and method == "DELETE":
        return True
    parts = path.strip("/").split("/")
    if len(parts) < 4 or parts[:3] != ["admin", "support", "tickets"] or not parts[3]:
        return False
    if len(parts) == 4:
        return method == "GET"
    if len(parts) != 5:
        return False
    action = parts[4]
    return (action == "notes" and method == "GET") or (
        action in {"messages", "assign", "priority", "notes", "close", "reopen"} and method == "POST"
    )


def auth_context(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
    user, row = authenticate_token(db, creds.credentials)
    if user.is_support_operator and not user.is_platform_admin and not _support_operator_route_allowed(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт оператора доступен только для поддержки")
    touch_session(db, row, request)
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


def require_org_owner_or_admin_member(db: Session, user: User, org_id: str) -> TeamMember:
    """Require a real legal representative; platform-admin bypass is intentionally excluded."""
    member = membership(db, user.id, org_id)
    if not member or member.role not in {"owner", "admin"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Подтверждение доступно только владельцу или администратору организации",
        )
    return member


def ensure_admin_2fa_configured(user: User) -> None:
    if not user.totp_enabled:
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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужен включённый второй фактор")
    totp = _totp_from_request(request, code)
    if totp:
        otp_limiter.check(f"otp:user:{user.id}")
    if not verify_totp_code(user.totp_secret, totp):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужен второй фактор")


def ensure_admin_2fa_session(
    request: Request,
    db: Session,
    user: User,
    session: SessionToken,
    *,
    force: bool = False,
) -> None:
    """Privileged reads/writes need a verified step-up session or header."""
    if force and not user.totp_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Администратору нужен включённый второй фактор (TOTP)",
        )
    ensure_admin_2fa_configured(user)
    header_code = _totp_from_request(request, None)
    if header_code:
        otp_limiter.check(f"otp:user:{user.id}")
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


def require_admin_step_up(
    request: Request,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> User:
    """Require a current TOTP step-up even when the global rollout flag is disabled."""

    user = ctx.user
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только администратор платформы")
    ensure_admin_2fa_session(request, db, user, ctx.session, force=True)
    return user


def require_support_step_up(
    request: Request,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> User:
    """Support queue access is separate from platform administration."""
    user = ctx.user
    if not (user.is_platform_admin or user.is_support_operator):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только оператор поддержки")
    ensure_admin_2fa_session(request, db, user, ctx.session, force=True)
    return user


def mark_admin_2fa_verified(db: Session, token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = db.get(SessionToken, token_hash) or db.get(SessionToken, token)
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
