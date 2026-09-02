"""Persist confirmed direct guest tariff payments."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_0037"
down_revision = "20260902_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guest_session_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workstation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tariff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tariff_quantity", sa.Integer(), nullable=False),
        sa.Column("guest_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("guest_name", sa.String(length=128), nullable=False),
        sa.Column("total_price_cents", sa.Integer(), nullable=False),
        sa.Column(
            "payment_parts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("cash_shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_guest_session_payments_idempotency_key",
        ),
    )
    op.create_index(
        "ix_guest_session_payments_workstation_id",
        "guest_session_payments",
        ["workstation_id"],
    )
    op.create_index(
        "ix_guest_session_payments_tariff_id",
        "guest_session_payments",
        ["tariff_id"],
    )
    op.create_index(
        "ix_guest_session_payments_guest_id",
        "guest_session_payments",
        ["guest_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_guest_session_payments_guest_id", table_name="guest_session_payments")
    op.drop_index("ix_guest_session_payments_tariff_id", table_name="guest_session_payments")
    op.drop_index(
        "ix_guest_session_payments_workstation_id",
        table_name="guest_session_payments",
    )
    op.drop_table("guest_session_payments")
