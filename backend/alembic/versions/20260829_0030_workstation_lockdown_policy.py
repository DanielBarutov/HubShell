"""Store declarative Windows lockdown policy per workstation group."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0030"
down_revision: str | None = "20260829_0029"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workstation_groups",
        sa.Column(
            "lockdown_policy_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.alter_column("workstation_groups", "lockdown_policy_json", server_default=None)


def downgrade() -> None:
    op.drop_column("workstation_groups", "lockdown_policy_json")
