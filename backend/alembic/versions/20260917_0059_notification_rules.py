"""Persist configurable remaining-time notification rules."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260917_0059"
down_revision = "20260917_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("threshold_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("play_sound", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sound", sa.String(length=16), nullable=False, server_default="standard"),
        sa.Column("custom_sound_path", sa.String(length=512), nullable=True),
        sa.Column("show_system_notification", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("threshold_minutes > 0", name="ck_notification_rules_threshold"),
        sa.CheckConstraint("sound IN ('standard', 'custom')", name="ck_notification_rules_sound"),
    )


def downgrade() -> None:
    op.drop_table("notification_rules")
