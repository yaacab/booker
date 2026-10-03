"""Private recipient-indexed notices rendered from reviewed static copy."""

from __future__ import annotations

from sqlalchemy.orm import Session

from booker_api.models import UserNotification

NOTICE_COPY: dict[str, tuple[str, str]] = {
    "request.created": (
        "Новая заявка",
        "В Букере появилась новая заявка. Откройте кабинет, чтобы посмотреть детали.",
    ),
    "offer.created": (
        "Новое предложение",
        "В Букере появилось новое предложение. Откройте кабинет, чтобы посмотреть детали.",
    ),
    "security.totp_enabled": (
        "Защита входа подключена",
        "Для аккаунта Букера подключён Authenticator. Если это были не вы, обратитесь в поддержку.",
    ),
    "security.totp_rotated": (
        "Приложение Authenticator изменено",
        "Для аккаунта Букера заменён второй фактор. Если это были не вы, обратитесь в поддержку.",
    ),
    "security.recovery_codes_regenerated": (
        "Резервные коды заменены",
        "Для аккаунта Букера выпущен новый комплект резервных кодов. Если это были не вы, обратитесь в поддержку.",
    ),
    "security.totp_recovered": (
        "Доступ восстановлен",
        "В аккаунте Букера восстановлен второй фактор и завершены прежние сеансы. Если это были не вы, обратитесь в поддержку.",
    ),
    "security.password_reset": (
        "Пароль изменён",
        "Пароль аккаунта Букера изменён и прежние сеансы завершены. Если это были не вы, обратитесь в поддержку.",
    ),
    "security.identity_linked": (
        "Способ входа добавлен",
        "К аккаунту Букера привязан Telegram. Если это были не вы, обратитесь в поддержку.",
    ),
    "security.identity_unlinked": (
        "Способ входа удалён",
        "Привязка Telegram удалена из аккаунта Букера. Если это были не вы, обратитесь в поддержку.",
    ),
    "support.acceptance_overdue": (
        "Срочное обращение не принято",
        "Истекли 15 рабочих минут на принятие обращения. Администратору нужно проверить очередь поддержки.",
    ),
    "support.first_response_overdue": (
        "Просрочен первый ответ поддержки",
        "Срок первого ответа по обращению истёк. Откройте операторскую очередь и проверьте обращение.",
    ),
    "support.ticket.new": (
        "Новое обращение в поддержку",
        "В очередь Букера поступило обращение. Откройте кабинет поддержки, чтобы проверить его.",
    ),
    "support.ticket.urgent": (
        "Срочное обращение в поддержку",
        "В очередь Букера поступило срочное обращение. Откройте кабинет поддержки и проверьте его.",
    ),
}


def persist_safe_notice(
    db: Session,
    *,
    recipient_user_id: str | None,
    template: str,
    entity_type: str,
    entity_id: str,
) -> UserNotification | None:
    """Persist only template identity; never store supplied subject/body or OTP."""
    if not recipient_user_id or not entity_id or template not in NOTICE_COPY:
        return None
    existing = db.query(UserNotification).filter(
        UserNotification.recipient_user_id == recipient_user_id,
        UserNotification.template == template,
        UserNotification.entity_type == entity_type,
        UserNotification.entity_id == entity_id,
    ).one_or_none()
    if existing:
        return existing
    row = UserNotification(
        recipient_user_id=recipient_user_id,
        template=template,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    # Flush in the outer transaction before any outbox SAVEPOINT. A first
    # SQLite SAVEPOINT can otherwise survive rollback of the logical parent.
    db.add(row)
    db.flush()
    return row


def notice_payload(row: UserNotification) -> dict:
    subject, body = NOTICE_COPY[row.template]
    return {
        "id": row.id,
        "channel": "in_app",
        "template": row.template,
        "subject": subject,
        "body": body,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "created_at": row.created_at.isoformat(),
    }
