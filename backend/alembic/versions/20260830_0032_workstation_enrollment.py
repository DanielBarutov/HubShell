"""Add MAC and installation identity for automatic Windows enrollment."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0032"
down_revision: str | None = "20260830_0031"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workstations", sa.Column("mac_address", sa.String(length=17), nullable=True))
    op.add_column(
        "workstations",
        sa.Column("installation_id", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_workstations_mac_address", "workstations", ["mac_address"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_workstations_mac_address", table_name="workstations")
    op.drop_column("workstations", "installation_id")
    op.drop_column("workstations", "mac_address")
