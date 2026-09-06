from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Organization, Service, User
from booker_api.schemas import ServiceFromTemplateIn, ServiceIn, ServiceOut
from booker_api.security import audit, current_user, require_org_member, require_org_writer
from booker_api.service_templates import SERVICE_TEMPLATES, get_template
from booker_api.supply_completeness import supply_completeness as compute_supply_completeness

router = APIRouter(tags=["services"])


def _out(row: Service) -> dict:
    return ServiceOut.model_validate(row).model_dump()


@router.post("/services")
def create_service(body: ServiceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_org_writer(db, user, body.organization_id)
    row = Service(
        organization_id=body.organization_id,
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
            category_code=tpl["category_code"],
            title=tpl["title"],
            description=tpl["description"],
            city=body.city,
            honorarium_rub=body.honorarium_rub,
        ),
        user=user,
        db=db,
    )


@router.get("/services/public")
def list_public_services(
    category: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Service).filter(Service.published.is_(True))
    if category:
        q = q.filter(Service.category_code == category.strip().lower())
    return {"items": [_out(row) for row in q.all()]}


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
