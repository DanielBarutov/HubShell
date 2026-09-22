import datetime

import pytest

from gameclub_backend.modules.analytics.application.read_v2 import AnalyticsReadService
from gameclub_backend.modules.analytics.read_v2 import AnalyticsFilter, AnalyticsReadState

UTC = datetime.UTC


class BrokenRepository:
    async def snapshot(self, filters=None):
        del filters
        raise RuntimeError("source unavailable")


@pytest.mark.asyncio
async def test_dashboard_returns_explicit_error_state_for_source_failure() -> None:
    """Проверяет явное состояние ошибки при недоступности источника."""
    report = await AnalyticsReadService(BrokenRepository()).dashboard(
        AnalyticsFilter(
            start_at=datetime.datetime(2026, 9, 20, tzinfo=UTC),
            end_at=datetime.datetime(2026, 9, 21, tzinfo=UTC),
        )
    )

    assert report.blocks["products"].state is AnalyticsReadState.ERROR
    assert report.blocks["products"].metrics == {}
