"""Snapshot product category on product sales."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0026"
down_revision: str | None = "20260828_0025"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_sales",
        sa.Column("product_category", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE product_sales SET product_category = 'unknown' "
            "WHERE product_category IS NULL"
        )
    )
    op.alter_column("product_sales", "product_category", nullable=False)


def downgrade() -> None:
    op.drop_column("product_sales", "product_category")
