"""Protect the one-active-session-per-client invariant."""

from alembic import op

revision = "20260902_0034"
down_revision = "20260830_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_gaming_sessions_active_client "
        "ON gaming_sessions (client_id) "
        "WHERE status = 'active' AND client_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_gaming_sessions_active_client")
