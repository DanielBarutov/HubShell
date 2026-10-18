"""Use neutral names for the single supported workstation session runtime."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_0073"
down_revision: str | None = "20261003_0072"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    # 0069/0071 оставили CHECK только для старых versioned-значений.
    # Сначала снимаем его, иначе PostgreSQL проверяет каждую строку UPDATE
    # до завершения преобразования и отклоняет `local_ledger`.
    op.drop_constraint(
        "ck_workstations_session_mode",
        "workstations",
        type_="check",
    )
    op.execute(
        sa.text(
            "UPDATE workstations SET session_mode = 'local_ledger' "
            "WHERE session_mode IN ('v1_server_owned', 'v2_local_ledger')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE gaming_sessions SET source = 'local_ledger' "
            "WHERE source = 'v2_local_ledger'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE gaming_sessions SET source = 'guest_local_ledger' "
            "WHERE source = 'v2_guest_local_ledger'"
        )
    )
    op.alter_column(
        "workstations",
        "session_mode",
        existing_type=sa.String(length=32),
        server_default="local_ledger",
    )
    op.create_check_constraint(
        "ck_workstations_session_mode",
        "workstations",
        "session_mode IN ('local_ledger')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_workstations_session_mode",
        "workstations",
        type_="check",
    )
    op.execute(
        sa.text(
            "UPDATE workstations SET session_mode = 'v2_local_ledger' "
            "WHERE session_mode = 'local_ledger'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE gaming_sessions SET source = 'v2_local_ledger' "
            "WHERE source = 'local_ledger'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE gaming_sessions SET source = 'v2_guest_local_ledger' "
            "WHERE source = 'guest_local_ledger'"
        )
    )
    op.alter_column(
        "workstations",
        "session_mode",
        existing_type=sa.String(length=32),
        server_default="v2_local_ledger",
    )
    op.create_check_constraint(
        "ck_workstations_session_mode",
        "workstations",
        "session_mode IN ('v1_server_owned', 'v2_local_ledger')",
    )
