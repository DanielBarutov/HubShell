"""Persist the exact signed V2 snapshot bound to every issued lease."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0068"
down_revision: str | None = "20260927_0067"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "v2_session_leases",
        sa.Column("signing_key_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "v2_session_leases",
        sa.Column("snapshot_payload", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "v2_session_leases",
        sa.Column("snapshot_signature", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "v2_session_leases",
        sa.Column("snapshot_payload_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("v2_session_leases", "snapshot_payload_hash")
    op.drop_column("v2_session_leases", "snapshot_signature")
    op.drop_column("v2_session_leases", "snapshot_payload")
    op.drop_column("v2_session_leases", "signing_key_id")
