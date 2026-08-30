import datetime
import typing
import uuid

from gameclub_backend.modules.analytics.domain import AnalyticsOverview, ClientAnalytics


class AnalyticsRepository(typing.Protocol):
    async def overview(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> AnalyticsOverview:
        """Aggregate completed club facts for a period."""

    async def client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> ClientAnalytics | None:
        """Aggregate one client without changing any business data."""
