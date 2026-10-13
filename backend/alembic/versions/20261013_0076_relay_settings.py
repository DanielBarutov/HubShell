"""Persist optional DIY relay settings without changing PC or Xbox sessions."""

import sqlalchemy as sa
from alembic import op

revision = "20261013_0076"
down_revision = "20261013_0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workstations", sa.Column("relay_settings", sa.JSON(), nullable=True))
    op.create_check_constraint(
        "ck_workstations_relay_equipment",
        "workstations",
        "relay_settings IS NULL OR equipment_type = 'xbox'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workstations_relay_equipment", "workstations", type_="check")
    op.drop_column("workstations", "relay_settings")
