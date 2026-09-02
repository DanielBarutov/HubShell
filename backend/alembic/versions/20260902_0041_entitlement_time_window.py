"""Persist tariff time-window snapshots on client entitlements."""

import sqlalchemy as sa
from alembic import op

revision = "20260902_0041"
down_revision = "20260902_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_entitlements",
        sa.Column("window_start_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("window_end_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("window_timezone", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_client_entitlements_window_bounds",
        "client_entitlements",
        "(window_start_minute IS NULL AND window_end_minute IS NULL) OR "
        "(window_start_minute >= 0 AND window_start_minute < 1440 AND "
        "window_end_minute >= 0 AND window_end_minute < 1440 AND "
        "window_start_minute <> window_end_minute)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_client_entitlements_window_bounds", "client_entitlements", type_="check")
    op.drop_column("client_entitlements", "window_timezone")
    op.drop_column("client_entitlements", "window_end_minute")
    op.drop_column("client_entitlements", "window_start_minute")
