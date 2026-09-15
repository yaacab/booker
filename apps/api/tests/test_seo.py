"""SEO is public inventory, not a calendar search or a sponsored impression."""
import pytest

from booker_api.models import Artist, ArtistTariff, AuditLog, PromotionTouch, Venue
from tests.test_commerce import org_user


def populate(client, SessionLocal, *, count=3):
    _, _, org = org_user(client)
    with SessionLocal() as db:
        artists = [Artist(organization_id=org, name=f'Исполнитель {i:04}', city='Москва', category='dj') for i in range(count)]
        db.add_all(artists)
        db.flush()
        ids = [row.id for row in artists]
        db.add(Artist(organization_id=org, name='Другой город', city='Казань', category='host'))
        db.add_all([Venue(organization_id=org, name=f'Зал {i}', city='Москва', moderation_status='published',
            phone='private-phone', email='private-email', description='Описание') for i in range(3)])
        db.add(Venue(organization_id=org, name='Скрытый зал', city='Москва', moderation_status='draft'))
        if artists:
            db.add(ArtistTariff(artist_id=ids[0], title='Программа', honorarium_rub=0))
            db.add(ArtistTariff(artist_id=ids[1], title='Программа', honorarium_rub=12000))
        db.commit()
    return ids


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
