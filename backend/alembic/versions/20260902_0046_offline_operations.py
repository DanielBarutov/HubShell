"""Persist device offline operations and replay results."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_0046"
down_revision = "20260902_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offline_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_offline_operations_idempotency_key"),
        sa.UniqueConstraint(
            "device_id",
            "session_id",
            "sequence",
            name="uq_offline_operations_device_session_sequence",
        ),
    )
    op.create_index(
        "ix_offline_operations_session_id",
        "offline_operations",
        ["session_id"],
    )
    op.create_index(
        "ix_offline_operations_device_id",
        "offline_operations",
        ["device_id"],
    )
    op.create_index(
        "ix_offline_operations_status",
        "offline_operations",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_offline_operations_status", table_name="offline_operations")
    op.drop_index("ix_offline_operations_device_id", table_name="offline_operations")
    op.drop_index("ix_offline_operations_session_id", table_name="offline_operations")
    op.drop_table("offline_operations")
