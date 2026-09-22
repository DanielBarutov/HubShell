from __future__ import annotations

import datetime
import typing

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from gameclub_backend.modules.analytics.application.finance import FinanceAnalyticsService
from gameclub_backend.modules.analytics.finance import (
    AnalyticsDataState,
    FinanceFilters,
    FinanceFlow,
    FinanceReport,
    MetricComparison,
    MetricInfo,
    MetricResult,
    PeriodComparison,
)
from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.presentation.http.auth import require_permissions

Reader = typing.Annotated[Principal, Depends(require_permissions("analytics.read"))]
QueryDatetime = typing.Annotated[datetime.datetime, Query()]


class MetricInfoResponse(BaseModel):
    key: str
    label: str
    description: str
    formula: str
    source: str

    @classmethod
    def from_domain(cls, item: MetricInfo) -> MetricInfoResponse:
        return cls.model_validate(item, from_attributes=True)


class MetricComparisonResponse(BaseModel):
    current: int | float | None
    previous: int | float | None
    delta: int | float | None
    change_percent: float | None
    change_percentage_points: float | None
    state: AnalyticsDataState

    @classmethod
    def from_domain(cls, item: MetricComparison) -> MetricComparisonResponse:
        return cls.model_validate(item, from_attributes=True)


class FinanceMetricResponse(BaseModel):
    value_cents: int | None
    state: AnalyticsDataState
    metric_info: MetricInfoResponse
    comparison: MetricComparisonResponse | None

    @classmethod
    def from_domain(cls, item: MetricResult) -> FinanceMetricResponse:
        return cls(
            value_cents=item.value_cents,
            state=item.state,
            metric_info=MetricInfoResponse.from_domain(item.metric_info),
            comparison=(
                MetricComparisonResponse.from_domain(item.comparison)
                if item.comparison is not None
                else None
            ),
        )


class FinanceSourceResponse(BaseModel):
    state: AnalyticsDataState


class FinanceFlowResponse(BaseModel):
    payment_received_cents: int | None
    direct_payment_cents: int | None
    deposit_top_up_revenue_cents: int | None
    wallet_debit_cents: int | None
    recognized_revenue_cents: int | None
    refunds_cents: int | None
    adjustments_cents: int | None
    net_cash_received_cents: int | None

    @classmethod
    def from_domain(cls, item: FinanceFlow) -> FinanceFlowResponse:
        return cls.model_validate(item, from_attributes=True)


class PaymentMethodAggregateResponse(BaseModel):
    key: str
    amount_cents: int
    operation_count: int
    share_bps: int
    average_amount_cents: int
    counter: int
    refunds_cents: int


class PeriodComparisonResponse(BaseModel):
    current_start_at: datetime.datetime
    current_end_at: datetime.datetime
    previous_start_at: datetime.datetime
    previous_end_at: datetime.datetime
    current_state: AnalyticsDataState

    @classmethod
    def from_domain(cls, item: PeriodComparison) -> PeriodComparisonResponse:
        return cls.model_validate(item, from_attributes=True)


class FinanceResponse(BaseModel):
    api_version: str
    period: FinanceFilters
    comparison: PeriodComparisonResponse
    flow: FinanceFlowResponse
    metrics: dict[str, FinanceMetricResponse]
    sources: dict[str, FinanceSourceResponse]
    payment_methods: list[PaymentMethodAggregateResponse]

    @classmethod
    def from_domain(cls, item: FinanceReport) -> FinanceResponse:
        return cls(
            api_version="v2",
            period=item.period,
            comparison=PeriodComparisonResponse.from_domain(item.comparison_period),
            flow=FinanceFlowResponse.from_domain(item.flow),
            metrics={
                key: FinanceMetricResponse.from_domain(value) for key, value in item.metrics.items()
            },
            sources={
                key: FinanceSourceResponse(state=value) for key, value in item.sources.items()
            },
            payment_methods=[
                PaymentMethodAggregateResponse.model_validate(value, from_attributes=True)
                for value in item.payment_methods
            ],
        )


def create_v2_router(service: FinanceAnalyticsService) -> APIRouter:
    router = APIRouter(prefix="/api/v2/analytics", tags=["analytics-v2"])

    @router.get("/finance", response_model=FinanceResponse)
    async def finance(
        principal: Reader,
        start_at: QueryDatetime,
        end_at: QueryDatetime,
        zone_key: str | None = Query(default=None),
        workstation_key: str | None = Query(default=None),
        tariff_key: str | None = Query(default=None),
        client_group_key: str | None = Query(default=None),
        payment_method_key: str | None = Query(default=None),
        operation_type: str | None = Query(default=None),
        product_key: str | None = Query(default=None),
        operator_key: str | None = Query(default=None),
    ) -> FinanceResponse:
        del principal
        try:
            filters = FinanceFilters(
                start_at=start_at,
                end_at=end_at,
                zone_key=zone_key,
                workstation_key=workstation_key,
                tariff_key=tariff_key,
                client_group_key=client_group_key,
                payment_method_key=payment_method_key,
                operation_type=operation_type,
                product_key=product_key,
                operator_key=operator_key,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return FinanceResponse.from_domain(await service.finance(filters))

    return router
