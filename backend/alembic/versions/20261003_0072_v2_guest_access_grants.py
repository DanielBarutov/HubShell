"""Persist one-time anonymous V2 guest access grants."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261003_0072"
down_revision: str | None = "20261002_0071"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "v2_guest_access_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workstation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", sa.LargeBinary(), nullable=True),
        sa.Column("signature", sa.LargeBinary(), nullable=True),
        sa.Column("signing_key_id", sa.String(length=128), nullable=True),
        sa.UniqueConstraint("payment_id", name="uq_v2_guest_access_payment"),
    )
    op.create_index("ix_v2_guest_access_workstation", "v2_guest_access_grants", ["workstation_id"])
    op.create_index("ix_v2_guest_access_expires", "v2_guest_access_grants", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_v2_guest_access_expires", table_name="v2_guest_access_grants")
    op.drop_index("ix_v2_guest_access_workstation", table_name="v2_guest_access_grants")
    op.drop_table("v2_guest_access_grants")
