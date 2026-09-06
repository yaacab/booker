"""Демо-данные для локального контура Букер."""

import os
from datetime import timedelta

from sqlalchemy.orm import Session

from booker_api.db import SessionLocal, engine, init_schema
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Organization,
    Service,
    TeamMember,
    User,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.security import hash_password, now

DEMO_PASSWORD = "password1"


def _ensure_venue_user(db: Session) -> bool:
    """Владелец площадки «Клуб Сигнал» для cross-role E2E."""
    venue = db.query(Venue).filter(Venue.name == "Клуб Сигнал").one_or_none()
    if not venue:
        return False
    user = db.query(User).filter(User.email == "venue@booker.test").one_or_none()
    if not user:
        user = User(
            email="venue@booker.test",
            full_name="Мария Площадка",
            phone="+79003333333",
            password_hash=hash_password(DEMO_PASSWORD),
        )
        db.add(user)
        db.flush()
    org = db.get(Organization, venue.organization_id)
    if not org:
        return False
    member = (
        db.query(TeamMember)
        .filter(TeamMember.user_id == user.id, TeamMember.organization_id == org.id)
        .one_or_none()
    )
    if not member:
        db.add(
            TeamMember(
                user_id=user.id,
                organization_id=org.id,
                role="owner",
                can_confirm_offer=True,
            )
        )
        return True
    return False


def _open_in_horizon(db: Session, resource_type: str, resource_id: str) -> bool:
    horizon_end = now() + timedelta(days=30)
    return (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.resource_type == resource_type,
            AvailabilitySlot.resource_id == resource_id,
            AvailabilitySlot.status == "open",
            AvailabilitySlot.ends_at >= now(),
            AvailabilitySlot.starts_at <= horizon_end,
        )
        .count()
        > 0
    )


def _ensure_cross_role_catalog(db: Session) -> int:
    """Open-слоты в горизонте 30д для cross-role E2E после исчерпания seed-слотов."""
    added = 0
    nova = db.query(Artist).filter(Artist.name == "DJ Nova").one_or_none()
    if nova and not _open_in_horizon(db, "artist", nova.id):
        db.add(_slot("artist", nova.id, 14, 18))
        added += 1
    venue = db.query(Venue).filter(Venue.name == "Клуб Сигнал").one_or_none()
    if venue:
        hall = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).first()
        if hall and not _open_in_horizon(db, "hall", hall.id):
            db.add(_slot("hall", hall.id, 14, 19))
            added += 1
    return added


def seed(db: Session) -> dict[str, str]:
    if db.query(User).filter(User.email == "customer@booker.test").one_or_none():
        added = enrich_catalog(db)
        added += _ensure_cross_role_catalog(db)
        venue_user_added = _ensure_venue_user(db)
        db.commit()
        return {"status": "already_seeded", "catalog_added": added, "venue_user_added": venue_user_added}

    customer = User(
        email="customer@booker.test",
        full_name="Анна Заказчица",
        phone="+79001111111",
        password_hash=hash_password(DEMO_PASSWORD),
    )
    artist_user = User(
        email="artist@booker.test",
        full_name="Илья Букер",
        phone="+79002222222",
        password_hash=hash_password(DEMO_PASSWORD),
    )
    admin = User(
        email="admin@booker.test",
        full_name="Админ Букер",
        password_hash=hash_password(DEMO_PASSWORD),
        is_platform_admin=True,
        totp_enabled=True,
        totp_secret="JBSWY3DPEHPK3PXP",
    )
    db.add_all([customer, artist_user, admin])
    db.flush()

    cust_org = Organization(name="Студия события", kind="customer", city="Москва")
    artist_org = Organization(name="Nova Show", kind="artist", city="Москва")
    db.add_all([cust_org, artist_org])
    db.flush()
    db.add_all(
        [
            TeamMember(
                user_id=customer.id,
                organization_id=cust_org.id,
                role="owner",
                can_confirm_offer=True,
            ),
            TeamMember(
                user_id=artist_user.id,
                organization_id=artist_org.id,
                role="owner",
                can_confirm_offer=True,
            ),
        ]
    )
    artist = Artist(
        organization_id=artist_org.id,
        name="DJ Nova",
        city="Москва",
        category="dj",
        verified=True,
        verified_status="approved",
        media_url="",
        rider_json='{"format":"DJ-сет 2 часа","formats":["club","wedding"],"travel_ok":true,"lineup":"1 человек","tech":"пульт, 2 колонки"}',
    )
    db.add(artist)
    db.flush()
    db.add(ArtistTariff(artist_id=artist.id, title="Сет 2 часа", honorarium_rub=100000, hours=2))
    start = now() + timedelta(days=14)
    start = start.replace(hour=18, minute=0, second=0, microsecond=0)
    db.add(
        AvailabilitySlot(
            resource_type="artist",
            resource_id=artist.id,
            starts_at=start,
            ends_at=start + timedelta(hours=4),
            status="open",
        )
    )
    db.commit()
    enrich_catalog(db)
    _ensure_cross_role_catalog(db)
    db.commit()
    _ensure_venue_user(db)
    return {
        "status": "ok",
        "customer": "customer@booker.test",
        "artist": "artist@booker.test",
        "venue": "venue@booker.test",
        "admin": "admin@booker.test",
        "password": DEMO_PASSWORD,
        "artist_id": artist.id,
    }


def _slot(resource_type: str, resource_id: str, days: int, hour: int) -> AvailabilitySlot:
    start = now() + timedelta(days=days)
    start = start.replace(hour=hour, minute=0, second=0, microsecond=0)
    return AvailabilitySlot(
        resource_type=resource_type,
        resource_id=resource_id,
        starts_at=start,
        ends_at=start + timedelta(hours=4),
        status="open",
    )


def enrich_catalog(db: Session) -> int:
    """Добирает демо-каталог, даже если пользователи уже созданы."""
    added = 0
    # ~30 founding artists (DJ Nova создаётся в seed() отдельно).
    packs = [
        {
            "org": "Комета",
            "name": "Луна Комета",
            "category": "cover",
            "rider": '{"format":"кавер-группа 4 человека","lineup":"вокал, гитара, бас, барабаны","tech":"сцена 4×3, 4 монитора"}',
            "tariff": ("Сет 90 минут", 180000),
            "days": (10, 16),
        },
        {
            "org": "Север Шоу",
            "name": "Эхо Севера",
            "category": "host",
            "rider": '{"format":"ведущий + диджей","lineup":"2 человека","tech":"радиомикрофон"}',
            "tariff": ("Вечер 4 часа", 120000),
            "days": (8, 21),
        },
        {
            "org": "Пульс Аудио",
            "name": "Маяк Пульс",
            "category": "dj",
            "rider": '{"format":"DJ-сет 3 часа","lineup":"1 человек","tech":"CDJ / контроллер"}',
            "tariff": ("Сет 3 часа", 95000),
            "days": (7, 19),
        },
        {
            "org": "Кадр Studio",
            "name": "Искра Кадр",
            "category": "photo",
            "rider": '{"format":"фоторепортаж","lineup":"1 фотограф","tech":"2 источника света"}',
            "tariff": ("Съёмка 4 часа", 70000),
            "days": (9, 22),
        },
        {
            "org": "Грань Beauty",
            "name": "Нить Грани",
            "category": "makeup",
            "rider": '{"format":"макияж + укладка","lineup":"1 визажист","tech":"зеркало, розетка"}',
            "tariff": ("Образ невесты", 45000),
            "days": (11, 24),
        },
        {
            "org": "Форма Декор",
            "name": "Объём Формы",
            "category": "decor",
            "rider": '{"format":"флористика и декор зала","lineup":"2 человека","tech":"доступ за 4 часа до старта"}',
            "tariff": ("Пакет зал", 160000),
            "days": (6, 18),
        },
        {
            "org": "Волна Sound",
            "name": "DJ Волна",
            "category": "dj",
            "rider": '{"format":"DJ + MC","lineup":"2 человека","tech":"пульт, 2 монитора"}',
            "tariff": ("Сет 4 часа", 110000),
            "days": (12, 25),
        },
        {
            "org": "Речь Event",
            "name": "Тон Речи",
            "category": "host",
            "rider": '{"format":"ведущий корпоратива","lineup":"1 человек","tech":"радиомикрофон"}',
            "tariff": ("Вечер 5 часов", 130000),
            "days": (5, 20),
        },
        {
            "org": "Ритм Band",
            "name": "Синапс Ритма",
            "category": "cover",
            "rider": '{"format":"кавер-трио","lineup":"вокал, гитара, перкуссия","tech":"сцена 3×2"}',
            "tariff": ("Сет 60 минут", 140000),
            "days": (13, 27),
        },
        {
            "org": "Свет Lens",
            "name": "Фокус Света",
            "category": "photo",
            "rider": '{"format":"портрет + репортаж","lineup":"фотограф + ассистент","tech":"кольцевой свет"}',
            "tariff": ("День съёмки", 90000),
            "days": (4, 17),
        },
        {
            "org": "Шёлк Face",
            "name": "Шёлк Лица",
            "category": "makeup",
            "rider": '{"format":"макияж гостей","lineup":"1 визажист","tech":"стол у окна"}',
            "tariff": ("Выезд 3 часа", 38000),
            "days": (14, 26),
        },
        {
            "org": "Линия Space",
            "name": "Контур Линии",
            "category": "decor",
            "rider": '{"format":"световой декор","lineup":"2 человека","tech":"220В, 3 точки"}',
            "tariff": ("Инсталляция", 125000),
            "days": (3, 15),
        },
        {
            "org": "Орбита Mix",
            "name": "Орбита Микс",
            "category": "dj",
            "rider": '{"format":"house / disco сет","lineup":"1 человек","tech":"Pioneer CDJ"}',
            "tariff": ("Сет 2 часа", 85000),
            "days": (8, 23),
        },
        {
            "org": "Сцена Слово",
            "name": "Янтарь Сцены",
            "category": "host",
            "rider": '{"format":"свадьба, церемония","lineup":"1 ведущий","tech":"петличка"}',
            "tariff": ("Полный день", 150000),
            "days": (9, 28),
        },
        {
            "org": "Аккорд Live",
            "name": "Аккорд Живой",
            "category": "cover",
            "rider": '{"format":"кавер-квартет","lineup":"4 музыканта","tech":"мониторы ×4"}',
            "tariff": ("Сет 2×45 мин", 200000),
            "days": (11, 29),
        },
        {
            "org": "Плёнка Pro",
            "name": "Плёнка Момент",
            "category": "photo",
            "rider": '{"format":"репортаж вечера","lineup":"1 фотограф","tech":"без вспышек по запросу"}',
            "tariff": ("Вечер 6 часов", 80000),
            "days": (6, 21),
        },
        {
            "org": "Тон Skin",
            "name": "Бархат Тона",
            "category": "makeup",
            "rider": '{"format":"макияж + ретушь на месте","lineup":"1 визажист","tech":"розетка, зеркало"}',
            "tariff": ("Пробный + день", 55000),
            "days": (7, 18),
        },
        {
            "org": "Плотность Art",
            "name": "Плотность Цвета",
            "category": "decor",
            "rider": '{"format":"президиум + фотозона","lineup":"3 человека","tech":"заезд за 5 часов"}',
            "tariff": ("Пакет свадьба", 190000),
            "days": (10, 24),
        },
        {
            "org": "Бас Клуб",
            "name": "Бас Ночи",
            "category": "dj",
            "rider": '{"format":"клубный сет","lineup":"1 человек","tech":"линия в клубный пульт"}',
            "tariff": ("Сет 3 часа", 100000),
            "days": (5, 16),
        },
        {
            "org": "Микрофон Plus",
            "name": "Микрофон Плюс",
            "category": "host",
            "rider": '{"format":"ведущий + игры","lineup":"1 человек","tech":"2 радиомикрофона"}',
            "tariff": ("Корпоратив 4 часа", 115000),
            "days": (12, 22),
        },
        {
            "org": "Струна Band",
            "name": "Струна Вечера",
            "category": "cover",
            "rider": '{"format":"акустический дуэт","lineup":"вокал, гитара","tech":"2 монитора"}',
            "tariff": ("Сет 75 минут", 95000),
            "days": (4, 19),
        },
        {
            "org": "Диафрагма Lab",
            "name": "Диафрагма Лаб",
            "category": "photo",
            "rider": '{"format":"love-story + день","lineup":"фотограф","tech":"рефлектор"}',
            "tariff": ("Пакет день", 110000),
            "days": (13, 25),
        },
        {
            "org": "Кисть Soft",
            "name": "Кисть Мягкая",
            "category": "makeup",
            "rider": '{"format":"вечерний макияж","lineup":"1 визажист","tech":"стол + свет"}',
            "tariff": ("Выезд 2 часа", 32000),
            "days": (8, 27),
        },
        {
            "org": "Ткань Room",
            "name": "Ткань Зала",
            "category": "decor",
            "rider": '{"format":"драпировка и свет","lineup":"2 человека","tech":"стремянка, удлинители"}',
            "tariff": ("Пакет зал M", 145000),
            "days": (14, 28),
        },
        {
            "org": "Частота DJ",
            "name": "Частота Рассвета",
            "category": "dj",
            "rider": '{"format":"sunset / lounge","lineup":"1 человек","tech":"контроллер + ноут"}',
            "tariff": ("Сет 2 часа", 75000),
            "days": (3, 20),
        },
        {
            "org": "Реплика Show",
            "name": "Реплика Шоу",
            "category": "host",
            "rider": '{"format":"интерактив + тайминг","lineup":"ведущий","tech":"петличка + гарнитура"}',
            "tariff": ("Вечер под ключ", 140000),
            "days": (9, 23),
        },
        {
            "org": "Гармония Cover",
            "name": "Гармония Кавер",
            "category": "cover",
            "rider": '{"format":"кавер-группа 5 человек","lineup":"полный бэнд","tech":"сцена 5×4"}',
            "tariff": ("Сет 90 минут", 220000),
            "days": (11, 26),
        },
        {
            "org": "Кадр Севера",
            "name": "Северный Кадр",
            "category": "photo",
            "rider": '{"format":"репортаж + портреты","lineup":"1 фотограф","tech":"2 вспышки"}',
            "tariff": ("Съёмка 5 часов", 85000),
            "days": (7, 17),
        },
        {
            "org": "Пудра Studio",
            "name": "Пудра Утра",
            "category": "makeup",
            "rider": '{"format":"сборы невесты","lineup":"визажист + стилист","tech":"окно или лампа 5600K"}',
            "tariff": ("Сборы 4 часа", 60000),
            "days": (6, 29),
        },
        {
            "org": "Флора Night",
            "name": "Флора Ночи",
            "category": "decor",
            "rider": '{"format":"живые композиции","lineup":"флорист + помощник","tech":"вода, холодильник по запросу"}',
            "tariff": ("Букеты + зал", 175000),
            "days": (5, 15),
        },
    ]
    for pack in packs:
        if db.query(Artist).filter(Artist.name == pack["name"]).one_or_none():
            continue
        org = Organization(name=pack["org"], kind="artist", city="Москва")
        db.add(org)
        db.flush()
        artist = Artist(
            organization_id=org.id,
            name=pack["name"],
            city="Москва",
            category=pack["category"],
            verified=True,
            verified_status="approved",
            rider_json=pack["rider"],
        )
        db.add(artist)
        db.flush()
        db.add(ArtistTariff(artist_id=artist.id, title=pack["tariff"][0], honorarium_rub=pack["tariff"][1], hours=2))
        for day in pack["days"]:
            db.add(_slot("artist", artist.id, day, 18))
        added += 1
    if not db.query(Venue).filter(Venue.name == "Клуб Сигнал").one_or_none():
        venue_user = db.query(User).filter(User.email == "venue@booker.test").one_or_none()
        if not venue_user:
            venue_user = User(
                email="venue@booker.test",
                full_name="Мария Площадка",
                phone="+79003333333",
                password_hash=hash_password(DEMO_PASSWORD),
            )
            db.add(venue_user)
            db.flush()
        vorg = Organization(name="Сигнал", kind="venue", city="Москва")
        db.add(vorg)
        db.flush()
        db.add(
            TeamMember(
                user_id=venue_user.id,
                organization_id=vorg.id,
                role="owner",
                can_confirm_offer=True,
            )
        )
        venue = Venue(
            organization_id=vorg.id,
            name="Клуб Сигнал",
            city="Москва",
            capacity=250,
            verified=True,
            verified_status="approved",
        )
        db.add(venue)
        db.flush()
        hall = VenueHall(venue_id=venue.id, name="Основной зал", capacity=250)
        db.add(hall)
        db.flush()
        db.add(VenueTariff(venue_id=venue.id, title="Аренда вечер", honorarium_rub=220000))
        db.add(_slot("hall", hall.id, 12, 19))
        added += 1
    nova = db.query(Artist).filter(Artist.name == "DJ Nova").one_or_none()
    if nova and (not nova.rider_json or nova.rider_json == "{}"):
        nova.rider_json = '{"format":"DJ-сет 2 часа","formats":["club","wedding"],"travel_ok":true,"lineup":"1 человек","tech":"пульт, 2 колонки"}'
    if nova:
        existing = db.query(Service).filter(Service.organization_id == nova.organization_id).count()
        if existing == 0:
            db.add_all(
                [
                    Service(
                        organization_id=nova.organization_id,
                        category_code="dj",
                        title="DJ-сет Nova",
                        description="Витрина, не quote.",
                        city="Москва",
                        published=True,
                        honorarium_rub=80000,
                    ),
                    Service(
                        organization_id=nova.organization_id,
                        category_code="host",
                        title="Ведущий в паре",
                        description="Витрина, не quote.",
                        city="Москва",
                        published=True,
                        honorarium_rub=60000,
                    ),
                ]
            )
            added += 2
    return added


def main() -> None:
    if os.environ.get("BOOKER_ALLOW_DEMO_SEED") != "1":
        print("demo seed отключён: задайте BOOKER_ALLOW_DEMO_SEED=1 (только локальный контур)")
        return
    init_schema(engine)
    db = SessionLocal()
    try:
        print(seed(db))
        from booker_api.seed_venues_moscow import import_moscow_venues

        print(import_moscow_venues(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
