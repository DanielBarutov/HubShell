"""Protect cash movement references from duplicate posting.

Revision ID: 20260827_0016
Revises: 20260827_0015
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0016"
down_revision: str | None = "20260827_0015"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_cash_movements_reference",
        "cash_movements",
        ["reference_type", "reference_id"],
        unique=True,
        postgresql_where=sa.text(
            "reference_type IS NOT NULL AND reference_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_cash_movements_reference", table_name="cash_movements")
