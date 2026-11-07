"""Persist approved client release policies independently from device jobs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261106_0088"
down_revision = "20261106_0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_release_policies",
        sa.Column("operation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("client_release_policies")
