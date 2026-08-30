"""Add metered tariff fields and sequential session quantity."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0027"
down_revision: str | None = "20260828_0026"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tariffs",
        sa.Column("billing_mode", sa.String(length=16), nullable=False, server_default="block"),
    )
    op.add_column(
        "tariffs",
        sa.Column("price_per_minute_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tariffs",
        sa.Column("free_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "gaming_sessions",
        sa.Column("tariff_quantity", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("tariffs", "billing_mode", server_default=None)
    op.alter_column("tariffs", "price_per_minute_cents", server_default=None)
    op.alter_column("tariffs", "free_minutes", server_default=None)
    op.alter_column("gaming_sessions", "tariff_quantity", server_default=None)


def downgrade() -> None:
    op.drop_column("gaming_sessions", "tariff_quantity")
    op.drop_column("tariffs", "free_minutes")
    op.drop_column("tariffs", "price_per_minute_cents")
    op.drop_column("tariffs", "billing_mode")
