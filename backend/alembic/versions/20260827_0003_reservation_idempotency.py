"""Add reservation idempotency keys.

Revision ID: 20260827_0003
Revises: 20260827_0002
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0003"
down_revision: str | None = "20260827_0002"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reservations",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_reservations_idempotency_key",
        "reservations",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_reservations_idempotency_key", table_name="reservations")
    op.drop_column("reservations", "idempotency_key")
