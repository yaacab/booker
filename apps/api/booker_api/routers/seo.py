"""Public discovery for crawlers: no paid ranking, calendar inference or tracking."""
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Artist, ArtistPresentation, ArtistTariff, Venue, VenueTariff
from booker_api.rate_limit import analytics_limiter, client_key
from booker_api.venue_catalog import publicly_listed_venue_query

router = APIRouter(prefix='/seo', tags=['catalog'])
PAGE_SIZE = 1000
# Pilot market, editorial copy. Other cities' public profiles are still indexed.
CITIES = {'moskva': ('Москва', 'в Москве')}
CATEGORIES = {
    'dj': ('DJ', 'Обсудите музыкальный формат, длительность сета и оборудование. Проверьте, кто привозит звук и как проходит монтаж.'),
    'host': ('Ведущие', 'Сравните стиль ведения и примеры мероприятий. До предложения согласуйте сценарий, язык программы и участие гостей.'),
    'cover': ('Кавер-группы', 'Уточните состав, репертуар и число музыкальных блоков. Сопоставьте райдер группы со сценой и звуком площадки.'),
    'photo': ('Фотографы', 'Посмотрите целые серии, а не только отдельные кадры. Согласуйте часы работы, объём обработки и срок передачи фотографий.'),
    'makeup': ('Визажисты', 'Сравните примеры образов и уточните количество гостей. Заранее обсудите рабочее место, освещение и время на подготовку.'),
    'decor': ('Декораторы', 'Опишите концепцию и размеры пространства. Уточните состав оформления, доставку, монтаж и демонтаж.'),
    'catering': ('Кейтеринг', 'Согласуйте меню, число гостей и формат подачи. Обсудите состав блюд, диетические ограничения, персонал и условия площадки.'),
    'venues': ('Площадки', 'Сопоставьте вместимость и рассадку с программой события. Уточните оборудование, время монтажа, ограничения по звуку и условия доступа.'),
}


def public_query(db, kind, *, at=None):
    return db.query(Artist) if kind == 'artists' else publicly_listed_venue_query(db, at=at)


def collections(db, *, at=None):
    result = []
    for slug, (city, suffix) in CITIES.items():
        groups = dict(db.query(Artist.category, func.count(Artist.id)).filter(Artist.city == city).group_by(Artist.category).all())
        groups['venues'] = public_query(db, 'venues', at=at).filter(Venue.city == city).count()
        for category, (label, description) in CATEGORIES.items():
            count = groups.get(category, 0)
            if count >= 3:
                result.append({'path': f'/catalog/{slug}/{category}', 'city_slug': slug, 'city': city,
                    'category': category, 'title': f'{label} {suffix}', 'description': description, 'count': count})
    return result


@router.get('/index')
def index(request: Request, db: Session = Depends(get_db)):
    analytics_limiter.check(client_key(request, 'seo-index'))
    at = datetime.now(timezone.utc)
    return {'page_size': PAGE_SIZE, 'counts': {kind: public_query(db, kind, at=at).count() for kind in ('artists', 'venues')},
        'collections': collections(db, at=at)}


@router.get('/profiles')
def profiles(request: Request, kind: Literal['artists', 'venues'], page: int = Query(0, ge=0, le=50000), db: Session = Depends(get_db)):
    analytics_limiter.check(client_key(request, 'seo-profiles'))
    model = Artist if kind == 'artists' else Venue
    rows = public_query(db, kind, at=datetime.now(timezone.utc)).with_entities(model.id).order_by(model.id).offset(page * PAGE_SIZE).limit(PAGE_SIZE).all()
    return {'items': [{'path': f'/{kind}/{row.id}'} for row in rows]}


@router.get('/collections/{city_slug}/{category}')
def collection(city_slug: str, category: str, request: Request, page: int = Query(0, ge=0, le=10000), db: Session = Depends(get_db)):
    analytics_limiter.check(client_key(request, 'seo-collection'))
    at = datetime.now(timezone.utc)
    info = next((item for item in collections(db, at=at) if item['city_slug'] == city_slug and item['category'] == category), None)
    if not info:
        raise HTTPException(404, 'Подборка пока недоступна')
    kind = 'venues' if category == 'venues' else 'artists'
    model, tariff = (Venue, VenueTariff) if kind == 'venues' else (Artist, ArtistTariff)
    foreign_id = tariff.venue_id if kind == 'venues' else tariff.artist_id
    minimum = db.query(foreign_id.label('profile_id'), func.min(tariff.honorarium_rub).label('amount')).group_by(foreign_id).subquery()
    query = public_query(db, kind, at=at).filter(model.city == info['city'])
    if kind == 'artists':
        query = query.filter(Artist.category == category)
    rows = query.outerjoin(minimum, minimum.c.profile_id == model.id).add_columns(minimum.c.amount).order_by(model.name, model.id).offset(page * 24).limit(25).all()
    if page and not rows:
        raise HTTPException(404, 'Страница подборки не найдена')
    presentations = {row.artist_id: row for row in db.query(ArtistPresentation).filter(ArtistPresentation.artist_id.in_([row.id for row, _ in rows])).all()} if kind == 'artists' else {}
    items = []
    for row, amount in rows[:24]:
        detail = ''
        if kind == 'venues':
            detail = ' · '.join(value for value in (row.district, row.metro) if value)
        elif row.id in presentations:
            data = json.loads(presentations[row.id].data_json)
            detail = data.get('format', '') if isinstance(data.get('format'), str) else ''
        items.append({'id': row.id, 'kind': 'artist' if kind == 'artists' else 'venue', 'path': f'/{kind}/{row.id}', 'name': row.name, 'city': row.city,
            'detail': detail[:240], 'honorarium_from_rub': amount,
            'availability_note': 'Дату и условия нужно уточнить в профиле и предложении.'})
    return {**info, 'items': items, 'page': page, 'has_more': len(rows) > 24}
