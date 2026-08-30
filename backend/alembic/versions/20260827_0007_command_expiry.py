"""Add workstation command expiry timestamps.

Revision ID: 20260827_0007
Revises: 20260827_0006
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0007"
down_revision: str | None = "20260827_0006"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workstation_commands",
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP + INTERVAL '120 seconds'"),
        ),
    )
    op.alter_column("workstation_commands", "expires_at", server_default=None)
    op.create_index(
        "ix_workstation_commands_expires_at",
        "workstation_commands",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workstation_commands_expires_at", table_name="workstation_commands")
    op.drop_column("workstation_commands", "expires_at")
