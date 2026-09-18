"""Add client groups, default assignment, and bounded negative balance."""

import sqlalchemy as sa
from alembic import op

revision = "20260917_0056"
down_revision = "20260917_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_groups",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("allow_negative_balance", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("negative_balance_limit_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "negative_balance_limit_cents >= 0",
            name="ck_client_groups_negative_limit",
        ),
    )
    op.add_column("clients", sa.Column("client_group_id", sa.String(length=128), nullable=True))
    op.create_index("ix_clients_client_group_id", "clients", ["client_group_id"])
    op.execute(
        sa.text(
            "INSERT INTO client_groups "
            "(id, name, allow_negative_balance, negative_balance_limit_cents, active, is_default, updated_at) "
            "VALUES ('regular', 'Обычные клиенты', FALSE, 0, TRUE, TRUE, CURRENT_TIMESTAMP)"
        )
    )
    op.execute(sa.text("UPDATE clients SET client_group_id = 'regular' WHERE client_group_id IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_clients_client_group_id", table_name="clients")
    op.drop_column("clients", "client_group_id")
    op.drop_table("client_groups")
