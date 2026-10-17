"""Persist bonus policies, confirmed source receipts and oldest-first debt allocation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261017_0079"
down_revision = "20261017_0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("LOCK TABLE clients IN SHARE ROW EXCLUSIVE MODE")
    op.create_table(
        "client_bonus_program",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy", JSONB(), nullable=False),
        sa.CheckConstraint("id = 1"),
    )
    op.execute("""
        INSERT INTO client_bonus_program VALUES (1,
            '{"enabled": true, "game_rate_bps": 500, "product_rate_bps": 200,
              "payment_limit_bps": 2000}'::jsonb)
    """)
    op.create_table(
        "client_bonus_program_changes",
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("policy", JSONB(), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "client_bonus_sessions",
        sa.Column("session_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("policy", JSONB(), nullable=False),
        sa.Column("finished", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_client_bonus_sessions_client_id", "client_bonus_sessions", ["client_id"])
    op.create_table(
        "client_bonus_debits",
        sa.Column("operation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("money_cents", sa.BigInteger(), nullable=False),
        sa.Column("paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("receipt_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_key", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("money_cents >= 0 AND paid_cents BETWEEN 0 AND money_cents"),
    )
    op.create_index("ix_client_bonus_debits_client_id", "client_bonus_debits", ["client_id"])
    op.execute("""
        INSERT INTO client_bonus_debits
            (operation_id, client_id, money_cents, paid_cents, created_at)
        SELECT id, id, -balance_cents, 0, created_at FROM clients WHERE balance_cents < 0
    """)
    op.create_table(
        "client_bonus_earnings",
        sa.Column("source_key", sa.String(160), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("rate_bps", sa.Integer(), nullable=False),
        sa.Column("money_cents", sa.BigInteger(), nullable=False),
        sa.Column("paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("released_bonus_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("rate_bps BETWEEN 0 AND 10000"),
        sa.CheckConstraint("money_cents >= 0 AND paid_cents BETWEEN 0 AND money_cents"),
        sa.CheckConstraint("released_bonus_cents >= 0"),
    )
    op.create_index("ix_client_bonus_earnings_client_id", "client_bonus_earnings", ["client_id"])
    op.create_table(
        "client_bonus_receipts",
        sa.Column("receipt_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_client_bonus_receipts_client_id", "client_bonus_receipts", ["client_id"])


def downgrade() -> None:
    op.execute("""
        LOCK TABLE client_bonus_receipts, client_bonus_earnings, client_bonus_debits,
            client_bonus_sessions, client_bonus_program_changes IN ACCESS EXCLUSIVE MODE
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM client_bonus_receipts)
            OR EXISTS (SELECT 1 FROM client_bonus_program_changes)
            OR EXISTS (SELECT 1 FROM client_bonus_sessions) THEN
                RAISE EXCEPTION 'Bonus earnings have activity; downgrade would lose history';
            END IF;
        END $$
    """)
    for table in (
        "client_bonus_receipts",
        "client_bonus_earnings",
        "client_bonus_debits",
        "client_bonus_sessions",
        "client_bonus_program_changes",
        "client_bonus_program",
    ):
        op.drop_table(table)
