import datetime
import uuid

from gameclub_backend.modules.analytics.infrastructure.read_postgres import (
    build_product_read_snapshot,
)

UTC = datetime.UTC


def test_product_read_snapshot_preserves_sale_snapshots_and_separates_adjustments() -> None:
    """Проверяет сохранение snapshots продажи и отдельные корректировки."""
    product_id = uuid.uuid4()
    sales, adjustments = build_product_read_snapshot(
        sale_rows=[
            {
                "id": uuid.uuid4(),
                "product_id": product_id,
                "product_name": "Cola at sale time",
                "product_category": "drinks",
                "quantity": 2,
                "total_price_cents": 500,
                "total_cost_price_cents": 180,
                "created_at": datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
                "status": "completed",
                "session_id": uuid.uuid4(),
                "client_id": uuid.uuid4(),
                "payment_method": "cash",
                "sold_by": "operator-1",
            }
        ],
        adjustment_rows=[
            {
                "id": uuid.uuid4(),
                "adjustment_type": "return",
                "amount_cents": 250,
                "quantity": 1,
                "created_at": datetime.datetime(2026, 9, 20, 11, tzinfo=UTC),
                "status": "confirmed",
                "product_id": product_id,
                "reason": "damaged",
                "actor_id": "operator-1",
            }
        ],
    )

    assert sales[0].product_name == "Cola at sale time"
    assert sales[0].cost_cents == 180
    assert sales[0].session_id is not None
    assert adjustments is not None
    assert adjustments[0].adjustment_type == "return"
    assert adjustments[0].reason == "damaged"
