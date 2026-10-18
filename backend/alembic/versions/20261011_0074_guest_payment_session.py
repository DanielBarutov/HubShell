"""Bind guest time additions to their session."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261011_0074"
down_revision = "20261003_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guest_session_payments", sa.Column("duration_minutes", sa.Integer(), nullable=True)
    )
    op.add_column("guest_session_payments", sa.Column("tariff_name", sa.String(256), nullable=True))
    op.add_column(
        "v2_guest_access_grants",
        sa.Column("is_extension", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "guest_session_payments",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("guest_session_payments", "tariff_name")
    op.drop_column("guest_session_payments", "duration_minutes")
    op.drop_column("v2_guest_access_grants", "is_extension")
    op.drop_column("guest_session_payments", "session_id")
