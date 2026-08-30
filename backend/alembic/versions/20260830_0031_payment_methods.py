"""Add configurable club payment methods."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0031"
down_revision: str | None = "20260829_0030"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_methods",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_methods_key", "payment_methods", ["key"])
    op.execute(
        sa.text(
            """
            INSERT INTO payment_methods
                (id, key, name, active, sort_order, created_at, updated_at)
            VALUES
                ('00000000-0000-0000-0000-000000000001', 'balance',
                 'Баланс клиента', true, 10, now(), now()),
                ('00000000-0000-0000-0000-000000000002', 'cash', 'Наличные', true, 20, now(), now())
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_payment_methods_key", table_name="payment_methods")
    op.drop_table("payment_methods")
