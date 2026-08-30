"""Add workstation archive marker for safe operator deletion."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0019"
down_revision: str | None = "20260827_0018"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workstations", sa.Column("archived_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("workstations", "archived_at")
