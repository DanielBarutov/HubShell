"""Replace legacy package UUIDs in balance history with tariff names."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260918_0061"
down_revision: str | None = "20260917_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE balance_operations AS operation
        SET reason = 'Покупка тарифа «' || tariff.name || '»'
        FROM client_entitlements AS entitlement
        JOIN tariffs AS tariff ON tariff.id = entitlement.tariff_id
        WHERE operation.reason = 'Package purchase ' || CAST(entitlement.id AS TEXT)
        """
    )


def downgrade() -> None:
    # The prior technical text cannot be reconstructed safely after renaming a tariff.
    pass
