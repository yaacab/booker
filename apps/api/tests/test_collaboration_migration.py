from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_legacy_share_survives_collaboration_migration_and_roundtrip(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy-share.db'}"
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'e6f7a8b9c0d1')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,totp_enabled,created_at) VALUES ('user','legacy@booker.test','Owner','test',0,0,'2026-09-01')"))
        connection.execute(text("INSERT INTO organizations (id,name,kind,city,created_at) VALUES ('org','Org','customer','Москва','2026-09-01')"))
        connection.execute(text("INSERT INTO shared_shortlists (id,owner_user_id,organization_id,target_type,title,token,expires_at,created_at) VALUES ('share','user','org','artist','Legacy','legacy-link','2030-01-01','2026-09-01')"))
        connection.execute(text("INSERT INTO shared_shortlist_items (id,shortlist_id,target_id,name,city,summary,sort_order) VALUES ('item','share','artist','Snapshot','Москва','DJ',0)"))
    command.upgrade(config, 'f7a8b9c0d1e2')
    with engine.connect() as connection:
        row = connection.execute(text('SELECT token,collaborative,event_id FROM shared_shortlists')).one()
        assert row == ('legacy-link', 0, None)
        assert connection.execute(text('SELECT name FROM shared_shortlist_items')).scalar() == 'Snapshot'
    assert {'shortlist_guests', 'shortlist_feedback'} <= set(inspect(engine).get_table_names())
    assert any(f['referred_table'] == 'events' for f in inspect(engine).get_foreign_keys('shared_shortlists'))
    command.downgrade(config, 'e6f7a8b9c0d1')
    command.upgrade(config, 'f7a8b9c0d1e2')
    with engine.connect() as connection:
        assert connection.execute(text('SELECT token,collaborative FROM shared_shortlists')).one() == ('legacy-link', 0)
    engine.dispose()
