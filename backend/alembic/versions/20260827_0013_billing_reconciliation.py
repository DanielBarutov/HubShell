"""Add durable billing reconciliation records.

Revision ID: 20260827_0013
Revises: 20260827_0012
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0013"
down_revision: str | None = "20260827_0012"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    aware_datetime = sa.DateTime(timezone=True)

    op.create_table(
        "billing_reconciliations",
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("charged_by", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", aware_datetime, nullable=False),
        sa.Column("last_error", sa.String(length=1_000), nullable=True),
        sa.Column("charge_id", uuid_type, nullable=True),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.Column("updated_at", aware_datetime, nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["gaming_sessions.id"],
            name="fk_billing_reconciliations_session",
        ),
        sa.ForeignKeyConstraint(
            ["charge_id"],
            ["session_charges.id"],
            name="fk_billing_reconciliations_charge",
        ),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_billing_reconciliations_idempotency_key"),
    )
    op.create_index(
        "ix_billing_reconciliations_status_next_attempt",
        "billing_reconciliations",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_billing_reconciliations_updated_at",
        "billing_reconciliations",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_billing_reconciliations_updated_at", table_name="billing_reconciliations")
    op.drop_index(
        "ix_billing_reconciliations_status_next_attempt",
        table_name="billing_reconciliations",
    )
    op.drop_table("billing_reconciliations")
