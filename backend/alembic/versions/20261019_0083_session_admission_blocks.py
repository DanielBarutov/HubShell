"""Durable Sessions admission barrier for coordinated client deployment."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261019_0083"
down_revision = "20261017_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_admission_blocks",
        sa.Column("workstation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("deployment_id", UUID(as_uuid=True), nullable=False),
    )
    op.create_index(
        "ix_session_admission_blocks_deployment_id", "session_admission_blocks", ["deployment_id"]
    )


def downgrade() -> None:
    op.drop_table("session_admission_blocks")
