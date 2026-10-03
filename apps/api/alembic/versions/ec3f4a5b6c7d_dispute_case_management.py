"""Add dispute queue, evidence, SLA, and protected decisions.

Revision ID: ec3f4a5b6c7d
Revises: eb2e3f4a5b6c
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ec3f4a5b6c7d"
down_revision: str | None = "eb2e3f4a5b6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    columns = _columns("disputes")
    dialect = op.get_bind().dialect.name
    additions = (
        ("opened_by_user_id", sa.Column("opened_by_user_id", sa.String(36), sa.ForeignKey("users.id"))),
        ("assigned_to_user_id", sa.Column("assigned_to_user_id", sa.String(36), sa.ForeignKey("users.id"))),
        ("priority", sa.Column("priority", sa.String(16), server_default="high", nullable=False)),
        ("response_due_at", sa.Column("response_due_at", sa.DateTime(timezone=True))),
        ("state_version", sa.Column("state_version", sa.Integer(), server_default="0", nullable=False)),
        ("decision_kind", sa.Column("decision_kind", sa.String(64))),
        ("resolved_by_user_id", sa.Column("resolved_by_user_id", sa.String(36), sa.ForeignKey("users.id"))),
        ("resolved_at", sa.Column("resolved_at", sa.DateTime(timezone=True))),
    )
    for name, column in additions:
        if name in columns:
            continue
        if dialect == "sqlite" and name in {
            "opened_by_user_id",
            "assigned_to_user_id",
            "resolved_by_user_id",
        }:
            op.execute(
                sa.text(
                    f"ALTER TABLE disputes ADD COLUMN {name} "
                    "VARCHAR(36) REFERENCES users(id)"
                )
            )
        else:
            op.add_column("disputes", column)

    if "dispute_evidence" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "dispute_evidence",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("dispute_id", sa.String(36), sa.ForeignKey("disputes.id"), nullable=False),
            sa.Column("attachment_id", sa.String(36), sa.ForeignKey("deal_attachments.id"), nullable=False),
            sa.Column("submitted_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note", sa.Text(), server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("dispute_id", "attachment_id"),
        )
    indexes = _indexes("disputes")
    if "ix_disputes_assigned_to_user_id" not in indexes:
        op.create_index("ix_disputes_assigned_to_user_id", "disputes", ["assigned_to_user_id"])
    if "ix_disputes_priority" not in indexes:
        op.create_index("ix_disputes_priority", "disputes", ["priority"])
    if "ix_disputes_response_due_at" not in indexes:
        op.create_index("ix_disputes_response_due_at", "disputes", ["response_due_at"])
    if "uq_disputes_active_booking" not in indexes:
        op.create_index(
            "uq_disputes_active_booking",
            "disputes",
            ["booking_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('open', 'in_review')"),
            sqlite_where=sa.text("status IN ('open', 'in_review')"),
        )
    evidence_indexes = _indexes("dispute_evidence")
    if "ix_dispute_evidence_dispute_id" not in evidence_indexes:
        op.create_index("ix_dispute_evidence_dispute_id", "dispute_evidence", ["dispute_id"])
    if "ix_dispute_evidence_attachment_id" not in evidence_indexes:
        op.create_index("ix_dispute_evidence_attachment_id", "dispute_evidence", ["attachment_id"])


def downgrade() -> None:
    bind = op.get_bind()
    enhanced_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM disputes WHERE opened_by_user_id IS NOT NULL "
            "OR assigned_to_user_id IS NOT NULL OR priority <> 'high' "
            "OR response_due_at IS NOT NULL OR state_version <> 0 "
            "OR decision_kind IS NOT NULL OR resolved_by_user_id IS NOT NULL "
            "OR resolved_at IS NOT NULL"
        )
    ).scalar_one()
    evidence_count = bind.execute(sa.text("SELECT COUNT(*) FROM dispute_evidence")).scalar_one()
    if enhanced_count or evidence_count:
        raise RuntimeError("Refusing to drop populated dispute case-management data")
    op.drop_table("dispute_evidence")
    op.drop_index("uq_disputes_active_booking", table_name="disputes")
    op.drop_index("ix_disputes_response_due_at", table_name="disputes")
    op.drop_index("ix_disputes_priority", table_name="disputes")
    op.drop_index("ix_disputes_assigned_to_user_id", table_name="disputes")
    op.drop_column("disputes", "resolved_at")
    op.drop_column("disputes", "resolved_by_user_id")
    op.drop_column("disputes", "decision_kind")
    op.drop_column("disputes", "state_version")
    op.drop_column("disputes", "response_due_at")
    op.drop_column("disputes", "priority")
    op.drop_column("disputes", "assigned_to_user_id")
    op.drop_column("disputes", "opened_by_user_id")
