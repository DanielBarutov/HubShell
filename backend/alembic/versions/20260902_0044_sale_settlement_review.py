"""Persist unresolved product sale settlement errors."""

import sqlalchemy as sa
from alembic import op

revision = "20260902_0044"
down_revision = "20260902_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_sales",
        sa.Column("settlement_error", sa.String(length=1_000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_sales", "settlement_error")
