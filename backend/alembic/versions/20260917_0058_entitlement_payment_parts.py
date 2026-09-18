"""Persist payment parts for tariff entitlements."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260917_0058"
down_revision = "20260917_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_entitlements",
        sa.Column("payment_parts", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("cash_shift_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_entitlements", "cash_shift_id")
    op.drop_column("client_entitlements", "payment_parts")
