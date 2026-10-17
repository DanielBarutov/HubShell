"""Preserve legacy whole-unit bonuses and add exact wallets and reservation journal."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261017_0078"
down_revision = "20261013_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Freeze old writers while the consistent opening balance is copied.
    op.execute("LOCK TABLE clients IN SHARE ROW EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM clients WHERE balance_bonus < 0
                OR balance_bonus::numeric * 100 > 9223372036854775807
            ) THEN
                RAISE EXCEPTION 'Legacy bonus balance cannot be converted safely; run bonus audit';
            END IF;
        END $$
    """)
    op.create_table(
        "client_bonus_wallets",
        sa.Column("client_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("reserved_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "total_cents >= 0 AND reserved_cents >= 0 AND reserved_cents <= total_cents",
            name="ck_client_bonus_wallet_amounts",
        ),
    )
    op.create_table(
        "client_bonus_reservations",
        sa.Column("client_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("remaining_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("remaining_cents >= 0", name="ck_client_bonus_reservation_amount"),
    )
    op.create_table(
        "client_bonus_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_after_cents", sa.BigInteger(), nullable=False),
        sa.Column("reserved_after_cents", sa.BigInteger(), nullable=False),
        sa.Column("session_reserved_after_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_delta_cents", sa.BigInteger(), nullable=False),
        sa.Column("reserved_delta_cents", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_client_bonus_operations_client_id", "client_bonus_operations", ["client_id"]
    )
    op.execute("""
        INSERT INTO client_bonus_wallets (client_id, total_cents, reserved_cents)
        SELECT id, balance_bonus * 100, 0 FROM clients
    """)
    op.execute("""
        INSERT INTO client_bonus_operations (
            id, client_id, kind, amount_cents, actor_id, reason, idempotency_key,
            session_id, total_after_cents, reserved_after_cents, session_reserved_after_cents,
            total_delta_cents, reserved_delta_cents, created_at
        ) SELECT id, id, 'adjust', balance_bonus * 100, 'bonus-migration',
            'Legacy bonus opening balance', 'bonus-opening:' || id::text,
            NULL, balance_bonus * 100, 0, 0, balance_bonus * 100, 0, now()
        FROM clients WHERE balance_bonus <> 0
    """)


def downgrade() -> None:
    op.execute("""
        LOCK TABLE client_bonus_wallets, client_bonus_reservations,
            client_bonus_operations IN ACCESS EXCLUSIVE MODE
    """)
    # Dropping precision or journal history after real use is never an automatic rollback.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM client_bonus_operations
                WHERE NOT (
                    idempotency_key = 'bonus-opening:' || client_id::text
                    AND kind = 'adjust' AND actor_id = 'bonus-migration'
                    AND reason = 'Legacy bonus opening balance'
                    AND total_delta_cents = amount_cents AND total_after_cents = amount_cents
                    AND reserved_delta_cents = 0 AND reserved_after_cents = 0
                    AND session_reserved_after_cents = 0 AND session_id IS NULL
                )
            ) OR EXISTS (
                SELECT 1 FROM client_bonus_wallets w LEFT JOIN clients c ON c.id = w.client_id
                WHERE c.id IS NULL OR w.reserved_cents <> 0
                    OR w.total_cents <> c.balance_bonus::numeric * 100
            ) THEN
                RAISE EXCEPTION 'Bonus activity prevents lossless downgrade';
            END IF;
        END $$
    """)
    op.drop_index("ix_client_bonus_operations_client_id", table_name="client_bonus_operations")
    op.drop_table("client_bonus_operations")
    op.drop_table("client_bonus_reservations")
    op.drop_table("client_bonus_wallets")
