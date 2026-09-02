"""Persist the per-login free-minute grant on sessions."""

import sqlalchemy as sa
from alembic import op

revision = "20260902_0039"
down_revision = "20260902_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gaming_sessions",
        sa.Column("login_grant_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("gaming_sessions", "login_grant_minutes", server_default=None)


def downgrade() -> None:
    op.drop_column("gaming_sessions", "login_grant_minutes")
