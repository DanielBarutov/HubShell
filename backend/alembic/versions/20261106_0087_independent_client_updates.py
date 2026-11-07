"""Allow independent PC updates while retaining the legacy fleet constraint."""

import sqlalchemy as sa
from alembic import op

revision = "20261106_0087"
down_revision = "20261019_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_one_unfinished_client_deployment", table_name="client_update_deployments")
    op.create_index(
        "uq_one_unfinished_client_deployment",
        "client_update_deployments",
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text(
            "phase <> 'completed' AND COALESCE(payload->>'independent', 'false') <> 'true'"
        ),
    )


def downgrade() -> None:
    # Refuse downgrade with multiple active jobs instead of deleting update state.
    op.drop_index("uq_one_unfinished_client_deployment", table_name="client_update_deployments")
    op.create_index(
        "uq_one_unfinished_client_deployment",
        "client_update_deployments",
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text("phase <> 'completed'"),
    )
