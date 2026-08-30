"""Add automatic cash shift opening and closing schedules."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0022"
down_revision: str | None = "20260828_0021"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cash_shift_schedules",
        sa.Column("register_id", sa.String(length=128), primary_key=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("auto_open", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_open_at", sa.Time(), nullable=True),
        sa.Column("auto_close", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_close_at", sa.Time(), nullable=True),
        sa.Column("opening_balance_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.alter_column("cash_shift_schedules", "timezone", server_default=None)
    op.alter_column("cash_shift_schedules", "auto_open", server_default=None)
    op.alter_column("cash_shift_schedules", "auto_close", server_default=None)
    op.alter_column("cash_shift_schedules", "opening_balance_cents", server_default=None)


def downgrade() -> None:
    op.drop_table("cash_shift_schedules")
