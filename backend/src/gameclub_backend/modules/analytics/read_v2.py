from __future__ import annotations

import dataclasses
import datetime
import enum
import typing
import uuid

from gameclub_backend.modules.auth.domain import Principal

CONFIRMED_STATUSES = frozenset({"completed", "confirmed"})


class AnalyticsReadState(enum.StrEnum):
    AVAILABLE = "available"
    EMPTY = "empty"
    PARTIAL = "partial"
    NOT_AVAILABLE = "not_available"
    NOT_CALCULATED = "not_calculated"
    ERROR = "error"
    PERMISSION_DENIED = "permission_denied"


@dataclasses.dataclass(frozen=True, slots=True)
class AnalyticsFilter:
    start_at: datetime.datetime
    end_at: datetime.datetime
    zone_key: str | None = None
    workstation_key: str | None = None
    tariff_key: str | None = None
    client_group_key: str | None = None
    payment_method_key: str | None = None
    operation_type: str | None = None
    category_key: str | None = None
    product_key: str | None = None
    operator_key: str | None = None

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("Analytics period requires aware timestamps")
        start_at = self.start_at.astimezone(datetime.UTC)
        end_at = self.end_at.astimezone(datetime.UTC)
        if start_at >= end_at:
            raise ValueError("Analytics period must start before it ends")
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)

    def matches(self, fact: ProductSaleFact | ProductAdjustmentFact) -> bool:
        if not self.start_at <= fact.occurred_at < self.end_at:
            return False
        dimensions = (
            (self.zone_key, fact.zone_key),
            (self.workstation_key, fact.workstation_key),
            (self.tariff_key, fact.tariff_key),
            (self.client_group_key, fact.client_group_key),
            (self.payment_method_key, fact.payment_method_key),
            (self.operation_type, fact.operation_type),
            (self.category_key, fact.category_key),
            (self.product_key, str(fact.product_id) if fact.product_id else None),
            (self.operator_key, fact.operator_key),
        )
        return all(expected is None or expected == actual for expected, actual in dimensions)


@dataclasses.dataclass(frozen=True, slots=True)
class ProductSaleFact:
    source_id: str
    product_id: uuid.UUID
    product_name: str
    category_key: str
    quantity: int
    revenue_cents: int
    cost_cents: int
    occurred_at: datetime.datetime
    status: str
    session_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    payment_method_key: str | None = None
    operation_type: str = "sale"
    zone_key: str | None = None
    workstation_key: str | None = None
    tariff_key: str | None = None
    client_group_key: str | None = None
    operator_key: str | None = None
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.product_name.strip():
            raise ValueError("Product sale source and name are required")
        if self.quantity <= 0 or self.revenue_cents < 0 or self.cost_cents < 0:
            raise ValueError("Product sale quantities and money must be non-negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("Product sale timestamp requires timezone")
        object.__setattr__(self, "source_id", self.source_id.strip())
        object.__setattr__(self, "status", self.status.strip().lower())
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(datetime.UTC))


@dataclasses.dataclass(frozen=True, slots=True)
class ProductAdjustmentFact:
    source_id: str
    adjustment_type: str
    amount_cents: int
    quantity: int
    occurred_at: datetime.datetime
    status: str
    product_id: uuid.UUID | None = None
    category_key: str | None = None
    session_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    payment_method_key: str | None = None
    operation_type: str = "adjustment"
    zone_key: str | None = None
    workstation_key: str | None = None
    tariff_key: str | None = None
    client_group_key: str | None = None
    operator_key: str | None = None
    reason: str | None = None
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or self.adjustment_type not in {"return", "adjustment"}:
            raise ValueError("Adjustment source and type are required")
        if self.amount_cents < 0 or self.quantity < 0:
            raise ValueError("Adjustment quantity and money must be non-negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("Adjustment timestamp requires timezone")
        object.__setattr__(self, "source_id", self.source_id.strip())
        object.__setattr__(self, "status", self.status.strip().lower())
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(datetime.UTC))


@dataclasses.dataclass(frozen=True, slots=True)
class ProductMetrics:
    sales_count: int = 0
    units: int = 0
    gross_revenue_cents: int = 0
    cost_cents: int = 0
    returns_cents: int | None = None
    adjustments_cents: int | None = None
    attachable_sales_count: int = 0
    linked_sales_count: int = 0
    attach_rate_coverage: float = 0.0
    attach_rate: float | None = None
    attach_rate_state: AnalyticsReadState = AnalyticsReadState.NOT_CALCULATED
    rows: tuple[ProductMetricRow, ...] = ()

    @property
    def gross_profit_cents(self) -> int:
        return self.gross_revenue_cents - self.cost_cents

    @property
    def net_revenue_cents(self) -> int | None:
        if self.returns_cents is None or self.adjustments_cents is None:
            return None
        return self.gross_revenue_cents - self.returns_cents + self.adjustments_cents

    @property
    def margin_bps(self) -> int | None:
        if not self.gross_revenue_cents:
            return None
        return round(self.gross_profit_cents * 10_000 / self.gross_revenue_cents)


@dataclasses.dataclass(frozen=True, slots=True)
class MetricInfo:
    key: str
    label: str
    description: str
    formula: str
    source: str


@dataclasses.dataclass(frozen=True, slots=True)
class ProductMetricRow:
    key: str
    label: str
    units: int
    revenue_cents: int
    cost_cents: int
    gross_profit_cents: int
    margin_bps: int | None
    share_bps: int


@dataclasses.dataclass(frozen=True, slots=True)
class MetricComparison:
    current: int | float | None
    previous: int | float | None
    delta: int | float | None
    change_percent: float | None
    change_percentage_points: float | None
    state: AnalyticsReadState


@dataclasses.dataclass(frozen=True, slots=True)
class ReadMetric:
    key: str
    value: int | float | None
    state: AnalyticsReadState
    metric_info: MetricInfo
    comparison: MetricComparison | None = None
    coverage: float | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class DashboardBlock:
    key: str
    state: AnalyticsReadState
    metrics: dict[str, ReadMetric]
    rows: tuple[ProductMetricRow, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class PeriodComparison:
    start_at: datetime.datetime
    end_at: datetime.datetime
    is_partial: bool


@dataclasses.dataclass(frozen=True, slots=True)
class AnalyticsDashboardReport:
    api_version: str
    timezone: str
    period: AnalyticsFilter
    filters: AnalyticsFilter
    comparison: PeriodComparison
    blocks: dict[str, DashboardBlock]


@dataclasses.dataclass(frozen=True, slots=True)
class DrillDownItem:
    source_id: str
    kind: str
    occurred_at: datetime.datetime
    amount_cents: int
    quantity: int
    product_id: uuid.UUID | None
    product_name: str | None
    operator_key: str | None
    reason: str | None
    source_reference: str | None
    client_id: uuid.UUID | None


@dataclasses.dataclass(frozen=True, slots=True)
class DrillDownResult:
    state: AnalyticsReadState
    items: tuple[DrillDownItem, ...]


class AnalyticsReadRepository(typing.Protocol):
    async def snapshot(
        self,
        filters: AnalyticsFilter | None = None,
    ) -> tuple[tuple[ProductSaleFact, ...], tuple[ProductAdjustmentFact, ...] | None]: ...


_PRODUCT_INFO = {
    "sales_count": MetricInfo(
        "sales_count",
        "Продажи",
        "Число завершённых товарных продаж.",
        "count(ProductSale)",
        "ProductSale snapshot",
    ),
    "units": MetricInfo(
        "units",
        "Единицы",
        "Количество проданных единиц.",
        "sum(ProductSale.quantity)",
        "ProductSale snapshot",
    ),
    "gross_revenue_cents": MetricInfo(
        "gross_revenue_cents",
        "Товарная выручка",
        "Выручка завершённых продаж до возвратов.",
        "sum(ProductSale.revenue_cents)",
        "ProductSale snapshot",
    ),
    "cost_cents": MetricInfo(
        "cost_cents",
        "Себестоимость",
        "Историческая себестоимость на момент продажи.",
        "sum(ProductSale.cost_cents)",
        "ProductSale snapshot",
    ),
    "gross_profit_cents": MetricInfo(
        "gross_profit_cents",
        "Валовая прибыль",
        "Товарная выручка минус историческая себестоимость.",
        "gross_revenue - cost",
        "ProductSale snapshot",
    ),
    "margin_bps": MetricInfo(
        "margin_bps",
        "Маржинальность",
        "Валовая прибыль как доля товарной выручки.",
        "gross_profit / gross_revenue × 10000",
        "ProductSale snapshot",
    ),
    "returns_cents": MetricInfo(
        "returns_cents",
        "Возвраты",
        "Отдельно подтверждённые возвраты товаров.",
        "sum(Adjustment[type=return])",
        "Adjustment read port",
    ),
    "adjustments_cents": MetricInfo(
        "adjustments_cents",
        "Корректировки",
        "Отдельные подтверждённые операторские корректировки.",
        "sum(Adjustment[type=adjustment])",
        "Adjustment read port",
    ),
    "attach_rate": MetricInfo(
        "attach_rate",
        "Attach rate",
        "Доля сессий со связанной товарной продажей.",
        "sessions_with_product / sessions",
        "ProductSale.session_id",
    ),
    "attach_rate_coverage": MetricInfo(
        "attach_rate_coverage",
        "Attach coverage",
        "Доля товарных продаж с известной сессией.",
        "sales_with_session_id / sales",
        "ProductSale.session_id",
    ),
}


def _confirmed(status: str) -> bool:
    return status.strip().lower() in CONFIRMED_STATUSES


def aggregate_product_metrics(
    sales: typing.Iterable[ProductSaleFact],
    adjustments: typing.Iterable[ProductAdjustmentFact] | None,
    filters: AnalyticsFilter,
) -> ProductMetrics:
    seen: set[str] = set()
    selected_sales: list[ProductSaleFact] = []
    for item in sales:
        if not _confirmed(item.status) or not filters.matches(item) or item.source_id in seen:
            continue
        seen.add(item.source_id)
        selected_sales.append(item)
    selected_adjustments = [
        item for item in (adjustments or ()) if _confirmed(item.status) and filters.matches(item)
    ]
    attachable = len(selected_sales)
    linked = sum(item.session_id is not None for item in selected_sales)
    coverage = linked / attachable if attachable else 0.0
    attach_state = (
        AnalyticsReadState.NOT_CALCULATED
        if not attachable
        else (AnalyticsReadState.AVAILABLE if coverage == 1 else AnalyticsReadState.PARTIAL)
    )
    returns = sum(
        item.amount_cents for item in selected_adjustments if item.adjustment_type == "return"
    )
    corrections = sum(
        item.amount_cents for item in selected_adjustments if item.adjustment_type == "adjustment"
    )
    grouped: dict[str, list[int]] = {}
    for item in selected_sales:
        values = grouped.setdefault(str(item.product_id), [0, 0, 0])
        values[0] += item.quantity
        values[1] += item.revenue_cents
        values[2] += item.cost_cents
    total_revenue = sum(values[1] for values in grouped.values())
    rows = tuple(
        ProductMetricRow(
            key=key,
            label=next(item.product_name for item in selected_sales if str(item.product_id) == key),
            units=values[0],
            revenue_cents=values[1],
            cost_cents=values[2],
            gross_profit_cents=values[1] - values[2],
            margin_bps=round((values[1] - values[2]) * 10_000 / values[1]) if values[1] else None,
            share_bps=round(values[1] * 10_000 / total_revenue) if total_revenue else 0,
        )
        for key, values in sorted(grouped.items(), key=lambda pair: (-pair[1][1], pair[0]))
    )
    return ProductMetrics(
        sales_count=len(selected_sales),
        units=sum(item.quantity for item in selected_sales),
        gross_revenue_cents=sum(item.revenue_cents for item in selected_sales),
        cost_cents=sum(item.cost_cents for item in selected_sales),
        returns_cents=returns if adjustments is not None else None,
        adjustments_cents=corrections if adjustments is not None else None,
        attachable_sales_count=attachable,
        linked_sales_count=linked,
        attach_rate_coverage=coverage,
        attach_rate=None,
        attach_rate_state=attach_state,
        rows=rows,
    )


def _compare(current: int | float | None, previous: int | float | None) -> MetricComparison:
    if current is None or previous is None:
        return MetricComparison(
            current, previous, None, None, None, AnalyticsReadState.NOT_AVAILABLE
        )
    delta = current - previous
    if previous == 0:
        return MetricComparison(
            current, previous, delta, None, None, AnalyticsReadState.NOT_AVAILABLE
        )
    return MetricComparison(
        current,
        previous,
        delta,
        round(delta / previous * 100, 2),
        None,
        AnalyticsReadState.AVAILABLE,
    )


def _metric(
    key: str,
    value: int | float | None,
    state: AnalyticsReadState,
    previous: int | float | None = None,
    coverage: float | None = None,
) -> ReadMetric:
    comparison = _compare(value, previous) if value is not None or previous is not None else None
    return ReadMetric(key, value, state, _PRODUCT_INFO[key], comparison, coverage)


class AnalyticsReadService:
    def __init__(self, repository: AnalyticsReadRepository) -> None:
        self._repository = repository

    async def dashboard(
        self,
        filters: AnalyticsFilter,
        now: datetime.datetime | None = None,
    ) -> AnalyticsDashboardReport:
        observed_at = now or datetime.datetime.now(datetime.UTC)
        duration = filters.end_at - filters.start_at
        comparison = PeriodComparison(
            start_at=filters.start_at - duration,
            end_at=filters.start_at,
            is_partial=filters.end_at > observed_at.astimezone(datetime.UTC),
        )
        try:
            sales, adjustments = await self._repository.snapshot(filters)
        except Exception:
            blocks = {
                key: DashboardBlock(key, AnalyticsReadState.NOT_CALCULATED, {})
                for key in (
                    "finance",
                    "occupancy",
                    "clients",
                    "workstations",
                    "tariffs",
                    "deposits",
                )
            }
            blocks["products"] = DashboardBlock("products", AnalyticsReadState.ERROR, {})
            return AnalyticsDashboardReport(
                "v2", "Europe/Moscow", filters, filters, comparison, blocks
            )
        previous_filters = dataclasses.replace(
            filters,
            start_at=comparison.start_at,
            end_at=comparison.end_at,
        )
        current = aggregate_product_metrics(sales, adjustments, filters)
        previous = aggregate_product_metrics(sales, adjustments, previous_filters)
        product_state = (
            AnalyticsReadState.EMPTY if current.sales_count == 0 else AnalyticsReadState.AVAILABLE
        )
        if current.attach_rate_state is AnalyticsReadState.PARTIAL:
            product_state = AnalyticsReadState.PARTIAL
        metrics = {
            "sales_count": _metric(
                "sales_count", current.sales_count, product_state, previous.sales_count
            ),
            "units": _metric("units", current.units, product_state, previous.units),
            "gross_revenue_cents": _metric(
                "gross_revenue_cents",
                current.gross_revenue_cents,
                product_state,
                previous.gross_revenue_cents,
            ),
            "cost_cents": _metric(
                "cost_cents", current.cost_cents, product_state, previous.cost_cents
            ),
            "gross_profit_cents": _metric(
                "gross_profit_cents",
                current.gross_profit_cents,
                product_state,
                previous.gross_profit_cents,
            ),
            "margin_bps": _metric(
                "margin_bps", current.margin_bps, product_state, previous.margin_bps
            ),
            "returns_cents": _metric(
                "returns_cents",
                current.returns_cents,
                AnalyticsReadState.AVAILABLE
                if adjustments is not None
                else AnalyticsReadState.NOT_AVAILABLE,
                previous.returns_cents,
            ),
            "adjustments_cents": _metric(
                "adjustments_cents",
                current.adjustments_cents,
                AnalyticsReadState.AVAILABLE
                if adjustments is not None
                else AnalyticsReadState.NOT_AVAILABLE,
                previous.adjustments_cents,
            ),
            "attach_rate": _metric(
                "attach_rate",
                current.attach_rate,
                AnalyticsReadState.NOT_CALCULATED,
                previous.attach_rate,
            ),
            "attach_rate_coverage": _metric(
                "attach_rate_coverage",
                current.attach_rate_coverage,
                current.attach_rate_state,
                previous.attach_rate_coverage,
                current.attach_rate_coverage,
            ),
        }
        blocks = {
            key: DashboardBlock(key, AnalyticsReadState.NOT_CALCULATED, {})
            for key in ("finance", "occupancy", "clients", "workstations", "tariffs", "deposits")
        }
        blocks["products"] = DashboardBlock("products", product_state, metrics, current.rows)
        return AnalyticsDashboardReport("v2", "Europe/Moscow", filters, filters, comparison, blocks)

    async def drill_down(
        self, filters: AnalyticsFilter, principal: Principal, limit: int = 100
    ) -> DrillDownResult:
        if not principal.can("analytics.drill_down"):
            raise PermissionError("analytics.drill_down permission required")
        sales, adjustments = await self._repository.snapshot(filters)
        items: list[DrillDownItem] = []
        facts: tuple[ProductSaleFact | ProductAdjustmentFact, ...] = (
            *sales,
            *(adjustments or ()),
        )
        for item in facts:
            if not filters.matches(item) or not _confirmed(item.status):
                continue
            if isinstance(item, ProductSaleFact):
                items.append(
                    DrillDownItem(
                        item.source_id,
                        "sale",
                        item.occurred_at,
                        item.revenue_cents,
                        item.quantity,
                        item.product_id,
                        item.product_name,
                        item.operator_key,
                        None,
                        item.source_reference,
                        None,
                    )
                )
            else:
                items.append(
                    DrillDownItem(
                        item.source_id,
                        item.adjustment_type,
                        item.occurred_at,
                        item.amount_cents,
                        item.quantity,
                        item.product_id,
                        None,
                        item.operator_key,
                        item.reason,
                        item.source_reference,
                        None,
                    )
                )
        items.sort(key=lambda value: value.occurred_at, reverse=True)
        return DrillDownResult(
            AnalyticsReadState.AVAILABLE if items else AnalyticsReadState.EMPTY,
            tuple(items[: max(1, min(limit, 500))]),
        )
