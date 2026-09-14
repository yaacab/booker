"""Business planning: immutable reusable briefs and organization-private notes."""
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.commerce.entitlements import get_entitlements, require_feature
from booker_api.db import get_db
from booker_api.event_commands import remember_command, replay_command
from booker_api.models import (
    BusinessEventNote,
    BusinessEventTemplate,
    Event,
    EventTeamRequirement,
    Organization,
    User,
)
from booker_api.rate_limit import analytics_limiter, messaging_limiter
from booker_api.security import (
    audit,
    aware,
    current_user,
    now,
    require_org_member,
    require_org_writer,
)

router = APIRouter(tags=["business"])


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_event_id: UUID
    name: str = Field(min_length=1, max_length=128)


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=255)
    event_date: datetime
    ends_at: datetime


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=4000)


class NoteEditIn(NoteIn):
    expected_revision: int = Field(ge=1, strict=True)


def organization(db, user, org_id, writer=False):
    org = db.get(Organization, str(org_id))
    if not org:
        raise HTTPException(404, "Организация не найдена")
    member = (require_org_writer if writer else require_org_member)(db, user, org.id)
    if org.kind != "customer":
        raise HTTPException(403, "Раздел доступен в пространстве заказчика")
    return org, member


def event_access(db, user, event_id, writer=False):
    event = db.get(Event, str(event_id))
    if not event:
        raise HTTPException(404, "Событие не найдено")
    org, member = organization(db, user, event.organization_id, writer)
    return event, org, member


def lock_org(db, org):
    db.execute(update(Organization).where(Organization.id == org.id).values(name=Organization.name))


def snapshot(db, event):
    # Whitelist brief fields; never copy private notes, old dates or any deal state.
    roles = db.query(EventTeamRequirement).filter_by(event_id=event.id).order_by(EventTeamRequirement.sort_order, EventTeamRequirement.id).all()
    return {"city": event.city, "event_type": event.event_type, "guest_count": event.guest_count, "budget_rub": event.budget_rub,
        "requirements": [{"category_code": r.category_code, "role_label": r.role_label, "qty": r.qty, "required": r.required, "sort_order": r.sort_order} for r in roles]}


def template_payload(row):
    return {"id": row.id, "name": row.name, "brief": json.loads(row.snapshot_json), "created_at": aware(row.created_at).isoformat(), "archived": row.archived}


def record(db, user, action, kind, target, payload=None):
    audit(db, actor_user_id=user.id, action=action, entity_type=kind, entity_id=target, payload=payload or {})


@router.get('/business/organizations/{org_id}/templates')
def list_templates(org_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org, member = organization(db, user, org_id)
    analytics_limiter.check(f'business-templates:{user.id}')
    rows = db.query(BusinessEventTemplate).filter_by(organization_id=org.id, archived=False).order_by(BusinessEventTemplate.created_at.desc(), BusinessEventTemplate.id).all()
    features = get_entitlements(db, org.id)['features']
    return {'items': [template_payload(row) for row in rows], 'can_manage': member.role in {'owner', 'admin', 'manager'}, 'can_create': bool(features.get('customer.templates'))}


@router.post('/business/organizations/{org_id}/templates', status_code=201)
def create_template(org_id: UUID, body: TemplateIn, user: User = Depends(current_user), db: Session = Depends(get_db),
    idempotency_key: str = Header(alias='Idempotency-Key', min_length=8, max_length=160)):
    org, _ = organization(db, user, org_id, True)
    messaging_limiter.check(f'business-template-create:{user.id}')
    lock_org(db, org)
    command, scope = body.model_dump(mode='json'), f'business.template:{org.id}'
    cached = replay_command(db, scope, idempotency_key, command)
    if cached:
        return cached
    require_feature(db, org.id, 'customer.templates')
    event = db.get(Event, str(body.source_event_id))
    if not event or event.organization_id != org.id:
        raise HTTPException(404, 'Событие не найдено в этой организации')
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title)); db.refresh(event)
    if db.query(BusinessEventTemplate).filter_by(organization_id=org.id, archived=False).count() >= 100:
        raise HTTPException(409, 'Доступно до 100 шаблонов. Уберите неиспользуемые в архив')
    row = BusinessEventTemplate(organization_id=org.id, name=body.name, snapshot_json=json.dumps(snapshot(db, event), ensure_ascii=False), created_by=user.id)
    db.add(row); db.flush()
    result = {'id': row.id}
    remember_command(db, scope, idempotency_key, command, result)
    record(db, user, 'business.template_created', 'business_template', row.id)
    db.commit()
    return result


@router.post('/business/templates/{template_id}/archive')
def archive_template(template_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(BusinessEventTemplate, str(template_id))
    if not row:
        raise HTTPException(404, 'Шаблон не найден')
    org, _ = organization(db, user, row.organization_id, True)
    messaging_limiter.check(f'business-template-archive:{user.id}')
    lock_org(db, org); db.refresh(row)
    if not row.archived:
        row.archived = True
        record(db, user, 'business.template_archived', 'business_template', row.id)
        db.commit()
    return {'id': row.id, 'archived': True}


def new_draft(db, user, org, brief, body, scope, key, command):
    cached = replay_command(db, scope, key, command)
    if cached:
        return cached
    require_feature(db, org.id, 'customer.templates')
    start, end = aware(body.event_date), aware(body.ends_at)
    if body.event_date.tzinfo is None or body.ends_at.tzinfo is None or start <= now() or end <= start:
        raise HTTPException(422, 'Укажите будущее начало с часовым поясом и окончание позже начала')
    event = Event(organization_id=org.id, title=body.title, event_date=start, ends_at=end, status='Draft', notes='',
        **{key: brief[key] for key in ('city', 'event_type', 'guest_count', 'budget_rub')})
    db.add(event); db.flush()
    for role in brief['requirements']:
        db.add(EventTeamRequirement(event_id=event.id, status='open', notes='', **role))
    result = {'id': event.id, 'status': 'Draft'}
    remember_command(db, scope, key, command, result)
    record(db, user, 'business.draft_created', 'event', event.id, {'source_kind': scope.split(':')[0]})
    db.commit()
    return result


@router.post('/business/templates/{template_id}/events', status_code=201)
def instantiate_template(template_id: UUID, body: DraftIn, user: User = Depends(current_user), db: Session = Depends(get_db),
    idempotency_key: str = Header(alias='Idempotency-Key', min_length=8, max_length=160)):
    row = db.get(BusinessEventTemplate, str(template_id))
    if not row:
        raise HTTPException(404, 'Шаблон не найден')
    org, _ = organization(db, user, row.organization_id, True)
    messaging_limiter.check(f'business-draft:{user.id}')
    lock_org(db, org); db.refresh(row)
    scope, command = f'business.from_template:{row.id}', body.model_dump(mode='json')
    cached = replay_command(db, scope, idempotency_key, command)
    if cached:
        return cached
    if row.archived:
        raise HTTPException(409, 'Шаблон в архиве')
    return new_draft(db, user, org, json.loads(row.snapshot_json), body, scope, idempotency_key, command)


@router.post('/business/events/{event_id}/clone', status_code=201)
def clone_event(event_id: UUID, body: DraftIn, user: User = Depends(current_user), db: Session = Depends(get_db),
    idempotency_key: str = Header(alias='Idempotency-Key', min_length=8, max_length=160)):
    event, org, _ = event_access(db, user, event_id, True)
    messaging_limiter.check(f'business-draft:{user.id}')
    lock_org(db, org)
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title)); db.refresh(event)
    return new_draft(db, user, org, snapshot(db, event), body, f'business.clone:{event.id}', idempotency_key, body.model_dump(mode='json'))


def note_payload(row, author_name, user, member, enabled):
    return {'id': row.id, 'body': row.body, 'revision': row.revision, 'author_name': author_name,
        'created_at': aware(row.created_at).isoformat(), 'updated_at': aware(row.updated_at).isoformat(),
        'can_edit': enabled and member.role in {'owner', 'admin', 'manager'} and row.author_id == user.id,
        'can_delete': member.role in {'owner', 'admin'} or (member.role == 'manager' and row.author_id == user.id)}


@router.get('/business/events/{event_id}/notes')
def list_notes(event_id: UUID, offset: int = Query(default=0, ge=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    event, org, member = event_access(db, user, event_id)
    analytics_limiter.check(f'business-notes:{user.id}')
    enabled = bool(get_entitlements(db, org.id)['features'].get('customer.notes'))
    query = db.query(BusinessEventNote).filter_by(event_id=event.id, deleted=False)
    rows = query.add_columns(User.full_name).join(User, User.id == BusinessEventNote.author_id).order_by(BusinessEventNote.created_at.desc(), BusinessEventNote.id).offset(offset).limit(50).all()
    return {'items': [note_payload(row, name, user, member, enabled) for row, name in rows], 'total': query.count(),
        'can_write': enabled and member.role in {'owner', 'admin', 'manager'}}


@router.post('/business/events/{event_id}/notes', status_code=201)
def create_note(event_id: UUID, body: NoteIn, user: User = Depends(current_user), db: Session = Depends(get_db),
    idempotency_key: str = Header(alias='Idempotency-Key', min_length=8, max_length=160)):
    event, org, _ = event_access(db, user, event_id, True)
    messaging_limiter.check(f'business-note:{user.id}')
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
    scope, command = f'business.note:{event.id}:{user.id}', body.model_dump(mode='json')
    cached = replay_command(db, scope, idempotency_key, command)
    if cached:
        return cached
    require_feature(db, org.id, 'customer.notes')
    row = BusinessEventNote(event_id=event.id, author_id=user.id, body=body.body)
    db.add(row); db.flush()
    result = {'id': row.id, 'revision': row.revision}
    remember_command(db, scope, idempotency_key, command, result)
    record(db, user, 'business.note_created', 'business_note', row.id)
    db.commit()
    return result


@router.put('/business/notes/{note_id}')
def edit_note(note_id: UUID, body: NoteEditIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(BusinessEventNote, str(note_id))
    if not row:
        raise HTTPException(404, 'Заметка не найдена')
    _, org, _ = event_access(db, user, row.event_id, True)
    if row.author_id != user.id:
        raise HTTPException(403, 'Редактировать заметку может только её автор')
    messaging_limiter.check(f'business-note:{user.id}')
    require_feature(db, org.id, 'customer.notes')
    db.execute(update(BusinessEventNote).where(BusinessEventNote.id == row.id).values(revision=BusinessEventNote.revision)); db.refresh(row)
    if row.deleted:
        raise HTTPException(409, 'Заметка удалена')
    if row.body == body.body and row.revision == body.expected_revision + 1:
        return {'id': row.id, 'revision': row.revision, 'reused': True}
    if row.revision != body.expected_revision:
        raise HTTPException(409, 'Заметка изменена. Обновите список перед редактированием')
    row.body = body.body; row.revision += 1; row.updated_at = now()
    record(db, user, 'business.note_edited', 'business_note', row.id)
    db.commit()
    return {'id': row.id, 'revision': row.revision}


@router.delete('/business/notes/{note_id}')
def delete_note(note_id: UUID, expected_revision: int = Query(ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(BusinessEventNote, str(note_id))
    if not row:
        raise HTTPException(404, 'Заметка не найдена')
    _, _, member = event_access(db, user, row.event_id, True)
    if row.author_id != user.id and member.role not in {'owner', 'admin'}:
        raise HTTPException(403, 'Удалить чужую заметку может владелец или администратор')
    messaging_limiter.check(f'business-note:{user.id}')
    db.execute(update(BusinessEventNote).where(BusinessEventNote.id == row.id).values(revision=BusinessEventNote.revision)); db.refresh(row)
    if not row.deleted:
        if row.revision != expected_revision:
            raise HTTPException(409, 'Заметка изменена. Обновите список перед удалением')
        row.body = ''; row.deleted = True; row.revision += 1; row.updated_at = now()
        record(db, user, 'business.note_deleted', 'business_note', row.id)
        db.commit()
    return {'id': row.id, 'deleted': True}
