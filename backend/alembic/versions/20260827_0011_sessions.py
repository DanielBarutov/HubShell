"""Create gaming sessions table.

Revision ID: 20260827_0011
Revises: 20260827_0010
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0011"
down_revision: str | None = "20260827_0010"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    aware_datetime = sa.DateTime(timezone=True)
    op.create_table(
        "gaming_sessions",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workstation_id", uuid_type, nullable=False),
        sa.Column("client_id", uuid_type, nullable=True),
        sa.Column("guest_name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", aware_datetime, nullable=False),
        sa.Column("ended_at", aware_datetime, nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.Column("reservation_id", uuid_type, nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_gaming_sessions_workstation_id", "gaming_sessions", ["workstation_id"])
    op.create_index("ix_gaming_sessions_client_id", "gaming_sessions", ["client_id"])
    op.create_index("ix_gaming_sessions_status", "gaming_sessions", ["status"])
    op.create_index("ix_gaming_sessions_started_at", "gaming_sessions", ["started_at"])
    op.create_index(
        "uq_gaming_sessions_idempotency_key",
        "gaming_sessions",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_gaming_sessions_active_workstation",
        "gaming_sessions",
        ["workstation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_gaming_sessions_active_workstation", table_name="gaming_sessions")
    op.drop_index("uq_gaming_sessions_idempotency_key", table_name="gaming_sessions")
    op.drop_index("ix_gaming_sessions_started_at", table_name="gaming_sessions")
    op.drop_index("ix_gaming_sessions_status", table_name="gaming_sessions")
    op.drop_index("ix_gaming_sessions_client_id", table_name="gaming_sessions")
    op.drop_index("ix_gaming_sessions_workstation_id", table_name="gaming_sessions")
    op.drop_table("gaming_sessions")
