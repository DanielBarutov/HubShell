"""Persist V2 minute bonus grants and immutable synchronization checkpoints."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261017_0082"
down_revision = "20261017_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_bonus_budgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("snapshot_id", UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("last_payload_hash", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("budget_cents", sa.BigInteger(), nullable=False),
        sa.Column("spent_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("payment_limit_bps", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("session_id", "idempotency_key"),
        sa.UniqueConstraint("session_id", "version"),
        sa.CheckConstraint(
            "version > 0 AND ((budget_cents > 0 AND payment_limit_bps BETWEEN 1 AND 10000) "
            "OR (cancelled AND budget_cents = 0 AND payment_limit_bps = 0))"
        ),
        sa.CheckConstraint("NOT cancelled OR NOT active"),
        sa.CheckConstraint("spent_cents >= 0 AND spent_cents <= budget_cents"),
    )
    op.create_index("ix_v2_bonus_budgets_session_id", "v2_bonus_budgets", ["session_id"])
    op.create_index(
        "uq_v2_bonus_budget_active",
        "v2_bonus_budgets",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM v2_bonus_budgets) THEN
            RAISE EXCEPTION 'V2 bonus grant history cannot be dropped after use';
        END IF;
    END $$""")
    op.drop_table("v2_bonus_budgets")
