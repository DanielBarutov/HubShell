"""Allow gRPC method names in audit actions.

Revision ID: 20260827_0008
Revises: 20260827_0007
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0008"
down_revision: str | None = "20260827_0007"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "audit_events",
        "action",
        existing_type=sa.String(length=16),
        type_=sa.String(length=64),
    )


def downgrade() -> None:
    op.alter_column(
        "audit_events",
        "action",
        existing_type=sa.String(length=64),
        type_=sa.String(length=16),
    )
