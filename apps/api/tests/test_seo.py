"""SEO is public inventory, not a calendar search or a sponsored impression."""
from datetime import datetime, timedelta, timezone

import pytest

from booker_api.models import (
    Artist,
    ArtistTariff,
    AuditLog,
    AvailabilitySlot,
    PromotionTouch,
    Venue,
    VenueHall,
    VenuePhoto,
    VenueTariff,
)
from booker_api.venue_catalog import is_publicly_listed, publicly_listed_venue_query
from tests.test_commerce import org_user


def add_publication_candidate(
    db,
    organization_id: str,
    name: str,
    *,
    missing: str | None = None,
    research: bool = False,
):
    venue = Venue(
        organization_id=organization_id,
        name=name,
        city='Москва',
        moderation_status='published',
        listing_origin='open_data' if research else 'owner',
        source_type='automated_import' if research else 'owner_submission',
        availability_mode='research' if research else 'owner',
        partnership_status=(
            'unverified_listing' if research else 'claimed' if missing == 'partnership' else 'verified'
        ),
        is_claimed=not research,
        verified=not research and missing != 'partnership',
        phone='private-phone',
        email='private-email',
        description='Описание',
    )
    db.add(venue)
    db.flush()
    hall = VenueHall(venue_id=venue.id, name='Основной зал', capacity=100)
    db.add(hall)
    db.flush()
    horizon = datetime.now(timezone.utc) + timedelta(days=35)
    if missing != 'calendar':
        db.add(
            AvailabilitySlot(
                resource_type='hall',
                resource_id=hall.id,
                starts_at=horizon - timedelta(hours=4),
                ends_at=horizon,
                status='open',
            )
        )
    if missing != 'price':
        db.add(VenueTariff(venue_id=venue.id, title='Публичный тариф', honorarium_rub=50000))
    if missing != 'media':
        db.add(
            VenuePhoto(
                venue_id=venue.id,
                photo_url=f'https://venue.example/{venue.id}.jpg',
                photo_source_url='https://venue.example/gallery',
                photo_rights_status='official_permission',
            )
        )
    return venue


def populate(client, SessionLocal, *, count=3):
    _, _, org = org_user(client)
    with SessionLocal() as db:
        artists = [Artist(organization_id=org, name=f'Исполнитель {i:04}', city='Москва', category='dj') for i in range(count)]
        db.add_all(artists)
        db.flush()
        ids = [row.id for row in artists]
        db.add(Artist(organization_id=org, name='Другой город', city='Казань', category='host'))
        for index in range(3):
            add_publication_candidate(db, org, f'Зал {index}')
        db.add(Venue(organization_id=org, name='Скрытый зал', city='Москва', moderation_status='draft'))
        if artists:
            db.add(ArtistTariff(artist_id=ids[0], title='Программа', honorarium_rub=0))
            db.add(ArtistTariff(artist_id=ids[1], title='Программа', honorarium_rub=12000))
        db.commit()
    return ids


def test_venue_inventory_uses_complete_publication_gate(client, SessionLocal):
    _, _, org = org_user(client, kind='venue', suffix='seo-publication-gate')
    with SessionLocal() as db:
        candidates = {
            'visible': add_publication_candidate(db, org, 'Доступная площадка'),
            'media': add_publication_candidate(db, org, 'Без медиа', missing='media'),
            'calendar': add_publication_candidate(db, org, 'Без календаря', missing='calendar'),
            'price': add_publication_candidate(db, org, 'Без цены', missing='price'),
            'partnership': add_publication_candidate(
                db, org, 'Без партнёрства', missing='partnership'
            ),
            'research': add_publication_candidate(db, org, 'Research synthetic', research=True),
        }
        db.commit()
        visible_id = candidates['visible'].id
        expected = {
            row.id
            for row in candidates.values()
            if is_publicly_listed(db, row)
        }
        assert expected == {visible_id}
        assert {row.id for row in publicly_listed_venue_query(db).all()} == expected

    index = client.get('/seo/index').json()
    assert index['counts']['venues'] == 1
    assert '/catalog/moskva/venues' not in {item['path'] for item in index['collections']}
    assert client.get('/seo/profiles?kind=venues').json()['items'] == [
        {'path': f'/venues/{visible_id}'}
    ]
    assert client.get('/seo/collections/moskva/venues').status_code == 404


def test_venue_gate_is_applied_before_profile_pagination(
    client, SessionLocal, monkeypatch
):
    from booker_api.routers import seo

    monkeypatch.setattr(seo, 'PAGE_SIZE', 1)
    _, _, org = org_user(client, kind='venue', suffix='seo-pagination-gate')
    with SessionLocal() as db:
        first = add_publication_candidate(db, org, 'Доступная A')
        add_publication_candidate(db, org, 'Скрытая между страницами', missing='media')
        second = add_publication_candidate(db, org, 'Доступная B')
        db.commit()
        expected = [f'/venues/{venue_id}' for venue_id in sorted((first.id, second.id))]

    assert client.get('/seo/index').json()['counts']['venues'] == 2
    assert [
        client.get(f'/seo/profiles?kind=venues&page={page}').json()['items'][0]['path']
        for page in range(2)
    ] == expected
    assert client.get('/seo/profiles?kind=venues&page=2').json()['items'] == []


@pytest.mark.parametrize('blocker', ['media', 'calendar', 'price', 'partnership'])
def test_revoked_venue_disappears_from_seo_totals_profiles_and_collection(
    client, SessionLocal, blocker
):
    populate(client, SessionLocal)
    before = client.get('/seo/index').json()
    assert before['counts']['venues'] == 3
    assert client.get('/seo/collections/moskva/venues').status_code == 200

    with SessionLocal() as db:
        venue = db.query(Venue).filter(Venue.name == 'Зал 0').one()
        revoked_id = venue.id
        if blocker == 'media':
            db.query(VenuePhoto).filter(VenuePhoto.venue_id == venue.id).delete()
        elif blocker == 'calendar':
            hall_ids = db.query(VenueHall.id).filter(VenueHall.venue_id == venue.id)
            db.query(AvailabilitySlot).filter(
                AvailabilitySlot.resource_id.in_(hall_ids)
            ).delete(synchronize_session=False)
        elif blocker == 'price':
            db.query(VenueTariff).filter(VenueTariff.venue_id == venue.id).delete()
        else:
            venue.partnership_status = 'claimed'
        db.commit()

    after = client.get('/seo/index').json()
    assert after['counts']['venues'] == 2
    assert {'path': f'/venues/{revoked_id}'} not in client.get(
        '/seo/profiles?kind=venues'
    ).json()['items']
    assert client.get('/seo/collections/moskva/venues').status_code == 404


def test_index_includes_public_profiles_without_slots_across_cities(client, SessionLocal):
    ids = populate(client, SessionLocal)
    with SessionLocal() as db:
        before = db.query(AuditLog).count(), db.query(PromotionTouch).count()
    data = client.get('/seo/index').json()
    assert data['counts'] == {'artists': 4, 'venues': 3}
    assert {item['path'] for item in data['collections']} == {'/catalog/moskva/dj', '/catalog/moskva/venues'}
    profiles = client.get('/seo/profiles?kind=artists').json()['items']
    assert len(profiles) == 4 and {'path': f'/artists/{ids[0]}'} in profiles
    assert len(client.get('/seo/profiles?kind=venues').json()['items']) == 3
    with SessionLocal() as db:
        assert (db.query(AuditLog).count(), db.query(PromotionTouch).count()) == before


def test_collections_only_public_facts_and_server_orientations(client, SessionLocal):
    populate(client, SessionLocal)
    data = client.get('/seo/collections/moskva/dj').json()
    assert data['items'][0]['honorarium_from_rub'] == 0
    assert data['items'][1]['honorarium_from_rub'] == 12000
    assert data['items'][2]['honorarium_from_rub'] is None
    assert not data['has_more']
    venues = client.get('/seo/collections/moskva/venues')
    assert venues.status_code == 200
    assert 'private-phone' not in venues.text and 'private-email' not in venues.text
    assert all('organization_id' not in row and 'verified' not in row and 'sponsored' not in row for row in data['items'])


def test_sparse_or_unknown_collection_is_not_an_indexable_page(client, SessionLocal):
    populate(client, SessionLocal, count=2)
    for path in ('/seo/collections/moskva/dj', '/seo/collections/unknown/dj', '/seo/collections/moskva/unknown'):
        assert client.get(path).status_code == 404
    assert '/catalog/moskva/dj' not in str(client.get('/seo/index').json())


def test_collection_pagination_and_private_venue_exclusion(client, SessionLocal):
    populate(client, SessionLocal, count=25)
    first = client.get('/seo/collections/moskva/dj').json()
    last = client.get('/seo/collections/moskva/dj?page=1').json()
    assert len(first['items']) == 24 and first['has_more']
    assert len(last['items']) == 1 and not last['has_more']
    assert not {row['id'] for row in first['items']} & {row['id'] for row in last['items']}
    assert client.get('/seo/collections/moskva/dj?page=2').status_code == 404


@pytest.mark.parametrize('query', ['kind=private', 'kind=artists&page=-1', 'kind=venues&page=50001'])
def test_inventory_parameters_are_bounded(client, query):
    assert client.get('/seo/profiles?' + query).status_code == 422


def test_inventory_chunks_cover_more_than_one_thousand_profiles(client, SessionLocal):
    populate(client, SessionLocal, count=1001)
    first = client.get('/seo/profiles?kind=artists&page=0').json()['items']
    second = client.get('/seo/profiles?kind=artists&page=1').json()['items']
    assert len(first) == 1000 and len(second) == 2
    assert len({row['path'] for row in first + second}) == 1002
