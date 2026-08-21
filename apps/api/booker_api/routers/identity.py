from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from booker_api.composition import ALLOWED_ORG_KINDS, ALLOWED_ROLES, normalize_kind
from booker_api.db import get_db
from booker_api.models import Organization, TeamMember, User
from booker_api.schemas import LoginIn, MemberIn, OrgIn, RegisterIn
from booker_api.security import (
    audit,
    current_user,
    hash_password,
    issue_token,
    require_org_member,
    verify_password,
)

router = APIRouter(tags=["identity"])


@router.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email уже занят")
    user = User(
        email=body.email.lower(),
        phone=body.phone,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="user.registered",
        entity_type="user",
        entity_id=user.id,
        payload={
            "legal_pack_version": "2026-08-18-draft",
            "accept_offer": True,
            "accept_privacy": True,
            "marketing_opt_in": body.marketing_opt_in,
        },
    )
    token = issue_token(db, user)
    db.commit()
    return {"token": token, "user_id": user.id, "is_platform_admin": False}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    token = issue_token(db, user)
    db.commit()
    return {"token": token, "user_id": user.id, "is_platform_admin": user.is_platform_admin}


@router.post("/auth/recover")
def recover(body: dict):
    _ = body.get("email")
    return {"ok": True, "message": "Если такой email есть, отправим ссылку. На пилоте письмо не уходит."}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    members = db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
    orgs = []
    for m in members:
        org = db.get(Organization, m.organization_id)
        orgs.append(
            {
                "id": m.organization_id,
                "name": org.name if org else "",
                "kind": org.kind if org else "",
                "role": m.role,
                "can_confirm_offer": m.can_confirm_offer,
            }
        )
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_platform_admin": user.is_platform_admin,
        "organizations": orgs,
        "active_organization_id": user.active_organization_id or (orgs[0]["id"] if orgs else None),
    }


@router.post("/orgs")
def create_org(body: OrgIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kind = normalize_kind(body.kind)
    if kind not in ALLOWED_ORG_KINDS:
        raise HTTPException(400, "kind: customer|artist|venue")
    org = Organization(name=body.name, kind=kind, city=body.city)
    db.add(org)
    db.flush()
    db.add(
        TeamMember(
            user_id=user.id,
            organization_id=org.id,
            role="owner",
            can_confirm_offer=True,
        )
    )
    user.active_organization_id = org.id
    audit(
        db,
        actor_user_id=user.id,
        action="org.created",
        entity_type="organization",
        entity_id=org.id,
    )
    db.commit()
    return {"id": org.id, "kind": org.kind, "name": org.name}


@router.get("/orgs/{org_id}")
def get_org(org_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    require_org_member(db, user, org_id)
    members = db.query(TeamMember).filter(TeamMember.organization_id == org_id).all()
    return {
        "id": org.id,
        "name": org.name,
        "kind": org.kind,
        "city": org.city,
        "members": [
            {
                "user_id": m.user_id,
                "role": m.role,
                "can_confirm_offer": m.can_confirm_offer,
            }
            for m in members
        ],
    }


@router.post("/orgs/{org_id}/members")
def add_member(
    org_id: str,
    body: MemberIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    owner = require_org_member(db, user, org_id)
    if owner.role not in {"owner", "admin"} and not user.is_platform_admin:
        raise HTTPException(403, "Только владелец добавляет команду")
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(400, "role: owner|admin|manager|viewer")
    if not db.get(User, body.user_id):
        raise HTTPException(404, "Пользователь не найден")
    confirm = False if body.role == "viewer" else body.can_confirm_offer
    member = TeamMember(
        user_id=body.user_id,
        organization_id=org_id,
        role=body.role,
        can_confirm_offer=confirm,
    )
    db.add(member)
    db.commit()
    return {"id": member.id, "can_confirm_offer": member.can_confirm_offer}


@router.post("/me/active-org")
def set_active_org(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org_id = body.get("organization_id")
    if not org_id:
        raise HTTPException(400, "organization_id обязателен")
    require_org_member(db, user, org_id)
    user.active_organization_id = org_id
    db.commit()
    return {"active_organization_id": org_id}
