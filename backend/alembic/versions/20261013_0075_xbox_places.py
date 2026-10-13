"""Add explicit equipment types without changing existing PC history."""

import sqlalchemy as sa
from alembic import op

revision = "20261013_0075"
down_revision = "20261011_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workstations", "tariffs"):
        op.add_column(
            table, sa.Column("equipment_type", sa.String(16), nullable=False, server_default="pc")
        )
        op.create_check_constraint(
            f"ck_{table}_equipment_type", table, "equipment_type IN ('pc', 'xbox')"
        )
    op.add_column(
        "guest_session_payments",
        sa.Column("equipment_type", sa.String(16), nullable=False, server_default="pc"),
    )
    op.add_column("guest_session_payments", sa.Column("zone_id", sa.String(128), nullable=True))
    op.add_column(
        "gaming_sessions", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "gaming_sessions",
        sa.Column("applied_payment_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.drop_constraint("ck_workstations_session_mode", "workstations", type_="check")
    op.create_check_constraint(
        "ck_workstations_session_mode",
        "workstations",
        "(equipment_type = 'pc' AND session_mode = 'local_ledger') OR "
        "(equipment_type = 'xbox' AND session_mode = 'server_owned')",
    )
    op.alter_column("workstations", "device_id", existing_type=sa.String(128), nullable=True)
    op.create_check_constraint(
        "ck_workstations_equipment_identity",
        "workstations",
        "(equipment_type = 'pc' AND device_id IS NOT NULL) OR "
        "(equipment_type = 'xbox' AND device_id IS NULL AND mac_address IS NULL "
        "AND installation_id IS NULL AND session_mode = 'server_owned')",
    )


def downgrade() -> None:
    # Xbox rows must be removed deliberately before dropping their type information.
    connection = op.get_bind()
    if (
        connection.execute(
            sa.text("SELECT 1 FROM workstations WHERE equipment_type = 'xbox' LIMIT 1")
        ).first()
        or connection.execute(
            sa.text("SELECT 1 FROM tariffs WHERE equipment_type = 'xbox' LIMIT 1")
        ).first()
        or connection.execute(
            sa.text("SELECT 1 FROM guest_session_payments WHERE equipment_type = 'xbox' LIMIT 1")
        ).first()
        or connection.execute(
            sa.text("SELECT 1 FROM gaming_sessions WHERE source = 'xbox' LIMIT 1")
        ).first()
    ):
        raise RuntimeError("Remove Xbox data explicitly before downgrade")
    op.drop_constraint("ck_workstations_session_mode", "workstations", type_="check")
    op.create_check_constraint(
        "ck_workstations_session_mode", "workstations", "session_mode = 'local_ledger'"
    )
    op.drop_column("guest_session_payments", "zone_id")
    op.drop_column("guest_session_payments", "equipment_type")
    op.drop_column("gaming_sessions", "applied_payment_ids")
    op.drop_column("gaming_sessions", "expires_at")
    op.drop_constraint("ck_workstations_equipment_identity", "workstations", type_="check")
    op.alter_column("workstations", "device_id", existing_type=sa.String(128), nullable=False)
    for table in ("workstations", "tariffs"):
        op.drop_constraint(f"ck_{table}_equipment_type", table, type_="check")
        op.drop_column(table, "equipment_type")
