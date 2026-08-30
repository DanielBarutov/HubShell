"""Persist guest profiles and link them to reservations and sessions.

Revision ID: 20260827_0017
Revises: 20260827_0016
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0017"
down_revision: str | None = "20260827_0016"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    aware_datetime = sa.DateTime(timezone=True)

    op.create_table(
        "guests",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("nickname", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("discount_category", sa.String(length=64), nullable=True),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.Column("updated_at", aware_datetime, nullable=False),
    )
    op.create_index("ix_guests_nickname", "guests", ["nickname"])
    op.create_index("ix_guests_phone", "guests", ["phone"])

    op.add_column(
        "reservations",
        sa.Column("guest_id", uuid_type, nullable=True),
    )
    op.create_index("ix_reservations_guest_id", "reservations", ["guest_id"])
    op.create_foreign_key(
        "fk_reservations_guest",
        "reservations",
        "guests",
        ["guest_id"],
        ["id"],
    )

    op.add_column(
        "gaming_sessions",
        sa.Column("guest_id", uuid_type, nullable=True),
    )
    op.create_index("ix_gaming_sessions_guest_id", "gaming_sessions", ["guest_id"])
    op.create_foreign_key(
        "fk_gaming_sessions_guest",
        "gaming_sessions",
        "guests",
        ["guest_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_gaming_sessions_guest", "gaming_sessions", type_="foreignkey")
    op.drop_index("ix_gaming_sessions_guest_id", table_name="gaming_sessions")
    op.drop_column("gaming_sessions", "guest_id")
    op.drop_constraint("fk_reservations_guest", "reservations", type_="foreignkey")
    op.drop_index("ix_reservations_guest_id", table_name="reservations")
    op.drop_column("reservations", "guest_id")
    op.drop_index("ix_guests_phone", table_name="guests")
    op.drop_index("ix_guests_nickname", table_name="guests")
    op.drop_table("guests")
