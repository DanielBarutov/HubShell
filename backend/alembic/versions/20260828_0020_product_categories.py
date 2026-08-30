"""Add managed product and drink categories."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0020"
down_revision: str | None = "20260828_0019"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_categories",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="product"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_product_categories_kind", "product_categories", ["kind"])
    op.alter_column("product_categories", "kind", server_default=None)
    op.alter_column("product_categories", "active", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_product_categories_kind", table_name="product_categories")
    op.drop_table("product_categories")
