from sqlalchemy.orm import Session

from booker_api.models import TeamMember, User
from booker_api.notifications.registry import transport_for
from booker_api.notifications.types import Channel, Notification


def notify(
    db: Session,
    *,
    actor_user_id: str | None,
    notifications: list[Notification],
) -> list[dict]:
    results: list[dict] = []
    for item in notifications:
        result = transport_for(item.channel).send(
            db,
            actor_user_id=actor_user_id,
            notification=item,
        )
        results.append(result.as_dict())
    return results


def org_member_notifications(
    db: Session,
    *,
    organization_id: str,
    template: str,
    subject: str,
    body: str,
    entity_type: str,
    entity_id: str,
    channels: tuple[Channel, ...] = (Channel.IN_APP, Channel.EMAIL),
) -> list[Notification]:
    members = db.query(TeamMember).filter(TeamMember.organization_id == organization_id).all()
    out: list[Notification] = []
    for member in members:
        user = db.get(User, member.user_id)
        if not user:
            continue
        for channel in channels:
            out.append(
                Notification(
                    channel=channel,
                    template=template,
                    recipient_user_id=user.id,
                    recipient_email=user.email,
                    recipient_phone=user.phone,
                    subject=subject,
                    body=body,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
            )
    return out


def on_request_created(
    db: Session,
    *,
    actor_user_id: str | None,
    request_id: str,
    supplier_org_id: str,
    event_title: str,
) -> list[dict]:
    subject = "Новая заявка"
    body = f"Поступила заявка: {event_title}"
    return notify(
        db,
        actor_user_id=actor_user_id,
        notifications=org_member_notifications(
            db,
            organization_id=supplier_org_id,
            template="request.created",
            subject=subject,
            body=body,
            entity_type="request",
            entity_id=request_id,
        ),
    )


def on_offer_created(
    db: Session,
    *,
    actor_user_id: str | None,
    offer_id: str,
    customer_org_id: str,
    event_title: str,
) -> list[dict]:
    subject = "Новое предложение"
    body = f"Получено предложение по событию: {event_title}"
    return notify(
        db,
        actor_user_id=actor_user_id,
        notifications=org_member_notifications(
            db,
            organization_id=customer_org_id,
            template="offer.created",
            subject=subject,
            body=body,
            entity_type="offer",
            entity_id=offer_id,
        ),
    )
