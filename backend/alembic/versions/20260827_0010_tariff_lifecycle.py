"""Add tariff key, version and lifecycle metadata.

Revision ID: 20260827_0010
Revises: 20260827_0009
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0010"
down_revision: str | None = "20260827_0009"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tariffs", sa.Column("tariff_key", sa.String(length=128), nullable=True))
    op.add_column(
        "tariffs",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "tariffs",
        sa.Column(
            "lifecycle",
            sa.String(length=16),
            nullable=False,
            server_default="published",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE tariffs SET tariff_key = id::text, "
            "lifecycle = CASE WHEN active THEN 'published' ELSE 'archived' END"
        )
    )
    op.alter_column("tariffs", "tariff_key", nullable=False, server_default=None)
    op.alter_column("tariffs", "version", server_default=None)
    op.alter_column("tariffs", "lifecycle", server_default=None)
    op.create_index("ix_tariffs_tariff_key", "tariffs", ["tariff_key"])
    op.create_index(
        "uq_tariffs_tariff_key_version",
        "tariffs",
        ["tariff_key", "version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_tariffs_tariff_key_version", table_name="tariffs")
    op.drop_index("ix_tariffs_tariff_key", table_name="tariffs")
    op.drop_column("tariffs", "lifecycle")
    op.drop_column("tariffs", "version")
    op.drop_column("tariffs", "tariff_key")
