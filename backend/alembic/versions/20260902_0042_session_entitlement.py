"""Link a gaming session to its server-activated package entitlement."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_0042"
down_revision = "20260902_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gaming_sessions",
        sa.Column("entitlement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_gaming_sessions_entitlement_id",
        "gaming_sessions",
        ["entitlement_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_gaming_sessions_entitlement_id", table_name="gaming_sessions")
    op.drop_column("gaming_sessions", "entitlement_id")
