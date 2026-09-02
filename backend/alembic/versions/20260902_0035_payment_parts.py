"""Persist payment parts for balance operations and product sales."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_0035"
down_revision = "20260902_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    default = sa.text("'[]'::jsonb")
    for table_name in ("balance_operations", "product_sales"):
        op.add_column(
            table_name,
            sa.Column(
                "payment_parts",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=default,
            ),
        )
        op.alter_column(table_name, "payment_parts", server_default=None)


def downgrade() -> None:
    for table_name in ("product_sales", "balance_operations"):
        op.drop_column(table_name, "payment_parts")
