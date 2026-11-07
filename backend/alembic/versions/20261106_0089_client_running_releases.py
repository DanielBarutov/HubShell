"""Bind independent GUI release observations to the enrolled installation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261106_0089"
down_revision = "20261106_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_running_releases",
        sa.Column("device_id", sa.String(128), primary_key=True),
        sa.Column("workstation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.String(128), nullable=False),
        sa.Column("release_id", sa.String(128), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("client_running_releases")
