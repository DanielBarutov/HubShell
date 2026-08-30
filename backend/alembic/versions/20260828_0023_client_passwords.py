"""Store client password hashes for operator reset flow."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0023"
down_revision: str | None = "20260828_0022"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "password_hash")
