"""Allow one inbox row per consumer and persist confirmed V2 client facts."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260927_0065"
down_revision: str | None = "20260927_0064"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.drop_constraint("v2_event_inbox_pkey", "v2_event_inbox", type_="primary")
    op.create_primary_key(
        "pk_v2_event_inbox_consumer_event",
        "v2_event_inbox",
        ["consumer_name", "event_id"],
    )
    op.create_table(
        "v2_confirmed_client_facts",
        sa.Column("event_id", uuid_type, primary_key=True),
        sa.Column("operation_id", uuid_type, nullable=False, unique=True),
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
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_v2_confirmed_client_facts_client_id",
        "v2_confirmed_client_facts",
        ["client_id"],
    )
    op.create_index(
        "ix_v2_confirmed_client_facts_session_id",
        "v2_confirmed_client_facts",
        ["session_id"],
    )
    op.create_index(
        "ix_v2_confirmed_client_facts_device_id",
        "v2_confirmed_client_facts",
        ["device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_v2_confirmed_client_facts_device_id", table_name="v2_confirmed_client_facts")
    op.drop_index("ix_v2_confirmed_client_facts_session_id", table_name="v2_confirmed_client_facts")
    op.drop_index("ix_v2_confirmed_client_facts_client_id", table_name="v2_confirmed_client_facts")
    op.drop_table("v2_confirmed_client_facts")
    op.drop_constraint("pk_v2_event_inbox_consumer_event", "v2_event_inbox", type_="primary")
    op.create_primary_key("v2_event_inbox_pkey", "v2_event_inbox", ["event_id"])
