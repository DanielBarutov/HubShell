import datetime
import uuid

import pytest

from gameclub_backend.modules.analytics.application.read_v2 import AnalyticsReadService
from gameclub_backend.modules.analytics.infrastructure.read_memory import (
    InMemoryAnalyticsReadRepository,
)
from gameclub_backend.modules.analytics.read_v2 import (
    AnalyticsFilter,
    AnalyticsReadState,
    ProductAdjustmentFact,
    ProductSaleFact,
    aggregate_product_metrics,
)
from gameclub_backend.modules.auth.domain import Principal, SubjectType

UTC = datetime.UTC


def filters() -> AnalyticsFilter:
    return AnalyticsFilter(
        start_at=datetime.datetime(2026, 9, 20, tzinfo=UTC),
        end_at=datetime.datetime(2026, 9, 22, tzinfo=UTC),
    )


def sale(
    *, session_id: uuid.UUID | None, quantity: int = 2, source_id: str = "sale-1"
) -> ProductSaleFact:
    return ProductSaleFact(
        source_id=source_id,
        product_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        product_name="Cola",
        category_key="drinks",
        quantity=quantity,
        revenue_cents=quantity * 250,
        cost_cents=quantity * 100,
        occurred_at=datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
        status="completed",
        session_id=session_id,
        payment_method_key="cash",
        operator_key="operator-1",
    )


def test_product_metrics_use_snapshots_and_explicit_attach_coverage() -> None:
    """Проверяет snapshots товаров и явное состояние покрытия attach rate."""
    session_id = uuid.uuid4()
    metrics = aggregate_product_metrics(
        (sale(session_id=session_id), sale(session_id=None, quantity=1, source_id="sale-2")),
        (
            ProductAdjustmentFact(
                source_id="return-1",
                adjustment_type="return",
                amount_cents=250,
                quantity=1,
                occurred_at=datetime.datetime(2026, 9, 20, 11, tzinfo=UTC),
                status="confirmed",
            ),
        ),
        filters(),
    )

    assert metrics.sales_count == 2
    assert metrics.units == 3
    assert metrics.gross_revenue_cents == 750
    assert metrics.cost_cents == 300
    assert metrics.gross_profit_cents == 450
    assert metrics.returns_cents == 250
    assert metrics.attach_rate_coverage == 1 / 2
    assert metrics.attach_rate_state is AnalyticsReadState.PARTIAL


@pytest.mark.asyncio
async def test_dashboard_has_versioned_blocks_filters_comparison_and_metric_info() -> None:
    """Проверяет блоки v2, фильтры, сравнение и паспорт метрики."""
    service = AnalyticsReadService(
        InMemoryAnalyticsReadRepository(product_sales=(sale(session_id=uuid.uuid4()),))
    )
    report = await service.dashboard(
        filters(),
        now=datetime.datetime(2026, 9, 21, 12, tzinfo=UTC),
    )

    assert report.api_version == "v2"
    assert report.comparison.is_partial is True
    assert report.filters.payment_method_key is None
    assert report.blocks["products"].metrics["gross_profit_cents"].metric_info.formula
    assert (
        report.blocks["products"].metrics["returns_cents"].state is AnalyticsReadState.NOT_AVAILABLE
    )
    assert report.blocks["products"].rows[0].label == "Cola"


@pytest.mark.asyncio
async def test_drill_down_requires_operator_permission_and_masks_pii() -> None:
    """Проверяет право оператора и маскирование персональных данных."""
    service = AnalyticsReadService(
        InMemoryAnalyticsReadRepository(product_sales=(sale(session_id=uuid.uuid4()),))
    )
    with pytest.raises(PermissionError):
        await service.drill_down(
            filters(), Principal("client-1", SubjectType.CLIENT, frozenset(), frozenset())
        )

    result = await service.drill_down(
        filters(),
        Principal(
            "operator-1",
            SubjectType.OPERATOR,
            frozenset({"operator"}),
            frozenset({"analytics.read", "analytics.drill_down"}),
        ),
    )
    assert result.items[0].source_id == "sale-1"
    assert result.items[0].operator_key == "operator-1"
    assert result.items[0].client_id is None
