import datetime
import uuid

from gameclub_backend.modules.analytics.domain import AnalyticsOverview, ClientAnalytics


class InMemoryAnalyticsRepository:
    """Small configurable fake for application/API tests."""

    def __init__(
        self,
        overview_result: AnalyticsOverview | None = None,
        client_results: dict[uuid.UUID, ClientAnalytics] | None = None,
    ) -> None:
        self.overview_result = overview_result
        self.client_results = client_results or {}

    async def overview(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> AnalyticsOverview:
        if self.overview_result is not None:
            return self.overview_result
        return AnalyticsOverview(
            start_at=start_at,
            end_at=end_at,
            session_revenue_cents=0,
            product_revenue_cents=0,
            total_revenue_cents=0,
            session_count=0,
            product_sale_count=0,
            product_units=0,
            played_minutes=0,
            guest_session_count=0,
            client_count=0,
            top_products=(),
            top_clients=(),
        )

    async def client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> ClientAnalytics | None:
        return self.client_results.get(client_id)
