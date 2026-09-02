"""Protect client portal identifiers from concurrent duplicate registration."""

from alembic import op

revision = "20260830_0033"
down_revision = "20260830_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX uq_clients_nickname_lower ON clients (lower(nickname))")
    op.execute("CREATE UNIQUE INDEX uq_clients_phone ON clients (phone) WHERE phone IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX uq_clients_phone")
    op.execute("DROP INDEX uq_clients_nickname_lower")
