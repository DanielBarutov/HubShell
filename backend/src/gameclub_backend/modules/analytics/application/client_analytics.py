from __future__ import annotations

import datetime
import typing

from gameclub_backend.modules.analytics.client_analytics import (
    ClientAnalyticsFacts,
    ClientAnalyticsReport,
    _period,
    build_client_analytics_report,
)


class ClientAnalyticsReadPort(typing.Protocol):
    async def snapshot(self) -> ClientAnalyticsFacts:
        """Read immutable domain facts without changing a producer module."""
        ...


class ClientAnalyticsService:
    def __init__(self, read_port: ClientAnalyticsReadPort) -> None:
        self._read_port = read_port

    async def report(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        *,
        as_of: datetime.datetime,
    ) -> ClientAnalyticsReport:
        start_at, end_at = _period(start_at, end_at)
        facts = await self._read_port.snapshot()
        return build_client_analytics_report(facts, start_at, end_at, as_of=as_of)
