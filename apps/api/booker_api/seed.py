"""Демо-данные для локального контура Букер."""

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
        rider_json='{"format":"DJ-сет 2 часа","lineup":"1 человек","tech":"пульт, 2 колонки"}',
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
        nova.rider_json = '{"format":"DJ-сет 2 часа","lineup":"1 человек","tech":"пульт, 2 колонки"}'
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
    init_schema(engine)
    db = SessionLocal()
    try:
        print(seed(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
