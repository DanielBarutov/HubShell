"""Reserve the target of a V2 session transfer."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261116_0090"
down_revision = "20261106_0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_transfer_reservations",
        sa.Column("operation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_workstation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("target_workstation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_token", sa.String(64), nullable=True),
        sa.Column("target_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_sequence", sa.Integer(), nullable=True),
        sa.Column("source_payload_hash", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "(source_sequence IS NULL AND source_payload_hash IS NULL)"
            " OR (source_sequence IS NOT NULL AND source_sequence = 0"
            " AND source_payload_hash IS NULL)"
            " OR (source_sequence IS NOT NULL AND source_sequence > 0"
            " AND source_payload_hash IS NOT NULL)",
            name="ck_v2_transfer_source_checkpoint",
        ),
        sa.CheckConstraint(
            "source_workstation_id <> target_workstation_id",
            name="ck_v2_transfer_distinct_workstations",
        ),
        sa.CheckConstraint(
            "status in ('preparing', 'committed', 'cancelled', 'expired')",
            name="ck_v2_transfer_reservation_status",
        ),
    )
    for column in ("session_id", "target_workstation_id"):
        op.create_index(
            f"uq_v2_transfer_pending_{column}",
            "v2_transfer_reservations",
            [column],
            unique=True,
            postgresql_where=sa.text("status = 'preparing'"),
        )

    op.create_index(
        "ix_v2_transfer_pending_expiry",
        "v2_transfer_reservations",
        ["expires_at"],
        postgresql_where=sa.text("status = 'preparing'"),
    )

    op.add_column(
        "guest_session_payments",
        sa.Column("transfer_hold", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute("""
        UPDATE guest_session_payments AS payment
        SET transfer_hold = true
        FROM workstations AS workstation
        WHERE workstation.id = payment.workstation_id
          AND workstation.session_mode = 'local_ledger'
          AND workstation.archived_at IS NULL
          AND payment.equipment_type = 'pc'
          AND payment.status IN ('pending', 'confirmed', 'needs_review')
          AND NOT EXISTS (
              SELECT 1 FROM v2_guest_access_grants AS access_grant
              WHERE access_grant.payment_id = payment.id
          )
          AND (
              (
                  payment.session_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM gaming_sessions AS session
                      WHERE session.guest_payment_id = payment.id
                  )
              )
              OR EXISTS (
                  SELECT 1 FROM gaming_sessions AS session
                  WHERE session.id = payment.session_id
                    AND session.workstation_id = payment.workstation_id
                    AND session.status = 'active'
                    AND session.source = 'guest_local_ledger'
                    AND NOT (session.applied_payment_ids::jsonb ? payment.id::text)
              )
          )
    """)
    op.create_index(
        "ix_guest_session_payments_transfer_hold",
        "guest_session_payments",
        ["workstation_id", "session_id"],
        postgresql_where=sa.text("transfer_hold"),
    )
    op.create_table(
        "v2_guest_transfer_access",
        sa.Column("operation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("target_workstation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signed_snapshot", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("v2_guest_transfer_access")
    op.drop_index("ix_guest_session_payments_transfer_hold", table_name="guest_session_payments")
    op.drop_column("guest_session_payments", "transfer_hold")
    op.drop_table("v2_transfer_reservations")
