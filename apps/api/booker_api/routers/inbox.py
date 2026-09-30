from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import InboxNotification, User
from booker_api.notifications.inbox import internal_href
from booker_api.rate_limit import analytics_limiter, messaging_limiter
from booker_api.security import audit, current_user, now

router = APIRouter(tags=['notifications'])


@router.get('/notifications')
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0), unread_only: bool = False):
    analytics_limiter.check(f'inbox:{user.id}')
    base = db.query(InboxNotification).filter_by(recipient_user_id=user.id)
    unread = base.filter(InboxNotification.read_at.is_(None)).count()
    q = base.filter(InboxNotification.read_at.is_(None)) if unread_only else base
    total = q.count()
    rows = q.order_by(InboxNotification.created_at.desc(), InboxNotification.id.desc()).offset(offset).limit(limit).all()
    return {'items': [{'id': r.id, 'channel': 'in_app', 'template': r.template, 'subject': r.subject, 'body': r.body,
        'entity_type': r.entity_type, 'entity_id': r.entity_id, 'href': internal_href(r.href),
        'created_at': r.created_at.isoformat(), 'read_at': r.read_at.isoformat() if r.read_at else None} for r in rows],
        'total': total, 'unread_count': unread, 'offset': offset}


@router.post('/notifications/{notification_id}/read')
def mark_read(notification_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(InboxNotification, str(notification_id))
    if not row:
        raise HTTPException(404, 'Уведомление не найдено')
    if row.recipient_user_id != user.id:
        raise HTTPException(403, 'Нет доступа к уведомлению')
    messaging_limiter.check(f'inbox-read:{user.id}')
    changed = db.execute(update(InboxNotification).where(InboxNotification.id == row.id, InboxNotification.read_at.is_(None)).values(read_at=now()))
    if changed.rowcount:
        audit(db, actor_user_id=user.id, action='notification.read', entity_type='notification', entity_id=row.id, payload={})
    db.commit()
    return {'id': row.id, 'read_at': row.read_at.isoformat()}
