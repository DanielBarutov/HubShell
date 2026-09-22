"""Add durable analytics outbox, projection, and report job storage."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_0062"
down_revision: str | None = "20260918_0061"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    aware_datetime = sa.DateTime(timezone=True)

    op.create_table(
        "analytics_outbox_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", aware_datetime, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.Column("published_at", aware_datetime, nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_analytics_outbox_idempotency_key"),
    )
    op.create_index(
        "ix_analytics_outbox_unpublished",
        "analytics_outbox_events",
        ["published_at", "occurred_at"],
    )

    op.create_table(
        "analytics_projection_events",
        sa.Column("event_id", uuid_type, primary_key=True),
        sa.Column("applied_at", aware_datetime, nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["analytics_outbox_events.id"],
            name="fk_analytics_projection_event_outbox",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "analytics_projection_daily",
        sa.Column("metric_key", sa.String(length=128), nullable=False),
        sa.Column("bucket_start", aware_datetime, nullable=False),
        sa.Column("dimensions_key", sa.String(length=1000), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(), nullable=False),
        sa.Column("value_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("quantity", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("event_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", aware_datetime, nullable=False),
        sa.PrimaryKeyConstraint(
            "metric_key",
            "bucket_start",
            "dimensions_key",
            name="pk_analytics_projection_daily",
        ),
    )
    op.create_index(
        "ix_analytics_projection_daily_bucket",
        "analytics_projection_daily",
        ["bucket_start", "metric_key"],
    )

    op.create_table(
        "analytics_report_jobs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("report_name", sa.String(length=128), nullable=False),
        sa.Column("export_format", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("include_pii", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.Column("started_at", aware_datetime, nullable=True),
        sa.Column("completed_at", aware_datetime, nullable=True),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("artifact_token_hash", sa.String(length=64), nullable=True),
        sa.Column("artifact_content_type", sa.String(length=128), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("artifact_size", sa.BigInteger(), nullable=True),
        sa.Column("artifact_expires_at", aware_datetime, nullable=True),
        sa.Column("artifact_content", sa.LargeBinary(), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_analytics_report_idempotency_key"),
    )
    op.create_index("ix_analytics_report_status", "analytics_report_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_analytics_report_status", table_name="analytics_report_jobs")
    op.drop_table("analytics_report_jobs")
    op.drop_index("ix_analytics_projection_daily_bucket", table_name="analytics_projection_daily")
    op.drop_table("analytics_projection_daily")
    op.drop_table("analytics_projection_events")
    op.drop_index("ix_analytics_outbox_unpublished", table_name="analytics_outbox_events")
    op.drop_table("analytics_outbox_events")
