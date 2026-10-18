"""Allow an autonomous V2 session lease without a server timeout."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0067"
down_revision: str | None = "20260927_0066"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "v2_session_leases",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE v2_session_leases SET expires_at = issued_at WHERE expires_at IS NULL")
    op.alter_column(
        "v2_session_leases",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
