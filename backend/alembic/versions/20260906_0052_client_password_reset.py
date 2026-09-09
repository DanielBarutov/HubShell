"""Track client password reset state for one-time passwordless login."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_0052"
down_revision: str | None = "20260906_0051"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column(
            "password_reset_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )



def downgrade() -> None:
    op.drop_column("clients", "password_reset_required")
