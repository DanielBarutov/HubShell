"""Split tariff usage windows from sale windows and add buyer audience."""

import sqlalchemy as sa
from alembic import op

revision = "20260917_0055"
down_revision = "20260915_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tariffs",
        sa.Column("time_restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("tariffs", sa.Column("sale_window_start_minute", sa.Integer(), nullable=True))
    op.add_column("tariffs", sa.Column("sale_window_end_minute", sa.Integer(), nullable=True))
    op.add_column("tariffs", sa.Column("usage_window_start_minute", sa.Integer(), nullable=True))
    op.add_column("tariffs", sa.Column("usage_window_end_minute", sa.Integer(), nullable=True))
    op.add_column(
        "tariffs",
        sa.Column("audience", sa.String(length=16), nullable=False, server_default="all"),
    )
    op.execute(
        sa.text(
            "UPDATE tariffs SET time_restricted = TRUE, "
            "sale_window_start_minute = window_start_minute, "
            "sale_window_end_minute = window_end_minute, "
            "usage_window_start_minute = window_start_minute, "
            "usage_window_end_minute = window_end_minute "
            "WHERE window_start_minute IS NOT NULL"
        )
    )
    op.drop_constraint("ck_tariffs_window_bounds", "tariffs", type_="check")
    op.drop_column("tariffs", "window_start_minute")
    op.drop_column("tariffs", "window_end_minute")
    op.create_check_constraint(
        "ck_tariffs_window_configuration",
        "tariffs",
        "(NOT time_restricted AND sale_window_start_minute IS NULL AND "
        "sale_window_end_minute IS NULL AND usage_window_start_minute IS NULL AND "
        "usage_window_end_minute IS NULL AND window_timezone IS NULL) OR "
        "(time_restricted AND sale_window_start_minute >= 0 AND "
        "sale_window_start_minute < 1440 AND sale_window_end_minute >= 0 AND "
        "sale_window_end_minute < 1440 AND sale_window_start_minute <> sale_window_end_minute "
        "AND usage_window_start_minute >= 0 AND usage_window_start_minute < 1440 AND "
        "usage_window_end_minute >= 0 AND usage_window_end_minute < 1440 AND "
        "usage_window_start_minute <> usage_window_end_minute AND window_timezone IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_tariffs_audience",
        "tariffs",
        "audience IN ('all', 'guest', 'registered')",
    )

    op.add_column(
        "client_entitlements",
        sa.Column("time_restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("sale_window_start_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("sale_window_end_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("usage_window_start_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("usage_window_end_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("audience", sa.String(length=16), nullable=False, server_default="all"),
    )
    op.execute(
        sa.text(
            "UPDATE client_entitlements SET time_restricted = TRUE, "
            "sale_window_start_minute = window_start_minute, "
            "sale_window_end_minute = window_end_minute, "
            "usage_window_start_minute = window_start_minute, "
            "usage_window_end_minute = window_end_minute "
            "WHERE window_start_minute IS NOT NULL"
        )
    )
    op.drop_constraint(
        "ck_client_entitlements_window_bounds",
        "client_entitlements",
        type_="check",
    )
    op.drop_column("client_entitlements", "window_start_minute")
    op.drop_column("client_entitlements", "window_end_minute")
    op.create_check_constraint(
        "ck_client_entitlements_window_configuration",
        "client_entitlements",
        "(NOT time_restricted AND sale_window_start_minute IS NULL AND "
        "sale_window_end_minute IS NULL AND usage_window_start_minute IS NULL AND "
        "usage_window_end_minute IS NULL AND window_timezone IS NULL) OR "
        "(time_restricted AND sale_window_start_minute >= 0 AND "
        "sale_window_start_minute < 1440 AND sale_window_end_minute >= 0 AND "
        "sale_window_end_minute < 1440 AND sale_window_start_minute <> sale_window_end_minute "
        "AND usage_window_start_minute >= 0 AND usage_window_start_minute < 1440 AND "
        "usage_window_end_minute >= 0 AND usage_window_end_minute < 1440 AND "
        "usage_window_start_minute <> usage_window_end_minute AND window_timezone IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_client_entitlements_audience",
        "client_entitlements",
        "audience IN ('all', 'guest', 'registered')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_client_entitlements_audience", "client_entitlements", type_="check")
    op.drop_constraint(
        "ck_client_entitlements_window_configuration",
        "client_entitlements",
        type_="check",
    )
    op.add_column(
        "client_entitlements",
        sa.Column("window_start_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("window_end_minute", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE client_entitlements SET window_start_minute = usage_window_start_minute, "
            "window_end_minute = usage_window_end_minute WHERE time_restricted"
        )
    )
    op.drop_column("client_entitlements", "audience")
    op.drop_column("client_entitlements", "usage_window_end_minute")
    op.drop_column("client_entitlements", "usage_window_start_minute")
    op.drop_column("client_entitlements", "sale_window_end_minute")
    op.drop_column("client_entitlements", "sale_window_start_minute")
    op.drop_column("client_entitlements", "time_restricted")
    op.create_check_constraint(
        "ck_client_entitlements_window_bounds",
        "client_entitlements",
        "(window_start_minute IS NULL AND window_end_minute IS NULL) OR "
        "(window_start_minute >= 0 AND window_start_minute < 1440 AND "
        "window_end_minute >= 0 AND window_end_minute < 1440 AND "
        "window_start_minute <> window_end_minute)",
    )

    op.drop_constraint("ck_tariffs_audience", "tariffs", type_="check")
    op.drop_constraint("ck_tariffs_window_configuration", "tariffs", type_="check")
    op.add_column("tariffs", sa.Column("window_start_minute", sa.Integer(), nullable=True))
    op.add_column("tariffs", sa.Column("window_end_minute", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE tariffs SET window_start_minute = usage_window_start_minute, "
            "window_end_minute = usage_window_end_minute WHERE time_restricted"
        )
    )
    op.drop_column("tariffs", "audience")
    op.drop_column("tariffs", "usage_window_end_minute")
    op.drop_column("tariffs", "usage_window_start_minute")
    op.drop_column("tariffs", "sale_window_end_minute")
    op.drop_column("tariffs", "sale_window_start_minute")
    op.drop_column("tariffs", "time_restricted")
    op.create_check_constraint(
        "ck_tariffs_window_bounds",
        "tariffs",
        "(window_start_minute IS NULL AND window_end_minute IS NULL) OR "
        "(window_start_minute >= 0 AND window_start_minute < 1440 AND "
        "window_end_minute >= 0 AND window_end_minute < 1440 AND "
        "window_start_minute <> window_end_minute)",
    )
