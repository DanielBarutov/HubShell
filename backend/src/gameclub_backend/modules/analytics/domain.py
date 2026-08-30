import dataclasses
import datetime
import uuid


@dataclasses.dataclass(frozen=True)
class TopProduct:
    product_id: uuid.UUID
    product_name: str
    units: int
    revenue_cents: int
    gross_profit_cents: int


@dataclasses.dataclass(frozen=True)
class TopClient:
    client_id: uuid.UUID
    nickname: str
    played_minutes: int
    session_spend_cents: int
    product_spend_cents: int
    product_units: int
    session_count: int = 0

    @property
    def total_spend_cents(self) -> int:
        return self.session_spend_cents + self.product_spend_cents


@dataclasses.dataclass(frozen=True)
class ClientAnalytics:
    client_id: uuid.UUID
    nickname: str
    phone: str | None
    start_at: datetime.datetime
    end_at: datetime.datetime
    played_minutes: int
    session_count: int
    session_spend_cents: int
    product_spend_cents: int
    product_units: int
    first_session_at: datetime.datetime | None
    last_session_at: datetime.datetime | None
    last_purchase_at: datetime.datetime | None
    favorite_products: tuple[TopProduct, ...]
    product_cost_cents: int = 0
    daily_activity: tuple["AnalyticsBucket", ...] = ()
    payment_methods: tuple["AnalyticsPayment", ...] = ()

    @property
    def total_spend_cents(self) -> int:
        return self.session_spend_cents + self.product_spend_cents

    @property
    def average_session_minutes(self) -> float:
        if not self.session_count:
            return 0.0
        return round(self.played_minutes / self.session_count, 2)


@dataclasses.dataclass(frozen=True)
class AnalyticsOverview:
    start_at: datetime.datetime
    end_at: datetime.datetime
    session_revenue_cents: int
    product_revenue_cents: int
    total_revenue_cents: int
    session_count: int
    product_sale_count: int
    product_units: int
    played_minutes: int
    guest_session_count: int
    client_count: int
    top_products: tuple[TopProduct, ...]
    top_clients: tuple[TopClient, ...]
    product_cost_cents: int = 0
    gross_profit_cents: int = 0
    discount_cents: int = 0
    active_client_count: int = 0
    new_client_count: int = 0
    returning_client_count: int = 0
    unique_visitor_count: int = 0
    workstation_count: int = 0
    occupancy_percent: float = 0.0
    peak_usage_hour: str | None = None
    daily_activity: tuple["AnalyticsBucket", ...] = ()
    hourly_activity: tuple["AnalyticsBucket", ...] = ()
    zones: tuple["AnalyticsBreakdown", ...] = ()
    workstations: tuple["AnalyticsBreakdown", ...] = ()
    tariffs: tuple["AnalyticsBreakdown", ...] = ()
    payment_methods: tuple["AnalyticsPayment", ...] = ()
    product_categories: tuple["AnalyticsBreakdown", ...] = ()

    @property
    def average_session_minutes(self) -> float:
        if not self.session_count:
            return 0.0
        return round(self.played_minutes / self.session_count, 2)


@dataclasses.dataclass(frozen=True)
class AnalyticsBucket:
    """A time bucket built from immutable session, charge and sale facts."""

    key: str
    label: str
    session_revenue_cents: int
    product_revenue_cents: int
    total_revenue_cents: int
    session_count: int
    product_sale_count: int
    product_units: int
    played_minutes: int
    guest_session_count: int = 0


@dataclasses.dataclass(frozen=True)
class AnalyticsBreakdown:
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
    share_bps: int = 0
    discount_cents: int = 0


@dataclasses.dataclass(frozen=True)
class AnalyticsPayment:
    key: str
    label: str
    revenue_cents: int
    operation_count: int
    share_bps: int = 0
