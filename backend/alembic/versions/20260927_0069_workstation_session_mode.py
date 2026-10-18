"""Persist the explicit V1 or V2 session owner for each workstation."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0069"
down_revision: str | None = "20260927_0068"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workstations",
        sa.Column(
            "session_mode",
            sa.String(length=32),
            nullable=False,
            server_default="v1_server_owned",
        ),
    )
    op.create_check_constraint(
        "ck_workstations_session_mode",
        "workstations",
        "session_mode IN ('v1_server_owned', 'v2_local_ledger')",
    )
    op.alter_column("workstations", "session_mode", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_workstations_session_mode", "workstations", type_="check")
    op.drop_column("workstations", "session_mode")
