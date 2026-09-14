"""Recipient-scoped persistent inbox, preserving valid legacy in-app history."""
import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table("inbox_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dedupe_key", sa.String(64), nullable=False, unique=True),
        sa.Column("template", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("href", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_inbox_notifications_recipient_user_id", "inbox_notifications", ["recipient_user_id"])
    conn = op.get_bind()
    audit = sa.table('audit_logs', sa.column('id'), sa.column('action'), sa.column('payload'), sa.column('entity_type'), sa.column('entity_id'), sa.column('created_at', sa.DateTime(timezone=True)))
    users = sa.table('users', sa.column('id'))
    for row in conn.execute(sa.select(audit).where(audit.c.action == 'notification.in_app').order_by(audit.c.created_at, audit.c.id)).mappings():
        try:
            data = json.loads(row['payload'])
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        recipient = data.get('recipient_user_id')
        if not isinstance(recipient, str) or not conn.execute(sa.select(users.c.id).where(users.c.id == recipient)).first():
            continue
        template, subject, body = (str(data.get(k) or '') for k in ['template', 'subject', 'body'])
        if template == 'auth.password_reset':
            body = 'Запрошено восстановление доступа. Используйте ссылку из письма. Если это были не вы, проверьте безопасность аккаунта.'
        key = hashlib.sha256(json.dumps([recipient, template, row['entity_type'], row['entity_id'], subject, body], ensure_ascii=False).encode()).hexdigest()
        if conn.execute(sa.select(table.c.id).where(table.c.dedupe_key == key)).first():
            continue
        conn.execute(table.insert().values(id=row['id'], recipient_user_id=recipient, dedupe_key=key, template=template[:64], subject=subject[:255], body=body,
            entity_type=row['entity_type'], entity_id=row['entity_id'], href=None, created_at=row['created_at'], read_at=None))


def downgrade():
    op.drop_table("inbox_notifications")
