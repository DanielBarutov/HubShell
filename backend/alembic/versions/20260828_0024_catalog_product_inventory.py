"""Add product cost and stock fields for operator catalog management."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0024"
down_revision: str | None = "20260828_0023"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("cost_price_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "products",
        sa.Column("stock_quantity", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.alter_column("products", "cost_price_cents", server_default=None)
    op.alter_column("products", "stock_quantity", server_default=None)


def downgrade() -> None:
    op.drop_column("products", "stock_quantity")
    op.drop_column("products", "cost_price_cents")
