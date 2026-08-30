"""Create core module tables.

Revision ID: 20260827_0002
Revises: 20260827_0001
Create Date: 2026-08-27
"""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0002"
down_revision: str | None = "20260827_0001"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    aware_datetime = sa.DateTime(timezone=True)

    op.create_table(
        "workstations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("group_id", sa.String(length=128), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", aware_datetime, nullable=True),
        sa.Column("client_version", sa.String(length=64), nullable=True),
        sa.Column("disabled_reason", sa.String(length=255), nullable=True),
        sa.UniqueConstraint("device_id", name="uq_workstations_device_id"),
    )
    op.create_index("ix_workstations_group_id", "workstations", ["group_id"])

    op.create_table(
        "clients",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("nickname", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("discount_category", sa.String(length=64), nullable=True),
        sa.Column("balance_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("balance_bonus", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.Column("updated_at", aware_datetime, nullable=False),
        sa.Column("blocked_at", aware_datetime, nullable=True),
    )
    op.create_index("ix_clients_nickname", "clients", ["nickname"])
    op.create_index("ix_clients_phone", "clients", ["phone"])

    op.create_table(
        "balance_operations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("client_id", uuid_type, nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("bonus_amount", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name="fk_balance_operations_client"),
        sa.UniqueConstraint("idempotency_key", name="uq_balance_operations_idempotency_key"),
    )
    op.create_index("ix_balance_operations_client_id", "balance_operations", ["client_id"])

    op.create_table(
        "products",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_products_category", "products", ["category"])

    op.create_table(
        "tariffs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("group_id", sa.String(length=128), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", aware_datetime, nullable=False),
        sa.Column("valid_to", aware_datetime, nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_tariffs_group_id", "tariffs", ["group_id"])

    op.create_table(
        "reservations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workstation_ids", postgresql.JSONB(), nullable=False),
        sa.Column("client_id", uuid_type, nullable=True),
        sa.Column("guest_name", sa.String(length=128), nullable=True),
        sa.Column("start_at", aware_datetime, nullable=False),
        sa.Column("end_at", aware_datetime, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("tariff_id", uuid_type, nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", aware_datetime, nullable=False),
        sa.Column("cancelled_at", aware_datetime, nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name="fk_reservations_client"),
    )
    op.create_index("ix_reservations_start_at", "reservations", ["start_at"])
    op.create_index("ix_reservations_end_at", "reservations", ["end_at"])
    op.create_index("ix_reservations_status", "reservations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reservations_status", table_name="reservations")
    op.drop_index("ix_reservations_end_at", table_name="reservations")
    op.drop_index("ix_reservations_start_at", table_name="reservations")
    op.drop_table("reservations")
    op.drop_index("ix_tariffs_group_id", table_name="tariffs")
    op.drop_table("tariffs")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_balance_operations_client_id", table_name="balance_operations")
    op.drop_table("balance_operations")
    op.drop_index("ix_clients_phone", table_name="clients")
    op.drop_index("ix_clients_nickname", table_name="clients")
    op.drop_table("clients")
    op.drop_index("ix_workstations_group_id", table_name="workstations")
    op.drop_table("workstations")
