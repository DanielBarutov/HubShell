"""Add product sales facts and inventory settlement."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0025"
down_revision: str | None = "20260828_0024"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_sales",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_name", sa.String(length=128), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("guest_name", sa.String(length=128), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("unit_cost_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_cost_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("payment_method", sa.String(length=16), nullable=False),
        sa.Column("cash_shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sold_by", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_product_sales_idempotency_key"),
    )
    op.create_index("ix_product_sales_product_id", "product_sales", ["product_id"])
    op.create_index("ix_product_sales_client_id", "product_sales", ["client_id"])
    op.create_index("ix_product_sales_status", "product_sales", ["status"])
    op.create_index("ix_product_sales_created_at", "product_sales", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_product_sales_created_at", table_name="product_sales")
    op.drop_index("ix_product_sales_status", table_name="product_sales")
    op.drop_index("ix_product_sales_client_id", table_name="product_sales")
    op.drop_index("ix_product_sales_product_id", table_name="product_sales")
    op.drop_table("product_sales")
