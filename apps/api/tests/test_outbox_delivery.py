from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from booker_api.config import settings
from booker_api.db import Base
from booker_api.models import EmailOutbox
from booker_api.notifications import Channel, Notification, notify
from booker_api.notifications.outbox import enqueue_email, retry_pending_outbox
from booker_api.security import now


@pytest.fixture()
def sessions(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'delivery.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, 'email_provider', 'smtp')
    monkeypatch.setattr(settings, 'email_smtp_host', 'smtp.test.invalid')
    yield sessionmaker(bind=engine)
    engine.dispose()


def enqueue(db, key='one'):
    return enqueue_email(db, idempotency_key=key, recipient_email='test@example.invalid', subject='Test', body='PRIVATE body')


def test_no_network_before_commit_and_rollback(sessions, monkeypatch):
    calls = []
    monkeypatch.setattr('booker_api.notifications.outbox._deliver', lambda row: (calls.append(row.id) or True, 'sent'))
    with sessions() as producer, sessions() as reader:
        note = Notification(channel=Channel.EMAIL, template='test', recipient_email='test@example.invalid', subject='Test', body='PRIVATE body')
        result = notify(producer, actor_user_id=None, notifications=[note])
        assert result[0]['status'] == 'queued' and result[0]['sent'] is False and calls == []
        assert retry_pending_outbox(reader)['processed'] == 0
        producer.rollback()
        assert reader.query(EmailOutbox).count() == 0
        notify(producer, actor_user_id=None, notifications=[note]); producer.commit()
        assert retry_pending_outbox(reader)['sent'] == 1
        assert len(calls) == 1
        notify(producer, actor_user_id=None, notifications=[note]); producer.commit()
        assert retry_pending_outbox(reader)['processed'] == 0
        assert len(calls) == 1


def test_claim_prevents_overlapping_workers_and_disabled(sessions, monkeypatch):
    with sessions() as producer:
        enqueue(producer); producer.commit()
    calls = []
    def deliver(row):
        calls.append(row.id)
        with sessions() as other:
            saved = other.get(EmailOutbox, row.id)
            assert saved.status == 'sending' and saved.claim_token
            assert retry_pending_outbox(other)['processed'] == 0
        return True, 'sent'
    monkeypatch.setattr('booker_api.notifications.outbox._deliver', deliver)
    with sessions() as worker:
        monkeypatch.setattr(settings, 'email_provider', 'disabled')
        assert retry_pending_outbox(worker)['state'] == 'disabled' and not calls
        monkeypatch.setattr(settings, 'email_provider', 'smtp')
        assert retry_pending_outbox(worker)['sent'] == 1 and len(calls) == 1


def test_failure_backoff_and_ambiguous_crash_never_auto_resend(sessions, monkeypatch):
    with sessions() as db:
        row = enqueue(db); db.commit(); row_id = row.id
    monkeypatch.setattr('booker_api.notifications.outbox._deliver', lambda row: (False, 'retryable:ConnectionRefusedError'))
    with sessions() as worker:
        assert retry_pending_outbox(worker)['failed'] == 1
        assert retry_pending_outbox(worker)['processed'] == 0
    with sessions() as db:
        row = db.get(EmailOutbox, row_id); row.next_attempt_at = now()-timedelta(seconds=1); db.commit()
    monkeypatch.setattr('booker_api.notifications.outbox._deliver', lambda row: (False, 'uncertain:SMTPServerDisconnected'))
    with sessions() as worker:
        assert retry_pending_outbox(worker)['uncertain'] == 1
        assert retry_pending_outbox(worker)['processed'] == 0
    with sessions() as db:
        row = enqueue(db, 'crashed'); row.status = 'sending'; row.claim_token = 'old-worker'; row.claim_expires_at = now()-timedelta(seconds=1); db.commit()
    monkeypatch.setattr('booker_api.notifications.outbox._deliver', lambda row: pytest.fail('Ambiguous delivery must not be retried'))
    with sessions() as worker:
        result = retry_pending_outbox(worker)
        assert result['uncertain'] == 1 and result['processed'] == 0


def test_new_reset_link_is_new_delivery_and_duplicate_is_not(sessions):
    with sessions() as db:
        for body in ['link-token-a', 'link-token-a', 'link-token-b']:
            notify(db, actor_user_id=None, notifications=[Notification(channel=Channel.EMAIL, template='auth.password_reset', recipient_email='test@example.invalid', entity_type='user', entity_id='same-user', body=body)])
        db.commit()
        assert db.query(EmailOutbox).count() == 2


def test_max_attempts_and_missing_configuration(sessions, monkeypatch):
    with sessions() as db:
        row = enqueue(db); row.status = 'failed'; row.attempts = 5; db.commit()
    monkeypatch.setattr('booker_api.notifications.outbox._deliver', lambda row: pytest.fail('Do not exceed retry limit'))
    with sessions() as worker:
        assert retry_pending_outbox(worker)['processed'] == 0
        monkeypatch.setattr(settings, 'email_smtp_host', '')
        assert retry_pending_outbox(worker)['state'] == 'unconfigured'


def test_outbox_migration_preserves_existing_rows(tmp_path):
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    url = f"sqlite:///{tmp_path / 'outbox-migration.db'}"; config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'a4b5c6d7e8f9'); engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO email_outbox (id,idempotency_key,recipient_email,subject,body,template,entity_type,entity_id,status,attempts,last_error,created_at) VALUES ('old','legacy','a@test.invalid','Saved','Saved body','test','notification','one','pending',0,'',CURRENT_TIMESTAMP)")
    command.upgrade(config, 'head')
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT status,body,claim_token,next_attempt_at FROM email_outbox WHERE id='old'").one()
        assert row == ('pending', 'Saved body', None, None)
    command.downgrade(config, 'a4b5c6d7e8f9'); command.upgrade(config, 'head'); engine.dispose()


def test_legacy_smtp_key_does_not_redeliver_identical_sent_message(sessions):
    with sessions() as db:
        row = enqueue_email(db, idempotency_key='test:user:same-user:a@test.invalid', recipient_email='a@test.invalid', subject='Test', body='Saved body', template='test', entity_type='user', entity_id='same-user')
        row.status = 'sent'; db.commit()
        result = notify(db, actor_user_id=None, notifications=[Notification(channel=Channel.EMAIL, template='test', recipient_email='a@test.invalid', subject='Test', body='Saved body', entity_type='user', entity_id='same-user')])
        db.commit()
        assert result[0]['status'] == 'already_sent' and db.query(EmailOutbox).count() == 1
