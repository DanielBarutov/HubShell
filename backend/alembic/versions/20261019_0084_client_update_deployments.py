"""Persist coordinated fleet deployment rounds, author and device outcomes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261019_0084"
down_revision = "20261019_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_update_deployments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("operation_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index(
        "uq_one_unfinished_client_deployment",
        "client_update_deployments",
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text("phase <> 'completed'"),
    )


def downgrade() -> None:
    op.drop_table("client_update_deployments")
