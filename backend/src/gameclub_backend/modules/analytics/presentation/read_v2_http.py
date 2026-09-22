from __future__ import annotations

import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from gameclub_backend.modules.analytics.application.read_v2 import AnalyticsReadService
from gameclub_backend.modules.analytics.read_v2 import (
    AnalyticsDashboardReport,
    AnalyticsFilter,
    AnalyticsReadState,
    DashboardBlock,
    DrillDownResult,
    MetricComparison,
    MetricInfo,
    ProductMetricRow,
    ReadMetric,
)
from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.presentation.http.auth import require_permissions

Reader = typing.Annotated[Principal, Depends(require_permissions("analytics.read"))]
DrillDownReader = typing.Annotated[Principal, Depends(require_permissions("analytics.drill_down"))]
QueryDatetime = typing.Annotated[datetime.datetime, Query()]


class V2MetricInfoResponse(BaseModel):
    key: str
    label: str
    description: str
    formula: str
    source: str

    @classmethod
    def from_domain(cls, value: MetricInfo) -> V2MetricInfoResponse:
        return cls.model_validate(value, from_attributes=True)


class V2ComparisonResponse(BaseModel):
    current: int | float | None
    previous: int | float | None
    delta: int | float | None
    change_percent: float | None
    change_percentage_points: float | None
    state: AnalyticsReadState

    @classmethod
    def from_domain(cls, value: MetricComparison) -> V2ComparisonResponse:
        return cls.model_validate(value, from_attributes=True)


class V2MetricResponse(BaseModel):
    key: str
    value: int | float | None
    state: AnalyticsReadState
    metric_info: V2MetricInfoResponse
    comparison: V2ComparisonResponse | None
    coverage: float | None

    @classmethod
    def from_domain(cls, value: ReadMetric) -> V2MetricResponse:
        return cls(
            key=value.key,
            value=value.value,
            state=value.state,
            metric_info=V2MetricInfoResponse.from_domain(value.metric_info),
            comparison=(
                V2ComparisonResponse.from_domain(value.comparison) if value.comparison else None
            ),
            coverage=value.coverage,
        )


class V2BlockResponse(BaseModel):
    key: str
    state: AnalyticsReadState
    metrics: dict[str, V2MetricResponse]
    rows: list[dict[str, object]]

    @classmethod
    def from_domain(cls, value: DashboardBlock) -> V2BlockResponse:
        return cls(
            key=value.key,
            state=value.state,
            metrics={
                key: V2MetricResponse.from_domain(metric) for key, metric in value.metrics.items()
            },
            rows=[ProductMetricRowResponse.from_domain(row).model_dump() for row in value.rows],
        )


class ProductMetricRowResponse(BaseModel):
    key: str
    label: str
    units: int
    revenue_cents: int
    cost_cents: int
    gross_profit_cents: int
    margin_bps: int | None
    share_bps: int

    @classmethod
    def from_domain(cls, value: ProductMetricRow) -> ProductMetricRowResponse:
        return cls.model_validate(value, from_attributes=True)


class V2FilterResponse(BaseModel):
    start_at: datetime.datetime
    end_at: datetime.datetime
    zone_key: str | None
    workstation_key: str | None
    tariff_key: str | None
    client_group_key: str | None
    payment_method_key: str | None
    operation_type: str | None
    category_key: str | None
    product_key: str | None
    operator_key: str | None

    @classmethod
    def from_domain(cls, value: AnalyticsFilter) -> V2FilterResponse:
        return cls.model_validate(value, from_attributes=True)


class V2PeriodComparisonResponse(BaseModel):
    start_at: datetime.datetime
    end_at: datetime.datetime
    is_partial: bool


class V2DashboardResponse(BaseModel):
    api_version: str
    timezone: str
    period: V2FilterResponse
    filters: V2FilterResponse
    comparison: V2PeriodComparisonResponse
    blocks: dict[str, V2BlockResponse]

    @classmethod
    def from_domain(cls, value: AnalyticsDashboardReport) -> V2DashboardResponse:
        return cls(
            api_version=value.api_version,
            timezone=value.timezone,
            period=V2FilterResponse.from_domain(value.period),
            filters=V2FilterResponse.from_domain(value.filters),
            comparison=V2PeriodComparisonResponse.model_validate(
                value.comparison, from_attributes=True
            ),
            blocks={key: V2BlockResponse.from_domain(block) for key, block in value.blocks.items()},
        )


class V2DrillDownItemResponse(BaseModel):
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


class V2DrillDownResponse(BaseModel):
    state: AnalyticsReadState
    items: list[V2DrillDownItemResponse]

    @classmethod
    def from_domain(cls, value: DrillDownResult) -> V2DrillDownResponse:
        return cls(
            state=value.state,
            items=[
                V2DrillDownItemResponse.model_validate(item, from_attributes=True)
                for item in value.items
            ],
        )


def _filters(
    start_at: datetime.datetime,
    end_at: datetime.datetime,
    zone_key: str | None,
    workstation_key: str | None,
    tariff_key: str | None,
    client_group_key: str | None,
    payment_method_key: str | None,
    operation_type: str | None,
    category_key: str | None,
    product_key: str | None,
    operator_key: str | None,
) -> AnalyticsFilter:
    try:
        return AnalyticsFilter(
            start_at=start_at,
            end_at=end_at,
            zone_key=zone_key,
            workstation_key=workstation_key,
            tariff_key=tariff_key,
            client_group_key=client_group_key,
            payment_method_key=payment_method_key,
            operation_type=operation_type,
            category_key=category_key,
            product_key=product_key,
            operator_key=operator_key,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def create_v2_read_router(service: AnalyticsReadService) -> APIRouter:
    router = APIRouter(prefix="/api/v2/analytics", tags=["analytics-v2"])

    @router.get("/dashboard", response_model=V2DashboardResponse)
    async def dashboard(
        principal: Reader,
        start_at: QueryDatetime,
        end_at: QueryDatetime,
        zone_key: str | None = Query(default=None),
        workstation_key: str | None = Query(default=None),
        tariff_key: str | None = Query(default=None),
        client_group_key: str | None = Query(default=None),
        payment_method_key: str | None = Query(default=None),
        operation_type: str | None = Query(default=None),
        category_key: str | None = Query(default=None),
        product_key: str | None = Query(default=None),
        operator_key: str | None = Query(default=None),
    ) -> V2DashboardResponse:
        del principal
        selected = _filters(
            start_at,
            end_at,
            zone_key,
            workstation_key,
            tariff_key,
            client_group_key,
            payment_method_key,
            operation_type,
            category_key,
            product_key,
            operator_key,
        )
        return V2DashboardResponse.from_domain(await service.dashboard(selected))

    @router.get("/drill-down", response_model=V2DrillDownResponse)
    async def drill_down(
        principal: DrillDownReader,
        start_at: QueryDatetime,
        end_at: QueryDatetime,
        limit: int = Query(default=100, ge=1, le=500),
        zone_key: str | None = Query(default=None),
        workstation_key: str | None = Query(default=None),
        tariff_key: str | None = Query(default=None),
        client_group_key: str | None = Query(default=None),
        payment_method_key: str | None = Query(default=None),
        operation_type: str | None = Query(default=None),
        category_key: str | None = Query(default=None),
        product_key: str | None = Query(default=None),
        operator_key: str | None = Query(default=None),
    ) -> V2DrillDownResponse:
        selected = _filters(
            start_at,
            end_at,
            zone_key,
            workstation_key,
            tariff_key,
            client_group_key,
            payment_method_key,
            operation_type,
            category_key,
            product_key,
            operator_key,
        )
        return V2DrillDownResponse.from_domain(await service.drill_down(selected, principal, limit))

    return router
