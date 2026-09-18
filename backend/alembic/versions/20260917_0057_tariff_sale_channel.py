"""Add an explicit operator/self-service tariff sale channel."""

import sqlalchemy as sa
from alembic import op

revision = "20260917_0057"
down_revision = "20260917_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tariffs",
        sa.Column("sale_channel", sa.String(length=16), nullable=False, server_default="both"),
    )
    op.create_check_constraint(
        "ck_tariffs_sale_channel",
        "tariffs",
        "sale_channel IN ('operator', 'self_service', 'both')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tariffs_sale_channel", "tariffs", type_="check")
    op.drop_column("tariffs", "sale_channel")
