"""Add durable workstation command delivery records.

Revision ID: 20260827_0004
Revises: 20260827_0003
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0004"
down_revision: str | None = "20260827_0003"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workstation_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workstation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_message", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["workstation_id"],
            ["workstations.id"],
            name="fk_workstation_commands_workstation",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_workstation_commands_idempotency_key"),
    )
    op.create_index(
        "ix_workstation_commands_workstation_id",
        "workstation_commands",
        ["workstation_id"],
    )
    op.create_index("ix_workstation_commands_status", "workstation_commands", ["status"])


def downgrade() -> None:
    op.drop_index("ix_workstation_commands_status", table_name="workstation_commands")
    op.drop_index("ix_workstation_commands_workstation_id", table_name="workstation_commands")
    op.drop_table("workstation_commands")
