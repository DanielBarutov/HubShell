"""Hash and bind updater credentials independently from GUI device credentials."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261019_0086"
down_revision = "20261019_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_updater_credentials",
        sa.Column("device_id", sa.String(128), primary_key=True),
        sa.Column("id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("workstation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.String(128), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("client_updater_credentials")
