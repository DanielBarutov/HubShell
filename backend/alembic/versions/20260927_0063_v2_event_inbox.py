"""Add the durable V2 server inbox boundary."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260927_0063"
down_revision: str | None = "20260921_0062"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "v2_event_inbox",
        sa.Column("event_id", uuid_type, primary_key=True),
        sa.Column("consumer_name", sa.String(length=128), nullable=False),
        sa.Column("operation_id", uuid_type, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("producer_id", sa.String(length=128), nullable=False),
        sa.Column("client_id", uuid_type, nullable=False),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("causation_id", uuid_type, nullable=True),
        sa.Column("correlation_id", uuid_type, nullable=False),
        sa.Column("traceparent", sa.String(length=55), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "consumer_name",
            "producer_id",
            "operation_id",
            name="uq_v2_event_inbox_consumer_producer_operation",
        ),
        sa.UniqueConstraint(
            "consumer_name",
            "producer_id",
            "session_id",
            "sequence",
            name="uq_v2_event_inbox_consumer_producer_session_sequence",
        ),
    )
    op.create_index("ix_v2_event_inbox_client_id", "v2_event_inbox", ["client_id"])
    op.create_index("ix_v2_event_inbox_session_id", "v2_event_inbox", ["session_id"])
    op.create_index("ix_v2_event_inbox_device_id", "v2_event_inbox", ["device_id"])

    op.create_table(
        "v2_server_outbox",
        sa.Column("event_id", uuid_type, primary_key=True),
        sa.Column("operation_id", uuid_type, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("producer_id", sa.String(length=128), nullable=False),
        sa.Column("client_id", uuid_type, nullable=False),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("causation_id", uuid_type, nullable=True),
        sa.Column("correlation_id", uuid_type, nullable=False),
        sa.Column("traceparent", sa.String(length=55), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("partition_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=2_000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_v2_server_outbox_pending",
        "v2_server_outbox",
        ["status", "created_at"],
    )

    op.create_table(
        "v2_session_chains",
        sa.Column("session_id", uuid_type, primary_key=True),
        sa.Column("client_id", uuid_type, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("producer_id", sa.String(length=128), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("last_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_v2_session_chains_client_id", "v2_session_chains", ["client_id"])
    op.create_index("ix_v2_session_chains_device_id", "v2_session_chains", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_v2_session_chains_device_id", table_name="v2_session_chains")
    op.drop_index("ix_v2_session_chains_client_id", table_name="v2_session_chains")
    op.drop_table("v2_session_chains")
    op.drop_index("ix_v2_server_outbox_pending", table_name="v2_server_outbox")
    op.drop_table("v2_server_outbox")
    op.drop_index("ix_v2_event_inbox_device_id", table_name="v2_event_inbox")
    op.drop_index("ix_v2_event_inbox_session_id", table_name="v2_event_inbox")
    op.drop_index("ix_v2_event_inbox_client_id", table_name="v2_event_inbox")
    op.drop_table("v2_event_inbox")
