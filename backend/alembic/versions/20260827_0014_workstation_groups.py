"""Add configurable workstation groups and themes.

Revision ID: 20260827_0014
Revises: 20260827_0013
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0014"
down_revision: str | None = "20260827_0013"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workstation_groups",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("theme", sa.String(length=32), nullable=False, server_default="standard"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.alter_column("workstation_groups", "theme", server_default=None)


def downgrade() -> None:
    op.drop_table("workstation_groups")
