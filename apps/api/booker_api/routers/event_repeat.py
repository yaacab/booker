"""Repeat completed events without carrying forward any deal state."""
from collections import Counter
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.db import get_db
from booker_api.event_commands import remember_command, replay_command
from booker_api.matching import MatchingContext, clean_selection
from booker_api.models import (
    Artist,
    AvailabilitySlot,
    Booking,
    Event,
    EventRepeatPreference,
    EventTeamRequirement,
    Offer,
    Request,
    User,
    Venue,
    VenueHall,
)
from booker_api.rate_limit import analytics_limiter, upload_limiter
from booker_api.security import (
    audit,
    aware,
    current_user,
    now,
    require_org_member,
    require_org_writer,
)

router = APIRouter(tags=["repeat event"])


class RepeatIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=255)
    event_date: datetime
    ends_at: datetime
    preferred_request_ids: list[UUID] = Field(default_factory=list, max_length=600)


def source_event(db, user, event_id, writer=False):
    event = db.get(Event, str(event_id))
    if not event:
        raise HTTPException(404, "Событие не найдено")
    member = (require_org_writer if writer else require_org_member)(db, user, event.organization_id)
    return event, member


def requirements(db, event):
    return db.query(EventTeamRequirement).filter_by(event_id=event.id).order_by(EventTeamRequirement.sort_order, EventTeamRequirement.id).all()


def profile(db, kind, resource_id, hall_id):
    if kind == 'artist':
        row = db.get(Artist, resource_id)
        return (row.name, row.category) if row else None
    venue = db.get(Venue, resource_id)
    hall = db.get(VenueHall, hall_id) if hall_id else None
    if venue and venue.moderation_status == 'published' and (not hall_id or hall and hall.venue_id == venue.id):
        return (f'{venue.name} · {hall.name}' if hall else venue.name, 'venue')
    return None


def participants(db, event):
    rows = db.query(Request, Booking).join(Offer, Offer.request_id == Request.id).join(Booking, Booking.offer_id == Offer.id).filter(Request.event_id == event.id, Booking.event_id == event.id, Booking.status == 'Completed').order_by(Request.id).all()
    result, seen = [], set()
    for req, booking in rows:
        kind, target, hall = req.resource_type, req.resource_id, None
        if kind in {'hall', 'venue'}:
            slot = db.get(AvailabilitySlot, booking.slot_id) if booking.slot_id else None
            room = db.get(VenueHall, req.resource_id if kind == 'hall' else slot.resource_id) if kind == 'hall' or slot and slot.resource_type == 'hall' else None
            if room and (kind == 'hall' or room.venue_id == target):
                kind, target, hall = 'venue', room.venue_id, room.id
            elif kind == 'hall':
                continue
        if kind not in {'artist', 'venue'} or (kind, target, hall) in seen:
            continue
        seen.add((kind, target, hall))
        fact = profile(db, kind, target, hall)
        result.append({'source_request_id': req.id, 'source_requirement_id': req.requirement_id, 'resource_type': kind, 'resource_id': target,
            'hall_id': hall, 'name': fact[0] if fact else 'Профиль недоступен', 'category': fact[1] if fact else None, 'can_prefer': bool(fact)})
    return result


@router.get('/events/{event_id}/repeat-options')
def repeat_options(event_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event, member = source_event(db, user, event_id)
    analytics_limiter.check(f'repeat-options:{user.id}')
    if event.status != 'Completed':
        raise HTTPException(409, 'Повтор доступен после завершения события')
    result = {'title': (event.title+' · повтор')[:255], 'city': event.city, 'event_type': event.event_type, 'guest_count': event.guest_count,
        'roles': [{'label': r.role_label, 'qty': r.qty, 'required': r.required} for r in requirements(db, event)],
        'participants': participants(db, event), 'can_manage': member.role in {'owner', 'admin', 'manager'} and settings.repeat_events,
        'enabled': settings.repeat_events}
    audit(db, actor_user_id=user.id, action='repeat_event.viewed', entity_type='event', entity_id=event.id, payload={})
    db.commit()
    return result


@router.post('/events/{event_id}/repeat', status_code=201)
def repeat_event(event_id: UUID, body: RepeatIn, user: User = Depends(current_user), db: Session = Depends(get_db),
    idempotency_key: str = Header(alias='Idempotency-Key', min_length=8, max_length=160)):
    event, _ = source_event(db, user, event_id, writer=True)
    if not settings.repeat_events:
        raise HTTPException(503, 'Повтор событий временно отключён')
    upload_limiter.check(f'repeat-event:{user.id}')
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title)); db.refresh(event)
    command = body.model_dump(mode='json')
    scope = f'event.repeat:{event.id}'
    cached = replay_command(db, scope, idempotency_key, command)
    if cached:
        return cached
    if event.status != 'Completed':
        raise HTTPException(409, 'Повтор доступен после завершения события')
    if aware(body.event_date) <= now() or aware(body.ends_at) <= aware(body.event_date):
        raise HTTPException(422, 'Укажите новое будущее начало и окончание позже начала')
    selected = [str(i) for i in body.preferred_request_ids]
    candidates = {p['source_request_id']: p for p in participants(db, event)}
    if len(set(selected)) != len(selected) or any(i not in candidates or not candidates[i]['can_prefer'] for i in selected):
        raise HTTPException(409, 'Обновите список участников завершённого события')
    draft = Event(organization_id=event.organization_id, title=body.title, city=event.city, event_type=event.event_type,
        event_date=aware(body.event_date), ends_at=aware(body.ends_at), guest_count=event.guest_count, status='Draft', budget_rub=None, notes='')
    db.add(draft); db.flush()
    roles, mapping = [], {}
    for old in requirements(db, event):
        role = EventTeamRequirement(event_id=draft.id, category_code=old.category_code, role_label=old.role_label, qty=old.qty,
            required=old.required, status='open', sort_order=old.sort_order, notes='')
        db.add(role); db.flush(); roles.append(role); mapping[old.id] = role
    used = Counter()
    for request_id in selected:
        candidate = candidates[request_id]
        role = mapping.get(candidate['source_requirement_id'])
        if not role:
            possible = [r for r in roles if r.category_code == candidate['category']]
            role = possible[0] if len(possible) == 1 else None
        position = used[role.id] if role and used[role.id] < role.qty else None
        if role and position is not None:
            used[role.id] += 1
        db.add(EventRepeatPreference(event_id=draft.id, requirement_id=role.id if role else None, position=position,
            resource_type=candidate['resource_type'], resource_id=candidate['resource_id'], hall_id=candidate['hall_id']))
    result = {'id': draft.id, 'status': 'Draft', 'preferred_count': len(selected), 'requires_new_availability': True}
    remember_command(db, scope, idempotency_key, command, result)
    audit(db, actor_user_id=user.id, action='repeat_event.created', entity_type='event', entity_id=draft.id,
        payload={'roles': len(roles), 'preferred_count': len(selected)})
    db.commit()
    return result


@router.get('/events/{event_id}/repeat-preferences')
def repeat_preferences(event_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event, member = source_event(db, user, event_id)
    analytics_limiter.check(f'repeat-preferences:{user.id}')
    prefs = db.query(EventRepeatPreference).filter_by(event_id=event.id).order_by(EventRepeatPreference.id).all()
    if not prefs:
        return {'items': []}
    ctx = MatchingContext(db, event) if settings.smart_matching else None
    items = []
    for pref in prefs:
        fact = profile(db, pref.resource_type, pref.resource_id, pref.hall_id)
        selection = {k: getattr(pref, k) for k in ('requirement_id', 'position', 'resource_type', 'resource_id', 'hall_id')}
        current = [clean_selection(s) for s in ctx.saved if s['requirement_id'] != pref.requirement_id or s['position'] != pref.position] if ctx else []
        problems = ctx.evaluate([*current, selection])['problems'] if ctx and pref.position is not None and fact else ['Уточните роль, позицию или профиль в подборе состава']
        if ctx and not ctx.window_known:
            problems = ['Укажите будущее окно события']
        items.append({'id': pref.id, 'name': fact[0] if fact else 'Профиль недоступен', 'selection': selection,
            'can_add': bool(ctx and settings.repeat_events and not problems and member.role in {'owner','admin','manager'} and event.status not in {'Completed','Cancelled'}),
            'problems': problems, 'already_selected': selection in (ctx.saved if ctx else [])})
    result = {'items': items, 'revision': ctx.revision if ctx else None, 'context_token': ctx.context_token if ctx else None, 'saved_selections': ctx.saved if ctx else []}
    audit(db, actor_user_id=user.id, action='repeat_event.preferences_viewed', entity_type='event', entity_id=event.id, payload={'count': len(items)})
    db.commit()
    return result
