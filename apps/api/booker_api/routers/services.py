from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Artist, Organization, Service, User, Venue
from booker_api.publication_eligibility import (
    artist_publication_eligibility,
    venue_publication_eligibility,
)
from booker_api.schemas import ServiceFromTemplateIn, ServiceIn, ServiceOut, ServiceProfileBindingIn
from booker_api.security import audit, current_user, require_org_member, require_org_writer
from booker_api.service_templates import SERVICE_TEMPLATES, get_template
from booker_api.supply_completeness import supply_completeness as compute_supply_completeness

router = APIRouter(tags=["services"])


def _out(row: Service) -> dict:
    return ServiceOut.model_validate(row).model_dump()


def _service_profile(db: Session, row: Service) -> Artist | Venue | None:
    if row.resource_type == "artist" and row.resource_id:
        profile = db.get(Artist, row.resource_id)
    elif row.resource_type == "venue" and row.resource_id:
        profile = db.get(Venue, row.resource_id)
    else:
        return None
    if not profile or profile.organization_id != row.organization_id:
        return None
    if isinstance(profile, Artist) and profile.category != row.category_code:
        return None
    if isinstance(profile, Venue) and row.category_code != "venue":
        return None
    return profile


def _binding_for_create(db: Session, body: ServiceIn) -> tuple[str | None, str | None]:
    if body.resource_type and body.resource_id:
        profile = (
            db.get(Artist, body.resource_id)
            if body.resource_type == "artist"
            else db.get(Venue, body.resource_id)
        )
        if not profile or profile.organization_id != body.organization_id:
            raise HTTPException(404, "Профиль не найден")
        if isinstance(profile, Artist) and profile.category != body.category_code:
            raise HTTPException(400, "Категория услуги не совпадает с категорией артиста")
        if isinstance(profile, Venue) and body.category_code != "venue":
            raise HTTPException(400, "Профиль площадки требует категорию venue")
        return body.resource_type, body.resource_id
    artists = db.query(Artist).filter(Artist.organization_id == body.organization_id).all()
    venues = db.query(Venue).filter(Venue.organization_id == body.organization_id).all()
    if len(artists) + len(venues) == 1:
        if artists and artists[0].category == body.category_code:
            return "artist", artists[0].id
        if venues and body.category_code == "venue":
            return "venue", venues[0].id
    return None, None


@router.post("/services")
def create_service(body: ServiceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_org_writer(db, user, body.organization_id)
    resource_type, resource_id = _binding_for_create(db, body)
    row = Service(
        organization_id=body.organization_id,
        resource_type=resource_type,
        resource_id=resource_id,
        category_code=body.category_code,
        title=body.title,
        description=body.description,
        city=body.city,
        published=body.published,
        honorarium_rub=body.honorarium_rub,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="service.created",
        entity_type="service",
        entity_id=row.id,
        payload={"organization_id": body.organization_id, "category_code": body.category_code},
    )
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/service-templates")
def list_service_templates():
    return {"items": list(SERVICE_TEMPLATES)}


@router.post("/services/from-template")
def create_service_from_template(
    body: ServiceFromTemplateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_org_writer(db, user, body.organization_id)
    tpl = get_template(body.template_id)
    if not tpl:
        raise HTTPException(404, "Шаблон не найден")
    return create_service(
        ServiceIn(
            organization_id=body.organization_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            category_code=tpl["category_code"],
            title=tpl["title"],
            description=tpl["description"],
            city=body.city,
            honorarium_rub=body.honorarium_rub,
        ),
        user=user,
        db=db,
    )


@router.put("/services/{service_id}/profile")
def bind_service_profile(
    service_id: str,
    body: ServiceProfileBindingIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(Service, service_id)
    if not row:
        raise HTTPException(404, "Услуга не найдена")
    require_org_writer(db, user, row.organization_id)
    resource_type, resource_id = _binding_for_create(
        db,
        ServiceIn(
            organization_id=row.organization_id,
            category_code=row.category_code,
            title=row.title,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
        ),
    )
    if row.resource_type != resource_type or row.resource_id != resource_id:
        row.resource_type = resource_type
        row.resource_id = resource_id
        audit(
            db,
            actor_user_id=user.id,
            action="service.profile_bound",
            entity_type="service",
            entity_id=row.id,
            payload={"resource_type": resource_type, "resource_id": resource_id},
        )
        db.commit()
    return _out(row)


@router.get("/services/public")
def list_public_services(
    category: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Service).filter(Service.published.is_(True))
    if category:
        q = q.filter(Service.category_code == category.strip().lower())
    items = []
    for row in q.all():
        profile = _service_profile(db, row)
        if isinstance(profile, Artist):
            eligible = artist_publication_eligibility(db, profile).eligible
        elif isinstance(profile, Venue):
            eligible = venue_publication_eligibility(db, profile).eligible
        else:
            eligible = False
        if eligible:
            items.append(_out(row))
    return {"items": items}


@router.get("/organizations/{org_id}/supply-completeness")
def get_supply_completeness(
    org_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_org_member(db, user, org_id)
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    return compute_supply_completeness(db, org)


@router.get("/services")
def list_services(
    organization_id: str = Query(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_org_member(db, user, organization_id)
    rows = db.query(Service).filter(Service.organization_id == organization_id).all()
    return {"items": [_out(row) for row in rows]}
