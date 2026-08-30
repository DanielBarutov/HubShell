"""Store per-zone manager credential verifiers for Windows clients."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0029"
down_revision: str | None = "20260829_0028"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workstation_groups",
        sa.Column("manager_password_verifier", sa.String(length=4096), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workstation_groups", "manager_password_verifier")
