"""Capture purchase bonus rules independently from later club setting changes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261017_0080"
down_revision = "20261017_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("product_sales", "client_entitlements"):
        op.add_column(
            table, sa.Column("bonus_rate_bps", sa.Integer(), nullable=False, server_default="0")
        )
        op.add_column(table, sa.Column("bonus_session_id", UUID(as_uuid=True), nullable=True))
        op.create_check_constraint(
            f"ck_{table}_bonus_rate", table, "bonus_rate_bps BETWEEN 0 AND 10000"
        )
    op.add_column(
        "client_entitlements", sa.Column("purchase_reason", sa.String(255), nullable=True)
    )
    op.add_column(
        "client_entitlements", sa.Column("purchase_actor_id", sa.String(128), nullable=True)
    )
    op.add_column(
        "client_entitlements",
        sa.Column("bonus_amount_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "client_entitlements",
        sa.Column("bonus_limit_bps", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_entitlements_bonus_amount",
        "client_entitlements",
        "bonus_amount_cents BETWEEN 0 AND price_cents",
    )
    op.create_check_constraint(
        "ck_entitlements_bonus_limit", "client_entitlements", "bonus_limit_bps BETWEEN 0 AND 10000"
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM product_sales WHERE bonus_rate_bps <> 0)
            OR EXISTS (SELECT 1 FROM client_entitlements
                       WHERE bonus_rate_bps <> 0 OR bonus_amount_cents <> 0
                          OR purchase_actor_id IS NOT NULL OR purchase_reason IS NOT NULL) THEN
                RAISE EXCEPTION 'Purchase bonus snapshots cannot be dropped after use';
            END IF;
        END $$
    """)
    op.drop_constraint("ck_entitlements_bonus_limit", "client_entitlements", type_="check")
    op.drop_constraint("ck_entitlements_bonus_amount", "client_entitlements", type_="check")
    op.drop_column("client_entitlements", "purchase_reason")
    op.drop_column("client_entitlements", "purchase_actor_id")
    op.drop_column("client_entitlements", "bonus_limit_bps")
    op.drop_column("client_entitlements", "bonus_amount_cents")
    for table in ("product_sales", "client_entitlements"):
        op.drop_constraint(f"ck_{table}_bonus_rate", table, type_="check")
        op.drop_column(table, "bonus_session_id")
        op.drop_column(table, "bonus_rate_bps")
