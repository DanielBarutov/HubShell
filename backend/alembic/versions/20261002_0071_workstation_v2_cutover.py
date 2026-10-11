"""Move every persisted workstation to the V2 session owner."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_0071"
down_revision: str | None = "20260928_0070"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.execute("LOCK TABLE workstations, gaming_sessions IN ACCESS EXCLUSIVE MODE")
    active_v1_session_id = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT gaming_sessions.id
            FROM gaming_sessions
            JOIN workstations ON workstations.id = gaming_sessions.workstation_id
            WHERE gaming_sessions.status = 'active'
              AND workstations.session_mode = 'v1_server_owned'
            LIMIT 1
            """
            )
        )
        .scalar_one_or_none()
    )
    if active_v1_session_id is not None:
        raise RuntimeError(
            "Cannot migrate workstations to V2 while V1 sessions are active. "
            "Run POST /api/v1/sessions/cutover/terminate-v1 with the explicit "
            "cutover confirmation, then retry the migration."
        )

    op.execute(
        sa.text(
            "UPDATE workstations "
            "SET session_mode = 'v2_local_ledger' "
            "WHERE session_mode <> 'v2_local_ledger'"
        )
    )
    op.alter_column(
        "workstations",
        "session_mode",
        existing_type=sa.String(length=32),
        server_default="v2_local_ledger",
    )


def downgrade() -> None:
    op.alter_column(
        "workstations",
        "session_mode",
        existing_type=sa.String(length=32),
        server_default=None,
    )
