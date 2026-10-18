"""Add immutable V2 server deposit and delivery references."""

import typing

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260927_0064"
down_revision: str | None = "20260927_0063"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "v2_deposit_credits",
        sa.Column("payment_operation_id", uuid_type, primary_key=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("client_id", uuid_type, nullable=False),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("amount_delta_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("balance_operation_id", uuid_type, nullable=False, unique=True),
        sa.Column("client_delivery_event_id", uuid_type, nullable=False, unique=True),
        sa.Column("confirmed_domain_event_id", uuid_type, nullable=False, unique=True),
        sa.Column("cash_shift_id", uuid_type, nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_v2_deposit_credits_client_id", "v2_deposit_credits", ["client_id"])
    op.create_index("ix_v2_deposit_credits_session_id", "v2_deposit_credits", ["session_id"])
    op.create_index("ix_v2_deposit_credits_device_id", "v2_deposit_credits", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_v2_deposit_credits_device_id", table_name="v2_deposit_credits")
    op.drop_index("ix_v2_deposit_credits_session_id", table_name="v2_deposit_credits")
    op.drop_index("ix_v2_deposit_credits_client_id", table_name="v2_deposit_credits")
    op.drop_table("v2_deposit_credits")
