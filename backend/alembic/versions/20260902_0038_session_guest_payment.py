"""Link tariff sessions to their confirmed guest payment."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_0038"
down_revision = "20260902_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gaming_sessions",
        sa.Column("guest_payment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_gaming_sessions_guest_payment_id",
        "gaming_sessions",
        ["guest_payment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_gaming_sessions_guest_payment_id", table_name="gaming_sessions")
    op.drop_column("gaming_sessions", "guest_payment_id")
