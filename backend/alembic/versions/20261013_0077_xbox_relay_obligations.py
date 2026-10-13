"""Persist Xbox OFF obligations atomically with session lifecycle."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261013_0077"
down_revision = "20261013_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "xbox_relay_obligations",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("workstation_id", sa.Uuid(), nullable=False),
        sa.Column("settings", postgresql.JSONB(), nullable=False),
        sa.Column("pending", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_xbox_relay_obligations_workstation_id", "xbox_relay_obligations", ["workstation_id"]
    )
    op.create_index("ix_xbox_relay_obligations_pending", "xbox_relay_obligations", ["pending"])
    # Existing active Xbox sessions must also be switched off after this upgrade.
    op.execute("""
        INSERT INTO xbox_relay_obligations (session_id, workstation_id, settings, pending)
        SELECT s.id, s.workstation_id, w.relay_settings::jsonb, false
        FROM gaming_sessions s JOIN workstations w ON w.id = s.workstation_id
        WHERE s.source = 'xbox' AND s.status = 'active' AND w.relay_settings IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table("xbox_relay_obligations")
