"""Allow transfer requests to bind the destination on the new workstation."""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260915_0054"
down_revision = "20260906_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "session_transfer_offers",
        "target_workstation_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "session_transfer_offers",
        "target_workstation_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
