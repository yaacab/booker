"""Team capacity and authorization shared by direct membership and invitations."""
from fastapi import HTTPException
from sqlalchemy import update

from booker_api.commerce.entitlements import get_entitlements
from booker_api.models import Organization, TeamInvitation, TeamMember
from booker_api.security import now, require_org_member


def lock_team(db, user, org_id):
    org = db.get(Organization, str(org_id))
    if not org:
        raise HTTPException(404, 'Организация не найдена')
    require_org_member(db, user, org.id)
    db.execute(update(Organization).where(Organization.id == org.id).values(name=Organization.name))
    member = require_org_member(db, user, org.id)
    db.refresh(member) if member.id else None
    if member.role not in {'owner', 'admin'} and not user.is_platform_admin:
        raise HTTPException(403, 'Управлять командой может владелец или администратор')
    return org, member


def seat_limit(db, org):
    features = get_entitlements(db, org.id)['features']
    seats = features.get('team.seats', 1)
    if org.kind == 'customer' and not features.get('customer.multi_user'):
        return 1
    return max(1, seats) if type(seats) is int else 1


def authorize_role(user, actor, role):
    if role not in {'owner', 'admin', 'manager', 'viewer'}:
        raise HTTPException(422, 'Выберите допустимую роль участника')
    if role in {'owner', 'admin'} and actor.role != 'owner' and not user.is_platform_admin:
        raise HTTPException(403, 'Назначать владельцев и администраторов может только владелец')


def ensure_capacity(db, org, pending=0):
    count = db.query(TeamMember).filter_by(organization_id=org.id).count()
    if count + pending >= seat_limit(db, org):
        raise HTTPException(409, 'Лимит мест команды исчерпан. Освободите место или измените тариф')


def pending(db, org_id):
    return db.query(TeamInvitation).filter(TeamInvitation.organization_id == org_id, TeamInvitation.revoked.is_(False), TeamInvitation.accepted_at.is_(None), TeamInvitation.expires_at > now())

