"""Persist monotonic per-minute session billing meters."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260829_0028"
down_revision: str | None = "20260829_0027"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_meters",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tariff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("billed_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("billed_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_session_meters_client_id", "session_meters", ["client_id"])
    op.create_index("ix_session_meters_status", "session_meters", ["status"])


def downgrade() -> None:
    op.drop_index("ix_session_meters_status", table_name="session_meters")
    op.drop_index("ix_session_meters_client_id", table_name="session_meters")
    op.drop_table("session_meters")
