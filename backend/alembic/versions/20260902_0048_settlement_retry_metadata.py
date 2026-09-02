"""Persist per-record settlement retry scheduling and errors."""

import sqlalchemy as sa
from alembic import op

revision = "20260902_0048"
down_revision = "20260902_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("guest_session_payments", "product_sales"):
        op.add_column(
            table_name,
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        )
        op.add_column(
            table_name,
            sa.Column(
                "next_attempt_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_index(
            f"ix_{table_name}_next_attempt_at",
            table_name,
            ["next_attempt_at"],
        )
    op.add_column(
        "guest_session_payments",
        sa.Column("settlement_error", sa.String(length=1_000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("guest_session_payments", "settlement_error")
    for table_name in ("product_sales", "guest_session_payments"):
        op.drop_index(f"ix_{table_name}_next_attempt_at", table_name=table_name)
        op.drop_column(table_name, "next_attempt_at")
        op.drop_column(table_name, "attempts")
