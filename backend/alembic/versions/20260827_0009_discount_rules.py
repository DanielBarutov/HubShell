"""Add extensible discount rules for catalog quotes.

Revision ID: 20260827_0009
Revises: 20260827_0008
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0009"
down_revision: str | None = "20260827_0008"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discount_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("percent_bps", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint(
            "percent_bps >= 0 AND percent_bps <= 10000",
            name="ck_discount_rules_percent_bps",
        ),
        sa.CheckConstraint("priority >= 0", name="ck_discount_rules_priority"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discount_rules_category", "discount_rules", ["category"])
    op.create_index("ix_discount_rules_valid_from", "discount_rules", ["valid_from"])


def downgrade() -> None:
    op.drop_index("ix_discount_rules_valid_from", table_name="discount_rules")
    op.drop_index("ix_discount_rules_category", table_name="discount_rules")
    op.drop_table("discount_rules")
