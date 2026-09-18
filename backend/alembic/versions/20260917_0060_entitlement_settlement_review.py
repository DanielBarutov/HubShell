"""Persist entitlement settlement retry and manual-review state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0060"
down_revision: str | None = "20260917_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "client_entitlements",
        sa.Column(
            "settlement_status",
            sa.String(length=16),
            nullable=False,
            server_default="settled",
        ),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("settlement_error", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("settlement_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("next_settlement_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_client_entitlements_settlement_status_next_attempt",
        "client_entitlements",
        ["settlement_status", "next_settlement_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_client_entitlements_settlement_status_next_attempt",
        table_name="client_entitlements",
    )
    op.drop_column("client_entitlements", "next_settlement_attempt_at")
    op.drop_column("client_entitlements", "settlement_attempts")
    op.drop_column("client_entitlements", "settlement_error")
    op.drop_column("client_entitlements", "settlement_status")
