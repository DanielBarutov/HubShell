"""Store the per-minute rate on workstation zones."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_0050"
down_revision: str | None = "20260905_0049"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workstation_groups",
        sa.Column("per_minute_price_cents", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.execute(
        sa.text(
            """
            UPDATE workstation_groups AS groups
            SET per_minute_price_cents = rates.price_per_minute_cents
            FROM (
                SELECT DISTINCT ON (group_id)
                    group_id,
                    price_per_minute_cents
                FROM tariffs
                WHERE group_id IS NOT NULL
                  AND billing_mode = 'per_minute'
                  AND active = true
                  AND lifecycle = 'published'
                ORDER BY group_id, price_per_minute_cents, duration_minutes, id
            ) AS rates
            WHERE groups.id = rates.group_id
            """
        )
    )
    op.alter_column(
        "workstation_groups",
        "per_minute_price_cents",
        server_default=None,
        existing_type=sa.BigInteger(),
    )


def downgrade() -> None:
    op.drop_column("workstation_groups", "per_minute_price_cents")
