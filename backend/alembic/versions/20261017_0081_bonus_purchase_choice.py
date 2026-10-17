"""Preserve explicit package bonus-payment choice for content-safe retries."""

import sqlalchemy as sa
from alembic import op

revision = "20261017_0081"
down_revision = "20261017_0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_entitlements",
        sa.Column(
            "bonus_requested",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_check_constraint(
        "ck_entitlements_bonus_choice_amount",
        "client_entitlements",
        "(bonus_amount_cents = 0 OR bonus_requested) AND "
        "bonus_amount_cents::numeric * 10000 <= price_cents::numeric * bonus_limit_bps",
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM client_entitlements WHERE bonus_requested) THEN
                RAISE EXCEPTION 'Bonus purchase choice cannot be dropped after use';
            END IF;
        END $$
    """)
    op.drop_constraint("ck_entitlements_bonus_choice_amount", "client_entitlements", type_="check")
    op.drop_column("client_entitlements", "bonus_requested")
