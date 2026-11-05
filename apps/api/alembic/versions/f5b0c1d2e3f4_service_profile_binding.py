"""Bind public services to a concrete supply profile.

Revision ID: f5b0c1d2e3f4
Revises: f49a012bc3d4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5b0c1d2e3f4"
down_revision: str | None = "f49a012bc3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("services")}


def upgrade() -> None:
    columns = _columns()
    if "resource_type" not in columns:
        op.add_column("services", sa.Column("resource_type", sa.String(16), nullable=True))
    if "resource_id" not in columns:
        op.add_column("services", sa.Column("resource_id", sa.String(36), nullable=True))
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE services SET resource_type = 'artist', "
        "resource_id = (SELECT id FROM artists WHERE artists.organization_id = services.organization_id) "
        "WHERE resource_id IS NULL AND "
        "(SELECT COUNT(*) FROM artists WHERE artists.organization_id = services.organization_id) = 1 "
        "AND (SELECT COUNT(*) FROM venues WHERE venues.organization_id = services.organization_id) = 0 "
        "AND services.category_code = "
        "(SELECT category FROM artists WHERE artists.organization_id = services.organization_id)"
    ))
    bind.execute(sa.text(
        "UPDATE services SET resource_type = 'venue', "
        "resource_id = (SELECT id FROM venues WHERE venues.organization_id = services.organization_id) "
        "WHERE resource_id IS NULL AND "
        "(SELECT COUNT(*) FROM venues WHERE venues.organization_id = services.organization_id) = 1 "
        "AND (SELECT COUNT(*) FROM artists WHERE artists.organization_id = services.organization_id) = 0 "
        "AND services.category_code = 'venue'"
    ))


def downgrade() -> None:
    bound = op.get_bind().execute(
        sa.text("SELECT 1 FROM services WHERE resource_id IS NOT NULL LIMIT 1")
    ).first()
    if bound:
        raise RuntimeError("Refusing to drop populated service profile bindings")
    columns = _columns()
    if "resource_id" in columns:
        op.drop_column("services", "resource_id")
    if "resource_type" in columns:
        op.drop_column("services", "resource_type")
