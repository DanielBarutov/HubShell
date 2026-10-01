"""Add server-owned V2 session lease references."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260927_0066"
down_revision: str | None = "20260927_0065"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "v2_session_leases",
        sa.Column("session_id", uuid_type, primary_key=True),
        sa.Column("client_id", uuid_type, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("snapshot_id", uuid_type, nullable=False, unique=True),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_v2_session_leases_client_id", "v2_session_leases", ["client_id"])
    op.create_index("ix_v2_session_leases_device_id", "v2_session_leases", ["device_id"])
    op.create_index("ix_v2_session_leases_status", "v2_session_leases", ["status"])


def downgrade() -> None:
    op.drop_index("ix_v2_session_leases_status", table_name="v2_session_leases")
    op.drop_index("ix_v2_session_leases_device_id", table_name="v2_session_leases")
    op.drop_index("ix_v2_session_leases_client_id", table_name="v2_session_leases")
    op.drop_table("v2_session_leases")
