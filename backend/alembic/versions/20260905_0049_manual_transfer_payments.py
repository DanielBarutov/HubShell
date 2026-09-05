"""Allow confirmed manual transfer settlements for sales and guest sessions."""

import typing

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0049"
down_revision: str | None = "20260902_0048"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "guest_session_payments",
        "cash_shift_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO payment_methods
                (id, key, name, active, sort_order, created_at, updated_at)
            VALUES
                ('00000000-0000-0000-0000-000000000003', 'transfer',
                 'Перевод', true, 30, now(), now())
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM payment_methods WHERE id = '00000000-0000-0000-0000-000000000003'"
        )
    )
    op.alter_column(
        "guest_session_payments",
        "cash_shift_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
