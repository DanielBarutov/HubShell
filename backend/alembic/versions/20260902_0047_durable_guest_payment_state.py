"""Persist durable state and author for guest direct payments."""

import sqlalchemy as sa
from alembic import op

revision = "20260902_0047"
down_revision = "20260902_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guest_session_payments",
        sa.Column("created_by", sa.String(length=128), nullable=False, server_default="system"),
    )


def downgrade() -> None:
    op.drop_column("guest_session_payments", "created_by")
