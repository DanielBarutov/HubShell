"""Persist package time consumed by each session meter."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_0043"
down_revision = "20260902_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_meters",
        sa.Column("package_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "session_meters",
        sa.Column("active_entitlement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_session_meters_active_entitlement_id",
        "session_meters",
        ["active_entitlement_id"],
    )
    op.alter_column("session_meters", "package_minutes", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_session_meters_active_entitlement_id", table_name="session_meters")
    op.drop_column("session_meters", "active_entitlement_id")
    op.drop_column("session_meters", "package_minutes")
