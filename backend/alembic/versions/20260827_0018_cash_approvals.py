"""Add supervisor approvals for risky cash operations.

Revision ID: 20260827_0018
Revises: 20260827_0017
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0018"
down_revision: str | None = "20260827_0017"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cash_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("target_key", sa.String(length=128), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["shift_id"],
            ["cash_shifts.id"],
            name="fk_cash_approvals_shift",
        ),
    )
    op.create_index("ix_cash_approvals_shift_id", "cash_approvals", ["shift_id"])
    op.create_index(
        "uq_cash_approvals_idempotency_key",
        "cash_approvals",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_cash_approvals_target",
        "cash_approvals",
        ["shift_id", "kind", "target_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_cash_approvals_target", table_name="cash_approvals")
    op.drop_index("uq_cash_approvals_idempotency_key", table_name="cash_approvals")
    op.drop_index("ix_cash_approvals_shift_id", table_name="cash_approvals")
    op.drop_table("cash_approvals")
