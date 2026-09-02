"""Persist explicit session transfer offers."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_0045"
down_revision = "20260902_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_transfer_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_workstation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_workstation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requires_package_burn", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("warning", sa.String(length=256), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("confirm_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token", name="uq_session_transfer_offers_token"),
        sa.UniqueConstraint("idempotency_key", name="uq_session_transfer_offers_idempotency_key"),
        sa.UniqueConstraint(
            "confirm_idempotency_key",
            name="uq_session_transfer_offers_confirm_idempotency_key",
        ),
    )
    op.create_index(
        "ix_session_transfer_offers_session_id",
        "session_transfer_offers",
        ["session_id"],
    )
    op.create_index(
        "ix_session_transfer_offers_client_id",
        "session_transfer_offers",
        ["client_id"],
    )
    op.create_index(
        "ix_session_transfer_offers_target_workstation_id",
        "session_transfer_offers",
        ["target_workstation_id"],
    )
    op.create_index(
        "ix_session_transfer_offers_status",
        "session_transfer_offers",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_transfer_offers_status",
        table_name="session_transfer_offers",
    )
    op.drop_index(
        "ix_session_transfer_offers_target_workstation_id",
        table_name="session_transfer_offers",
    )
    op.drop_index("ix_session_transfer_offers_client_id", table_name="session_transfer_offers")
    op.drop_index("ix_session_transfer_offers_session_id", table_name="session_transfer_offers")
    op.drop_table("session_transfer_offers")
