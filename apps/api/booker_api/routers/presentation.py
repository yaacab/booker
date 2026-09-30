import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.composition import seed_categories
from booker_api.db import get_db
from booker_api.models import Artist, ArtistPresentation, CatalogCategory, User
from booker_api.presentation import PresentationData, presentation_data, presentation_limits
from booker_api.rate_limit import upload_limiter
from booker_api.security import audit, current_user, now, require_org_member, require_org_writer

router = APIRouter(tags=["artist-presentation"])


class PresentationIn(PresentationData):
    expected_version: int = Field(ge=0, strict=True)


def get_owned_artist(db, artist_id, user, writer=False):
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Артист не найден")
    (require_org_writer if writer else require_org_member)(db, user, artist.organization_id)
    return artist


@router.get("/artists/{artist_id}/presentation")
def read_presentation(artist_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artist = get_owned_artist(db, artist_id, user)
    version, data = presentation_data(db, artist)
    return {"version": version, "data": data, "limits": presentation_limits(db, artist)}


@router.put("/artists/{artist_id}/presentation")
def save_presentation(artist_id: str, body: PresentationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artist = get_owned_artist(db, artist_id, user, writer=True)
    upload_limiter.check(f"presentation:{user.id}")
    seed_categories(db)
    category = db.query(CatalogCategory).filter_by(code=body.category).one_or_none()
    if not category or body.category == "venue":
        raise HTTPException(422, "Выберите категорию исполнителя из каталога")
    db.execute(update(Artist).where(Artist.id == artist_id).values(name=Artist.name))
    db.refresh(artist)
    version, old = presentation_data(db, artist)
    data = body.model_dump(exclude={"expected_version"})
    if data == old and body.expected_version <= version:
        return {"version": version, "data": old, "limits": presentation_limits(db, artist), "idempotent": True}
    if version != body.expected_version:
        raise HTTPException(409, "Витрина уже изменена. Загрузите актуальную версию перед сохранением")
    limits = presentation_limits(db, artist)
    for field in ("gallery", "links", "travel_cities"):
        if len(data[field]) > limits[field] and data[field] != old.get(field):
            raise HTTPException(403, "Объём портфолио или географии превышает возможности тарифа")
    if data["layout"] != "standard" and not limits["advanced_layout"] and data["layout"] != old.get("layout"):
        raise HTTPException(403, "Настройка витрины доступна на расширенном тарифе")
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True)
    row = db.get(ArtistPresentation, artist_id)
    if row:
        row.version += 1
        row.data_json = serialized
        row.updated_at = now()
    else:
        row = ArtistPresentation(artist_id=artist_id, version=1, data_json=serialized)
        db.add(row)
    artist.name, artist.city, artist.category = data["name"], data["city"], data["category"]
    try:
        rider = json.loads(artist.rider_json or "{}")
    except (TypeError, ValueError):
        rider = {}
    if not isinstance(rider, dict):
        rider = {}
    rider.update(format=data["format"], lineup=data["lineup"], tech=data["rider_text"], travel_cities=data["travel_cities"])
    if data["technical"]["supplied_equipment"] is not None:
        rider["equipment"] = data["technical"]["supplied_equipment"]
    artist.rider_json = json.dumps(rider, ensure_ascii=False)
    audit(db, actor_user_id=user.id, action="artist.presentation_updated", entity_type="artist", entity_id=artist.id,
          payload={"version": row.version, "media_rights_confirmed": body.media_rights_confirmed})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Витрина уже изменена. Обновите страницу") from None
    return {"version": row.version, "data": data, "limits": limits}
