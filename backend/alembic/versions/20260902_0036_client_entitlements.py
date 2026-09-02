"""Add durable ordered package entitlements for client queues."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_0036"
down_revision = "20260902_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tariff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", sa.String(length=128), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("remaining_minutes", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("queue_position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("burn_reason", sa.String(length=256), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_client_entitlements_idempotency_key"),
    )
    op.create_index(
        "ix_client_entitlements_client_id",
        "client_entitlements",
        ["client_id"],
    )
    op.create_index(
        "ix_client_entitlements_tariff_id",
        "client_entitlements",
        ["tariff_id"],
    )
    op.create_index(
        "ix_client_entitlements_active_client",
        "client_entitlements",
        ["client_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_client_entitlements_queue",
        "client_entitlements",
        ["client_id", "queue_position"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_entitlements_queue", table_name="client_entitlements")
    op.drop_index("ix_client_entitlements_active_client", table_name="client_entitlements")
    op.drop_index("ix_client_entitlements_tariff_id", table_name="client_entitlements")
    op.drop_index("ix_client_entitlements_client_id", table_name="client_entitlements")
    op.drop_table("client_entitlements")
