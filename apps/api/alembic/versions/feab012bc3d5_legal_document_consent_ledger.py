"""Version legal documents and retain immutable consent evidence.

Revision ID: feab012bc3d5
Revises: fd9a012bc3d4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "feab012bc3d5"
down_revision: str | None = "fd9a012bc3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _install_guards() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("""
            CREATE TRIGGER IF NOT EXISTS legal_documents_insert_guard
            BEFORE INSERT ON legal_document_versions
            WHEN length(trim(NEW.key)) = 0 OR length(trim(NEW.version)) = 0
              OR length(NEW.content_hash) != 64 OR length(trim(NEW.source_path)) = 0
              OR (NEW.status = 'draft' AND
                  (NEW.published_at IS NOT NULL OR NEW.retired_at IS NOT NULL))
              OR (NEW.status = 'published' AND
                  (NEW.published_at IS NULL OR NEW.retired_at IS NOT NULL))
              OR (NEW.status = 'retired' AND
                  (NEW.published_at IS NULL OR NEW.retired_at IS NULL))
            BEGIN SELECT RAISE(ABORT, 'invalid legal document version'); END
        """)
        op.execute("""
            CREATE TRIGGER IF NOT EXISTS legal_documents_no_delete
            BEFORE DELETE ON legal_document_versions
            BEGIN SELECT RAISE(ABORT, 'legal document versions are immutable'); END
        """)
        op.execute("""
            CREATE TRIGGER IF NOT EXISTS legal_documents_update_guard
            BEFORE UPDATE ON legal_document_versions
            WHEN NEW.id IS NOT OLD.id
              OR NEW.key IS NOT OLD.key
              OR NEW.version IS NOT OLD.version
              OR NEW.created_at IS NOT OLD.created_at
              OR NEW.created_by_user_id IS NOT OLD.created_by_user_id
              OR (OLD.status = 'draft' AND (
                    NEW.status NOT IN ('draft', 'published')
                    OR (NEW.status = 'draft' AND
                        (NEW.published_at IS NOT NULL OR NEW.retired_at IS NOT NULL))
                    OR (NEW.status = 'published' AND
                        (NEW.published_at IS NULL OR NEW.retired_at IS NOT NULL
                         OR NEW.content_hash IS NULL OR length(NEW.content_hash) != 64
                         OR length(trim(NEW.source_path)) = 0))))
              OR (OLD.status = 'published' AND (
                    NEW.status NOT IN ('published', 'retired')
                    OR NEW.content_hash IS NOT OLD.content_hash
                    OR NEW.source_path IS NOT OLD.source_path
                    OR NEW.published_at IS NOT OLD.published_at
                    OR (NEW.status = 'published' AND NEW.retired_at IS NOT NULL)
                    OR (NEW.status = 'retired' AND NEW.retired_at IS NULL)))
              OR (OLD.status = 'retired' AND (
                    NEW.status IS NOT OLD.status
                    OR NEW.content_hash IS NOT OLD.content_hash
                    OR NEW.source_path IS NOT OLD.source_path
                    OR NEW.published_at IS NOT OLD.published_at
                    OR NEW.retired_at IS NOT OLD.retired_at))
            BEGIN SELECT RAISE(ABORT, 'legal document version is immutable'); END
        """)
        op.execute("""
            CREATE TRIGGER IF NOT EXISTS consent_events_insert_guard
            BEFORE INSERT ON consent_events
            WHEN NEW.action NOT IN ('accepted', 'withdrawn')
              OR NEW.kind NOT IN ('offer', 'privacy', 'processing', 'marketing_email')
              OR length(trim(NEW.document_version)) = 0
              OR length(NEW.document_hash) != 64
            BEGIN SELECT RAISE(ABORT, 'invalid consent event'); END
        """)
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS consent_events_no_{action.lower()} "
                f"BEFORE {action} ON consent_events "
                "BEGIN SELECT RAISE(ABORT, 'consent events are append-only'); END"
            )
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION booker_legal_document_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'legal document versions are immutable';
                END IF;
                IF NEW.id IS DISTINCT FROM OLD.id
                   OR NEW.key IS DISTINCT FROM OLD.key
                   OR NEW.version IS DISTINCT FROM OLD.version
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at
                   OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                   OR (OLD.status = 'draft' AND (
                       NEW.status NOT IN ('draft', 'published')
                       OR (NEW.status = 'draft' AND
                           (NEW.published_at IS NOT NULL OR NEW.retired_at IS NOT NULL))
                       OR (NEW.status = 'published' AND
                           (NEW.published_at IS NULL OR NEW.retired_at IS NOT NULL
                            OR NEW.content_hash IS NULL OR length(NEW.content_hash) != 64
                            OR length(btrim(NEW.source_path)) = 0))))
                   OR (OLD.status = 'published' AND (
                       NEW.status NOT IN ('published', 'retired')
                       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
                       OR NEW.source_path IS DISTINCT FROM OLD.source_path
                       OR NEW.published_at IS DISTINCT FROM OLD.published_at
                       OR (NEW.status = 'published' AND NEW.retired_at IS NOT NULL)
                       OR (NEW.status = 'retired' AND NEW.retired_at IS NULL)))
                   OR (OLD.status = 'retired' AND (
                       NEW.status IS DISTINCT FROM OLD.status
                       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
                       OR NEW.source_path IS DISTINCT FROM OLD.source_path
                       OR NEW.published_at IS DISTINCT FROM OLD.published_at
                       OR NEW.retired_at IS DISTINCT FROM OLD.retired_at)) THEN
                    RAISE EXCEPTION 'legal document version is immutable';
                END IF;
                RETURN NEW;
            END; $$
        """)
        op.execute("""
            CREATE TRIGGER legal_documents_mutation_guard
            BEFORE UPDATE OR DELETE ON legal_document_versions
            FOR EACH ROW EXECUTE FUNCTION booker_legal_document_guard()
        """)
        op.execute("""
            CREATE FUNCTION booker_consent_event_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'consent events are append-only'; END; $$
        """)
        op.execute("""
            CREATE TRIGGER consent_events_mutation_guard
            BEFORE UPDATE OR DELETE ON consent_events
            FOR EACH ROW EXECUTE FUNCTION booker_consent_event_guard()
        """)


def upgrade() -> None:
    bind = op.get_bind()
    user_columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "marketing_consent_active" not in user_columns:
        op.add_column(
            "users", sa.Column("marketing_consent_active", sa.Boolean(),
                               nullable=False, server_default=sa.false()),
        )
    existing = set(sa.inspect(bind).get_table_names())
    tables = {"legal_document_versions", "consent_events"}
    if tables & existing:
        if tables - existing or bind.dialect.name != "sqlite":
            raise RuntimeError("Existing legal ledger requires a reviewed schema adoption")
        inspector = sa.inspect(bind)
        expected_columns = {
            "legal_document_versions": {
                "id", "key", "version", "content_hash", "status", "source_path",
                "created_at", "created_by_user_id", "published_at", "retired_at",
            },
            "consent_events": {
                "id", "user_id", "kind", "document_version_id", "document_version",
                "document_hash", "action", "channel", "created_at", "metadata_json",
            },
        }
        for table, names in expected_columns.items():
            found = {column["name"] for column in inspector.get_columns(table)}
            if found != names:
                raise RuntimeError(f"Incompatible existing {table} columns")
        unique_sets = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("legal_document_versions")
        }
        if ("key", "version") not in unique_sets:
            raise RuntimeError("Existing legal document versions lack key/version uniqueness")
        indexes = {item["name"] for item in inspector.get_indexes("legal_document_versions")}
        if "uq_legal_document_published_key" not in indexes:
            op.create_index(
                "uq_legal_document_published_key", "legal_document_versions", ["key"],
                unique=True, sqlite_where=sa.text("status = 'published'"),
                postgresql_where=sa.text("status = 'published'"),
            )
        _install_guards()
        return

    op.create_table(
        "legal_document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(48), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_path", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", "version", name="uq_legal_document_key_version"),
        sa.CheckConstraint("length(trim(key)) > 0", name="ck_legal_document_key"),
        sa.CheckConstraint("length(trim(version)) > 0", name="ck_legal_document_version"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')", name="ck_legal_document_status"
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND published_at IS NULL AND retired_at IS NULL)"
            " OR (status = 'published' AND published_at IS NOT NULL AND retired_at IS NULL"
            " AND content_hash IS NOT NULL AND length(content_hash) = 64"
            " AND length(trim(source_path)) > 0)"
            " OR (status = 'retired' AND published_at IS NOT NULL AND retired_at IS NOT NULL"
            " AND content_hash IS NOT NULL AND length(content_hash) = 64"
            " AND length(trim(source_path)) > 0)",
            name="ck_legal_document_lifecycle",
        ),
    )
    op.create_index("ix_legal_document_versions_key", "legal_document_versions", ["key"])
    op.create_index(
        "uq_legal_document_published_key", "legal_document_versions", ["key"],
        unique=True, sqlite_where=sa.text("status = 'published'"),
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_table(
        "consent_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "document_version_id", sa.String(36),
            sa.ForeignKey("legal_document_versions.id"), nullable=True,
        ),
        sa.Column("document_version", sa.String(64), nullable=False),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.CheckConstraint("action IN ('accepted', 'withdrawn')", name="ck_consent_action"),
        sa.CheckConstraint(
            "kind IN ('offer', 'privacy', 'processing', 'marketing_email')",
            name="ck_consent_kind",
        ),
        sa.CheckConstraint("length(trim(document_version)) > 0", name="ck_consent_document_version"),
        sa.CheckConstraint("length(document_hash) = 64", name="ck_consent_document_hash"),
    )
    op.create_index("ix_consent_events_user_id", "consent_events", ["user_id"])
    op.create_index("ix_consent_events_kind", "consent_events", ["kind"])
    op.create_index(
        "ix_consent_events_document_version_id", "consent_events", ["document_version_id"]
    )
    _install_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM consent_events")).scalar_one():
        raise RuntimeError("Refusing to drop consent history")
    if bind.execute(sa.text("SELECT COUNT(*) FROM legal_document_versions")).scalar_one():
        raise RuntimeError("Refusing to drop legal document versions")
    if bind.dialect.name == "sqlite":
        for name in (
            "consent_events_no_update", "consent_events_no_delete",
            "consent_events_insert_guard", "legal_documents_insert_guard",
            "legal_documents_update_guard", "legal_documents_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS consent_events_mutation_guard ON consent_events")
        op.execute("DROP TRIGGER IF EXISTS legal_documents_mutation_guard ON legal_document_versions")
        op.execute("DROP FUNCTION IF EXISTS booker_consent_event_guard()")
        op.execute("DROP FUNCTION IF EXISTS booker_legal_document_guard()")
    op.drop_index("ix_consent_events_document_version_id", table_name="consent_events")
    op.drop_index("ix_consent_events_kind", table_name="consent_events")
    op.drop_index("ix_consent_events_user_id", table_name="consent_events")
    op.drop_table("consent_events")
    op.drop_index("uq_legal_document_published_key", table_name="legal_document_versions")
    op.drop_index("ix_legal_document_versions_key", table_name="legal_document_versions")
    op.drop_table("legal_document_versions")
    op.drop_column("users", "marketing_consent_active")
