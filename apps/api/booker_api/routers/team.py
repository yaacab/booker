"""Account-bound invitation acceptance; no automatic email or public team directory."""
import hashlib
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Organization, TeamInvitation, TeamMember, User
from booker_api.rate_limit import analytics_limiter, messaging_limiter
from booker_api.security import audit, aware, current_user, membership, now, require_org_member
from booker_api.team import authorize_role, ensure_capacity, lock_team, pending, seat_limit

router = APIRouter(tags=['team'])


class InviteIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    role: Literal['admin', 'manager', 'viewer'] = 'manager'
    can_confirm_offer: bool = False
    secret: str = Field(pattern=r'^[a-f0-9]{64}$')


class MemberEditIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['owner', 'admin', 'manager', 'viewer']
    can_confirm_offer: bool = False
    expected_role: str
    expected_can_confirm_offer: bool




def log(db, user, action, kind, target):
    audit(db, actor_user_id=user.id, action=action, entity_type=kind, entity_id=target, payload={})


@router.get('/orgs/{org_id}/team')
def get_team(org_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    actor = require_org_member(db, user, str(org_id))
    org = db.get(Organization, str(org_id))
    analytics_limiter.check(f'team:{user.id}')
    can_manage = actor.role in {'owner', 'admin'} or user.is_platform_admin
    members = db.query(TeamMember, User).join(User, User.id == TeamMember.user_id).filter(TeamMember.organization_id == org.id).order_by(User.full_name, TeamMember.id).all()
    invites = pending(db, org.id).order_by(TeamInvitation.created_at).all()
    limit = seat_limit(db, org)
    return {'organization_id': org.id, 'name': org.name, 'can_manage': can_manage,
        'can_assign_admin': actor.role == 'owner' or user.is_platform_admin, 'seats': limit, 'used': len(members), 'reserved': len(invites),
        'members': [{'id': m.id, 'name': u.full_name, 'role': m.role, 'can_confirm_offer': m.can_confirm_offer,
            'is_self': u.id == user.id, 'can_manage': can_manage and (actor.role == 'owner' or user.is_platform_admin or m.role in {'manager', 'viewer'})} for m, u in members],
        'invitations': [{'id': i.id, 'email': i.email, 'role': i.role, 'expires_at': aware(i.expires_at).isoformat()} for i in invites] if can_manage else []}


@router.post('/orgs/{org_id}/team/invitations', status_code=201)
def invite(org_id: UUID, body: InviteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org, actor = lock_team(db, user, org_id)
    messaging_limiter.check(f'team-invite:{user.id}')
    authorize_role(user, actor, body.role)
    digest = hashlib.sha256(body.secret.encode()).hexdigest()
    email = str(body.email).lower()
    confirm = body.can_confirm_offer and body.role != 'viewer'
    existing = db.query(TeamInvitation).filter_by(token_hash=digest).one_or_none()
    if existing:
        if (existing.organization_id, existing.email, existing.role, existing.can_confirm_offer) != (org.id, email, body.role, confirm):
            raise HTTPException(409, 'Этот ключ приглашения уже использован')
        return {'id': existing.id, 'expires_at': aware(existing.expires_at).isoformat(), 'reused': True}
    if db.query(TeamMember).join(User, User.id == TeamMember.user_id).filter(TeamMember.organization_id == org.id, User.email == email).first():
        raise HTTPException(409, 'Этот пользователь уже в команде')
    if pending(db, org.id).filter(TeamInvitation.email == email).first():
        raise HTTPException(409, 'Для этого адреса уже есть активное приглашение')
    ensure_capacity(db, org, pending(db, org.id).count())
    row = TeamInvitation(organization_id=org.id, email=email, role=body.role, can_confirm_offer=confirm,
        token_hash=digest, created_by=user.id, expires_at=now()+timedelta(days=7))
    db.add(row); db.flush(); log(db, user, 'team.invited', 'team_invitation', row.id); db.commit()
    return {'id': row.id, 'expires_at': aware(row.expires_at).isoformat()}


@router.post('/orgs/{org_id}/team/invitations/{invite_id}/revoke')
def revoke(org_id: UUID, invite_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org, _ = lock_team(db, user, org_id)
    messaging_limiter.check(f'team-invite:{user.id}')
    row = db.get(TeamInvitation, str(invite_id))
    if not row or row.organization_id != org.id:
        raise HTTPException(404, 'Приглашение не найдено')
    if not row.revoked:
        row.revoked = True; log(db, user, 'team.invitation_revoked', 'team_invitation', row.id); db.commit()
    return {'revoked': True}


def invitation(db, secret):
    if not secret or len(secret) != 64:
        raise HTTPException(404, 'Приглашение недоступно')
    row = db.query(TeamInvitation).filter_by(token_hash=hashlib.sha256(secret.encode()).hexdigest()).one_or_none()
    if not row:
        raise HTTPException(404, 'Приглашение недоступно')
    return row


@router.post('/team-invitations/accept')
def accept(user: User = Depends(current_user), db: Session = Depends(get_db), secret: str = Header(alias='X-Team-Invitation', min_length=64, max_length=64)):
    messaging_limiter.check(f'team-accept:{user.id}')
    row = invitation(db, secret)
    org = db.get(Organization, row.organization_id)
    db.execute(update(Organization).where(Organization.id == org.id).values(name=Organization.name)); db.refresh(row)
    if row.email != user.email.lower():
        raise HTTPException(403, 'Войдите с адресом, для которого создано приглашение')
    member = membership(db, user.id, org.id)
    if row.accepted_by == user.id and member:
        return {'organization_id': org.id, 'name': org.name, 'reused': True}
    if row.revoked or row.accepted_at or aware(row.expires_at) <= now():
        raise HTTPException(410, 'Приглашение отозвано, использовано или истекло')
    # Recheck current inviter privileges and current plan at acceptance, not just at issue.
    creator = membership(db, row.created_by, org.id)
    creator_user = db.get(User, row.created_by)
    platform_authorized = bool(creator_user and creator_user.is_platform_admin)
    if not platform_authorized and (not creator or creator.role not in {'owner', 'admin'} or row.role == 'admin' and creator.role != 'owner'):
        raise HTTPException(410, 'Создатель приглашения больше не может приглашать эту роль')
    if not member:
        ensure_capacity(db, org, max(0, pending(db, org.id).count()-1))
        member = TeamMember(user_id=user.id, organization_id=org.id, role=row.role, can_confirm_offer=row.can_confirm_offer)
        db.add(member)
    row.accepted_by = user.id; row.accepted_at = now()
    log(db, user, 'team.invitation_accepted', 'team_invitation', row.id); db.commit()
    return {'organization_id': org.id, 'name': org.name}


@router.put('/orgs/{org_id}/team/members/{member_id}')
def edit(org_id: UUID, member_id: UUID, body: MemberEditIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org, actor = lock_team(db, user, org_id)
    messaging_limiter.check(f'team-member:{user.id}')
    row = db.get(TeamMember, str(member_id))
    if not row or row.organization_id != org.id:
        raise HTTPException(404, 'Участник не найден')
    authorize_role(user, actor, row.role); authorize_role(user, actor, body.role)
    confirm = body.can_confirm_offer and body.role != 'viewer'
    if (row.role, row.can_confirm_offer) == (body.role, confirm):
        return {'id': row.id, 'reused': True}
    if (row.role, row.can_confirm_offer) != (body.expected_role, body.expected_can_confirm_offer):
        raise HTTPException(409, 'Права участника изменились. Обновите команду')
    if row.role == 'owner' and body.role != 'owner' and db.query(TeamMember).filter_by(organization_id=org.id, role='owner').count() <= 1:
        raise HTTPException(409, 'В команде должен остаться хотя бы один владелец')
    row.role = body.role; row.can_confirm_offer = confirm
    log(db, user, 'team.member_updated', 'team_member', row.id); db.commit()
    return {'id': row.id}


@router.delete('/orgs/{org_id}/team/members/{member_id}')
def remove(org_id: UUID, member_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org, actor = lock_team(db, user, org_id)
    messaging_limiter.check(f'team-member:{user.id}')
    row = db.get(TeamMember, str(member_id))
    if not row:
        return {'removed': True}
    if row.organization_id != org.id:
        raise HTTPException(404, 'Участник не найден')
    authorize_role(user, actor, row.role)
    if row.role == 'owner' and db.query(TeamMember).filter_by(organization_id=org.id, role='owner').count() <= 1:
        raise HTTPException(409, 'Нельзя удалить последнего владельца')
    target = db.get(User, row.user_id)
    if target.active_organization_id == org.id:
        target.active_organization_id = None
    log(db, user, 'team.member_removed', 'team_member', row.id); db.delete(row); db.commit()
    return {'removed': True}


@router.post('/team-invitations/preview')
def preview(user: User = Depends(current_user), db: Session = Depends(get_db), secret: str = Header(alias='X-Team-Invitation', min_length=64, max_length=64)):
    analytics_limiter.check(f'team-preview:{user.id}')
    row = invitation(db, secret)
    if row.email != user.email.lower():
        raise HTTPException(403, 'Войдите с адресом, для которого создано приглашение')
    if row.accepted_by == user.id and membership(db, user.id, row.organization_id):
        return {'name': db.get(Organization, row.organization_id).name, 'accepted': True}
    if row.revoked or aware(row.expires_at) <= now() or row.accepted_at:
        raise HTTPException(410, 'Приглашение отозвано, использовано или истекло')
    org = db.get(Organization, row.organization_id)
    return {'name': org.name, 'role': row.role, 'can_confirm_offer': row.can_confirm_offer, 'expires_at': aware(row.expires_at).isoformat()}
