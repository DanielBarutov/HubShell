import csv
import datetime
import io
import typing
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel

from gameclub_backend.modules.analytics.application.service import AnalyticsService
from gameclub_backend.modules.analytics.domain import (
    AnalyticsBreakdown,
    AnalyticsBucket,
    AnalyticsOverview,
    AnalyticsPayment,
    ClientAnalytics,
    TopClient,
    TopProduct,
)
from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.presentation.http.auth import require_permissions

Reader = typing.Annotated[Principal, Depends(require_permissions("analytics.read"))]
QueryDatetime = typing.Annotated[datetime.datetime, Query()]


class AnalyticsBucketResponse(BaseModel):
    key: str
    label: str
    session_revenue_cents: int
    product_revenue_cents: int
    total_revenue_cents: int
    session_count: int
    product_sale_count: int
    product_units: int
    played_minutes: int
    guest_session_count: int

    @classmethod
    def from_domain(cls, item: AnalyticsBucket) -> "AnalyticsBucketResponse":
        return cls.model_validate(item, from_attributes=True)


class AnalyticsBreakdownResponse(BaseModel):
    key: str
    label: str
    session_revenue_cents: int
    product_revenue_cents: int
    revenue_cents: int
    product_cost_cents: int
    gross_profit_cents: int
    session_count: int
    product_sale_count: int
    product_units: int
    played_minutes: int
    share_bps: int
    discount_cents: int

    @classmethod
    def from_domain(cls, item: AnalyticsBreakdown) -> "AnalyticsBreakdownResponse":
        return cls.model_validate(item, from_attributes=True)


class AnalyticsPaymentResponse(BaseModel):
    key: str
    label: str
    revenue_cents: int
    operation_count: int
    share_bps: int

    @classmethod
    def from_domain(cls, item: AnalyticsPayment) -> "AnalyticsPaymentResponse":
        return cls.model_validate(item, from_attributes=True)


class TopProductResponse(BaseModel):
    product_id: uuid.UUID
    product_name: str
    units: int
    revenue_cents: int
    gross_profit_cents: int

    @classmethod
    def from_domain(cls, item: TopProduct) -> "TopProductResponse":
        return cls.model_validate(item, from_attributes=True)


class TopClientResponse(BaseModel):
    client_id: uuid.UUID
    nickname: str
    session_count: int
    played_minutes: int
    session_spend_cents: int
    product_spend_cents: int
    product_units: int
    total_spend_cents: int

    @classmethod
    def from_domain(cls, item: TopClient) -> "TopClientResponse":
        return cls(
            client_id=item.client_id,
            nickname=item.nickname,
            session_count=item.session_count,
            played_minutes=item.played_minutes,
            session_spend_cents=item.session_spend_cents,
            product_spend_cents=item.product_spend_cents,
            product_units=item.product_units,
            total_spend_cents=item.total_spend_cents,
        )


class AnalyticsOverviewResponse(BaseModel):
    start_at: datetime.datetime
    end_at: datetime.datetime
    session_revenue_cents: int
    product_revenue_cents: int
    total_revenue_cents: int
    session_count: int
    product_sale_count: int
    product_units: int
    played_minutes: int
    average_session_minutes: float
    guest_session_count: int
    client_count: int
    top_products: list[TopProductResponse]
    top_clients: list[TopClientResponse]
    product_cost_cents: int
    gross_profit_cents: int
    discount_cents: int
    active_client_count: int
    new_client_count: int
    returning_client_count: int
    unique_visitor_count: int
    workstation_count: int
    occupancy_percent: float
    peak_usage_hour: str | None
    daily_activity: list[AnalyticsBucketResponse]
    hourly_activity: list[AnalyticsBucketResponse]
    zones: list[AnalyticsBreakdownResponse]
    workstations: list[AnalyticsBreakdownResponse]
    tariffs: list[AnalyticsBreakdownResponse]
    payment_methods: list[AnalyticsPaymentResponse]
    product_categories: list[AnalyticsBreakdownResponse]

    @classmethod
    def from_domain(cls, item: AnalyticsOverview) -> "AnalyticsOverviewResponse":
        return cls(
            start_at=item.start_at,
            end_at=item.end_at,
            session_revenue_cents=item.session_revenue_cents,
            product_revenue_cents=item.product_revenue_cents,
            total_revenue_cents=item.total_revenue_cents,
            session_count=item.session_count,
            product_sale_count=item.product_sale_count,
            product_units=item.product_units,
            played_minutes=item.played_minutes,
            average_session_minutes=item.average_session_minutes,
            guest_session_count=item.guest_session_count,
            client_count=item.client_count,
            top_products=[TopProductResponse.from_domain(value) for value in item.top_products],
            top_clients=[TopClientResponse.from_domain(value) for value in item.top_clients],
            product_cost_cents=item.product_cost_cents,
            gross_profit_cents=item.gross_profit_cents,
            discount_cents=item.discount_cents,
            active_client_count=item.active_client_count,
            new_client_count=item.new_client_count,
            returning_client_count=item.returning_client_count,
            unique_visitor_count=item.unique_visitor_count,
            workstation_count=item.workstation_count,
            occupancy_percent=item.occupancy_percent,
            peak_usage_hour=item.peak_usage_hour,
            daily_activity=[
                AnalyticsBucketResponse.from_domain(value) for value in item.daily_activity
            ],
            hourly_activity=[
                AnalyticsBucketResponse.from_domain(value) for value in item.hourly_activity
            ],
            zones=[AnalyticsBreakdownResponse.from_domain(value) for value in item.zones],
            workstations=[
                AnalyticsBreakdownResponse.from_domain(value) for value in item.workstations
            ],
            tariffs=[AnalyticsBreakdownResponse.from_domain(value) for value in item.tariffs],
            payment_methods=[
                AnalyticsPaymentResponse.from_domain(value) for value in item.payment_methods
            ],
            product_categories=[
                AnalyticsBreakdownResponse.from_domain(value) for value in item.product_categories
            ],
        )


class ClientAnalyticsResponse(BaseModel):
    client_id: uuid.UUID
    nickname: str
    phone: str | None
    start_at: datetime.datetime
    end_at: datetime.datetime
    played_minutes: int
    played_hours: float
    session_count: int
    average_session_minutes: float
    session_spend_cents: int
    product_spend_cents: int
    total_spend_cents: int
    product_units: int
    product_cost_cents: int
    first_session_at: datetime.datetime | None
    last_session_at: datetime.datetime | None
    last_purchase_at: datetime.datetime | None
    favorite_products: list[TopProductResponse]
    daily_activity: list[AnalyticsBucketResponse]
    payment_methods: list[AnalyticsPaymentResponse]

    @classmethod
    def from_domain(cls, item: ClientAnalytics) -> "ClientAnalyticsResponse":
        return cls(
            client_id=item.client_id,
            nickname=item.nickname,
            phone=item.phone,
            start_at=item.start_at,
            end_at=item.end_at,
            played_minutes=item.played_minutes,
            played_hours=round(item.played_minutes / 60, 2),
            session_count=item.session_count,
            average_session_minutes=item.average_session_minutes,
            session_spend_cents=item.session_spend_cents,
            product_spend_cents=item.product_spend_cents,
            total_spend_cents=item.total_spend_cents,
            product_units=item.product_units,
            product_cost_cents=item.product_cost_cents,
            first_session_at=item.first_session_at,
            last_session_at=item.last_session_at,
            last_purchase_at=item.last_purchase_at,
            favorite_products=[
                TopProductResponse.from_domain(value) for value in item.favorite_products
            ],
            daily_activity=[
                AnalyticsBucketResponse.from_domain(value) for value in item.daily_activity
            ],
            payment_methods=[
                AnalyticsPaymentResponse.from_domain(value) for value in item.payment_methods
            ],
        )


_CSV_HEADERS = (
    "section",
    "key",
    "label",
    "session_revenue_cents",
    "product_revenue_cents",
    "revenue_cents",
    "total_revenue_cents",
    "product_cost_cents",
    "gross_profit_cents",
    "discount_cents",
    "session_count",
    "product_sale_count",
    "product_units",
    "played_minutes",
    "guest_session_count",
    "operation_count",
    "share_bps",
    "units",
)


def _csv_text(value: object) -> str:
    """Avoid turning labels into spreadsheet formulas on import."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _write_csv_row(writer: csv.writer, section: str, **values: object) -> None:
    writer.writerow(
        [_csv_text(section), *(_csv_text(values.get(header)) for header in _CSV_HEADERS[1:])]
    )


def _overview_csv(item: AnalyticsOverview) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(_CSV_HEADERS)
    _write_csv_row(
        writer,
        "overview",
        key="period",
        label=f"{item.start_at.isoformat()} — {item.end_at.isoformat()}",
        session_revenue_cents=item.session_revenue_cents,
        product_revenue_cents=item.product_revenue_cents,
        revenue_cents=item.total_revenue_cents,
        total_revenue_cents=item.total_revenue_cents,
        product_cost_cents=item.product_cost_cents,
        gross_profit_cents=item.gross_profit_cents,
        discount_cents=item.discount_cents,
        session_count=item.session_count,
        product_sale_count=item.product_sale_count,
        product_units=item.product_units,
        played_minutes=item.played_minutes,
        guest_session_count=item.guest_session_count,
    )
    for section, buckets in (
        ("daily", item.daily_activity),
        ("hourly", item.hourly_activity),
    ):
        for bucket in buckets:
            _write_csv_row(
                writer,
                section,
                key=bucket.key,
                label=bucket.label,
                session_revenue_cents=bucket.session_revenue_cents,
                product_revenue_cents=bucket.product_revenue_cents,
                revenue_cents=bucket.total_revenue_cents,
                total_revenue_cents=bucket.total_revenue_cents,
                session_count=bucket.session_count,
                product_sale_count=bucket.product_sale_count,
                product_units=bucket.product_units,
                played_minutes=bucket.played_minutes,
                guest_session_count=bucket.guest_session_count,
            )
    for section, breakdowns in (
        ("zone", item.zones),
        ("workstation", item.workstations),
        ("tariff", item.tariffs),
        ("product_category", item.product_categories),
    ):
        for breakdown in breakdowns:
            _write_csv_row(
                writer,
                section,
                key=breakdown.key,
                label=breakdown.label,
                session_revenue_cents=breakdown.session_revenue_cents,
                product_revenue_cents=breakdown.product_revenue_cents,
                revenue_cents=breakdown.revenue_cents,
                product_cost_cents=breakdown.product_cost_cents,
                gross_profit_cents=breakdown.gross_profit_cents,
                discount_cents=breakdown.discount_cents,
                session_count=breakdown.session_count,
                product_sale_count=breakdown.product_sale_count,
                product_units=breakdown.product_units,
                played_minutes=breakdown.played_minutes,
                share_bps=breakdown.share_bps,
            )
    for payment in item.payment_methods:
        _write_csv_row(
            writer,
            "payment",
            key=payment.key,
            label=payment.label,
            revenue_cents=payment.revenue_cents,
            operation_count=payment.operation_count,
            share_bps=payment.share_bps,
        )
    for product in item.top_products:
        _write_csv_row(
            writer,
            "top_product",
            key=product.product_id,
            label=product.product_name,
            revenue_cents=product.revenue_cents,
            gross_profit_cents=product.gross_profit_cents,
            units=product.units,
        )
    for client in item.top_clients:
        _write_csv_row(
            writer,
            "top_client",
            key=client.client_id,
            label=client.nickname,
            session_revenue_cents=client.session_spend_cents,
            product_revenue_cents=client.product_spend_cents,
            revenue_cents=client.total_spend_cents,
            session_count=client.session_count,
            product_units=client.product_units,
            played_minutes=client.played_minutes,
        )
    return output.getvalue()


def create_router(service: AnalyticsService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

    @router.get("/overview", response_model=AnalyticsOverviewResponse)
    async def overview(
        principal: Reader,
        start_at: QueryDatetime,
        end_at: QueryDatetime,
        limit: int = Query(default=10, ge=1, le=50),
    ) -> AnalyticsOverviewResponse:
        del principal
        return AnalyticsOverviewResponse.from_domain(
            await service.overview(start_at, end_at, limit)
        )

    @router.get("/overview.csv", response_class=Response)
    async def overview_csv(
        principal: Reader,
        start_at: QueryDatetime,
        end_at: QueryDatetime,
        limit: int = Query(default=10, ge=1, le=50),
    ) -> Response:
        del principal
        overview = await service.overview(start_at, end_at, limit)
        filename = f"analytics-{overview.start_at:%Y%m%d}-{overview.end_at:%Y%m%d}.csv"
        return Response(
            content="\ufeff" + _overview_csv(overview),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/clients/{client_id}", response_model=ClientAnalyticsResponse)
    async def client(
        client_id: uuid.UUID,
        principal: Reader,
        start_at: QueryDatetime,
        end_at: QueryDatetime,
        limit: int = Query(default=10, ge=1, le=50),
    ) -> ClientAnalyticsResponse:
        del principal
        return ClientAnalyticsResponse.from_domain(
            await service.client(client_id, start_at, end_at, limit)
        )

    return router
