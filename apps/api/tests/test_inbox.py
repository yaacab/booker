from booker_api.models import InboxNotification
from booker_api.notifications import Channel, Notification, notify
from tests.conftest import auth_header, register


def deliver(db, user_id, key='one', **kwargs):
    item = Notification(channel=Channel.IN_APP, recipient_user_id=user_id, template='test.notice', subject='Важное сообщение', body='Текст уведомления', entity_type='user', entity_id=user_id, dedupe_key=key, **kwargs)
    return notify(db, actor_user_id=None, notifications=[item])


def test_recipient_filter_before_limit_and_read_authorization(client, SessionLocal):
    user = register(client, 'inbox-owner@booker.test'); other = register(client, 'inbox-other@booker.test')
    with SessionLocal() as db:
        deliver(db, user['user_id']); db.commit()
        for n in range(105):
            deliver(db, other['user_id'], key=str(n))
        db.commit()
    h = auth_header(user['token'])
    result = client.get('/notifications?limit=1', headers=h).json()
    assert len(result['items']) == 1 and result['unread_count'] == 1 and result['total'] == 1
    item = result['items'][0]; assert item['href'] == '/profile' and item['read_at'] is None
    path = f"/notifications/{item['id']}/read"
    assert client.post(path, headers=auth_header(other['token'])).status_code == 403
    first = client.post(path, headers=h); assert first.status_code == 200, first.text
    assert client.post(path, headers=h).json()['read_at'] == first.json()['read_at']
    assert client.get('/notifications?unread_only=true', headers=h).json()['items'] == []
    assert client.get('/notifications', headers=h).json()['unread_count'] == 0


def test_atomic_deduplication_and_internal_links(client, SessionLocal):
    user = register(client, 'inbox-atomic@booker.test')
    with SessionLocal() as db:
        deliver(db, user['user_id']); db.rollback()
        assert db.query(InboxNotification).count() == 0
        deliver(db, user['user_id'], metadata={'href': '//evil.example'}); db.commit()
        deliver(db, user['user_id'], metadata={'href': '/safe'}); db.commit()
        assert db.query(InboxNotification).count() == 1
        assert db.query(InboxNotification).one().href == '/profile'
    from booker_api.notifications.inbox import internal_href
    for bad in ['javascript:alert(1)', '//evil.example', '/\\evil.example', '/x\nInjected']:
        assert internal_href(bad) is None


def test_password_reset_token_not_in_inbox(client, SessionLocal):
    user = register(client, 'inbox-reset@booker.test')
    response = client.post('/auth/recover', json={'email': 'inbox-reset@booker.test'})
    assert response.status_code == 200, response.text
    data = client.get('/notifications', headers=auth_header(user['token'])).json()
    assert len(data['items']) == 1 and 'Токен' not in data['items'][0]['body'] and 'reset=' not in data['items'][0]['body']


def test_legacy_inbox_migration(tmp_path):
    import json
    from pathlib import Path

    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from alembic import command

    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    url = f"sqlite:///{tmp_path / 'inbox.db'}"; config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'f3a4b5c6d7e8'); engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,totp_enabled,created_at) VALUES ('legacy-user','legacy@test.local','Legacy','x',0,0,CURRENT_TIMESTAMP)")
        for i in range(2):
            conn.execute(text("INSERT INTO audit_logs (id,action,entity_type,entity_id,payload,created_at) VALUES (:id,'notification.in_app','user','legacy-user',:payload,CURRENT_TIMESTAMP)"), {'id': f'legacy-{i}', 'payload': json.dumps({'recipient_user_id': 'legacy-user', 'template': 'auth.password_reset', 'subject': 'Сброс пароля', 'body': 'Токен сброса: SECRET'})})
    command.upgrade(config, 'head')
    with engine.connect() as conn:
        rows = conn.exec_driver_sql('SELECT recipient_user_id,body FROM inbox_notifications').all()
        assert len(rows) == 1 and rows[0][0] == 'legacy-user' and 'SECRET' not in rows[0][1]
    command.downgrade(config, 'f3a4b5c6d7e8'); command.upgrade(config, 'head'); engine.dispose()
