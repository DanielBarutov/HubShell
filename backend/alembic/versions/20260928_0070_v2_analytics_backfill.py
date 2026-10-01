"""Persist resumable V2 confirmed analytics backfill state and skips."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260928_0070"
down_revision: str | None = "20260927_0069"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "v2_analytics_backfill_runs",
        sa.Column("name", sa.String(length=128), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cutoff_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cutoff_event_id", uuid_type, nullable=True),
        sa.Column("cursor_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_event_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "v2_analytics_backfill_skips",
        sa.Column("backfill_name", sa.String(length=128), nullable=False),
        sa.Column("source_event_id", uuid_type, nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["backfill_name"],
            ["v2_analytics_backfill_runs.name"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("backfill_name", "source_event_id"),
    )


def downgrade() -> None:
    op.drop_table("v2_analytics_backfill_skips")
    op.drop_table("v2_analytics_backfill_runs")
