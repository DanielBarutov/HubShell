"""Bind guest payments to the reservation that authorizes entry."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261116_0091"
down_revision = "20261116_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guest_session_payments", sa.Column("reservation_id", UUID(as_uuid=True)))


def downgrade() -> None:
    op.drop_column("guest_session_payments", "reservation_id")
