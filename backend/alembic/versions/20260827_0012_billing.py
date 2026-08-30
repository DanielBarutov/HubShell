"""Add ledger operation type and session charges.

Revision ID: 20260827_0012
Revises: 20260827_0011
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0012"
down_revision: str | None = "20260827_0011"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    aware_datetime = sa.DateTime(timezone=True)

    op.add_column(
        "balance_operations",
        sa.Column(
            "operation_type",
            sa.String(length=32),
            nullable=False,
            server_default="top_up",
        ),
    )
    op.alter_column("balance_operations", "operation_type", server_default=None)

    op.create_table(
        "session_charges",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("client_id", uuid_type, nullable=False),
        sa.Column("balance_operation_id", uuid_type, nullable=False),
        sa.Column("tariff_id", uuid_type, nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("amount_before_discount_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_percent_bps", sa.Integer(), nullable=False),
        sa.Column("discount_category", sa.String(length=64), nullable=True),
        sa.Column("charged_by", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["gaming_sessions.id"],
            name="fk_session_charges_session",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name="fk_session_charges_client",
        ),
        sa.ForeignKeyConstraint(
            ["balance_operation_id"],
            ["balance_operations.id"],
            name="fk_session_charges_balance_operation",
        ),
    )
    op.create_index(
        "uq_session_charges_session_id",
        "session_charges",
        ["session_id"],
        unique=True,
    )
    op.create_index("ix_session_charges_client_id", "session_charges", ["client_id"])
    op.create_index(
        "uq_session_charges_idempotency_key",
        "session_charges",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_session_charges_idempotency_key", table_name="session_charges")
    op.drop_index("ix_session_charges_client_id", table_name="session_charges")
    op.drop_index("uq_session_charges_session_id", table_name="session_charges")
    op.drop_table("session_charges")
    op.drop_column("balance_operations", "operation_type")
