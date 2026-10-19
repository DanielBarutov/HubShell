"""Keep fleet membership stable across the final all-PC poll and replacement."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261019_0085"
down_revision = "20261019_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workstation_deployment_freeze",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("deployment_id", UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("id = 1", name="single_workstation_freeze"),
    )


def downgrade() -> None:
    op.drop_table("workstation_deployment_freeze")
