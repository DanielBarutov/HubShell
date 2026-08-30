import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.analytics.application.ports import AnalyticsRepository
from gameclub_backend.modules.analytics.domain import AnalyticsOverview, ClientAnalytics


class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository) -> None:
        self._repository = repository

    async def overview(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int = 10,
    ) -> AnalyticsOverview:
        start_at, end_at = self._validate_period(start_at, end_at)
        return await self._repository.overview(start_at, end_at, max(1, min(limit, 50)))

    async def client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int = 10,
    ) -> ClientAnalytics:
        start_at, end_at = self._validate_period(start_at, end_at)
        result = await self._repository.client(client_id, start_at, end_at, max(1, min(limit, 50)))
        if result is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Client not found")
        return result

    @staticmethod
    def _validate_period(
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> tuple[datetime.datetime, datetime.datetime]:
        if start_at.tzinfo is None or end_at.tzinfo is None:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Analytics period requires aware timestamps",
            )
        start_at = start_at.astimezone(datetime.UTC)
        end_at = end_at.astimezone(datetime.UTC)
        if start_at >= end_at:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Analytics period must start before it ends",
            )
        return start_at, end_at
