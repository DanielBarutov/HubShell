"""Add cash shift and cash movement ledgers.

Revision ID: 20260827_0015
Revises: 20260827_0014
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0015"
down_revision: str | None = "20260827_0014"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    aware_datetime = sa.DateTime(timezone=True)

    op.create_table(
        "cash_shifts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("register_id", sa.String(length=128), nullable=False),
        sa.Column("opened_by", sa.String(length=128), nullable=False),
        sa.Column("opened_at", aware_datetime, nullable=False),
        sa.Column("opening_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("expected_close_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("open_idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("closed_by", sa.String(length=128), nullable=True),
        sa.Column("closed_at", aware_datetime, nullable=True),
        sa.Column("actual_close_cents", sa.BigInteger(), nullable=True),
        sa.Column("difference_cents", sa.BigInteger(), nullable=True),
        sa.Column("close_idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "uq_cash_shifts_open_idempotency_key",
        "cash_shifts",
        ["open_idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_cash_shifts_close_idempotency_key",
        "cash_shifts",
        ["close_idempotency_key"],
        unique=True,
    )
    op.create_index("ix_cash_shifts_register_id", "cash_shifts", ["register_id"])
    op.create_index("ix_cash_shifts_status", "cash_shifts", ["status"])
    op.create_index(
        "uq_cash_shifts_open_register_id",
        "cash_shifts",
        ["register_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "cash_movements",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("shift_id", uuid_type, nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["shift_id"],
            ["cash_shifts.id"],
            name="fk_cash_movements_shift",
        ),
    )
    op.create_index(
        "uq_cash_movements_idempotency_key",
        "cash_movements",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index("ix_cash_movements_shift_id", "cash_movements", ["shift_id"])
    op.create_index(
        "ix_cash_movements_shift_created_at",
        "cash_movements",
        ["shift_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cash_movements_shift_created_at", table_name="cash_movements")
    op.drop_index("ix_cash_movements_shift_id", table_name="cash_movements")
    op.drop_index("uq_cash_movements_idempotency_key", table_name="cash_movements")
    op.drop_table("cash_movements")
    op.drop_index("uq_cash_shifts_open_register_id", table_name="cash_shifts")
    op.drop_index("ix_cash_shifts_status", table_name="cash_shifts")
    op.drop_index("ix_cash_shifts_register_id", table_name="cash_shifts")
    op.drop_index("uq_cash_shifts_close_idempotency_key", table_name="cash_shifts")
    op.drop_index("uq_cash_shifts_open_idempotency_key", table_name="cash_shifts")
    op.drop_table("cash_shifts")
