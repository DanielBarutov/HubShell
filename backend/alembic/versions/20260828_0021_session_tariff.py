"""Store the tariff selected when a gaming session starts."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0021"
down_revision: str | None = "20260828_0020"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gaming_sessions",
        sa.Column("tariff_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_gaming_sessions_tariff_id", "gaming_sessions", ["tariff_id"])


def downgrade() -> None:
    op.drop_index("ix_gaming_sessions_tariff_id", table_name="gaming_sessions")
    op.drop_column("gaming_sessions", "tariff_id")
