from __future__ import annotations

import typing

from gameclub_backend.modules.analytics.read_v2 import (
    AnalyticsFilter,
    AnalyticsReadRepository,
    ProductAdjustmentFact,
    ProductSaleFact,
)


class InMemoryAnalyticsReadRepository(AnalyticsReadRepository):
    def __init__(
        self,
        product_sales: typing.Iterable[ProductSaleFact] = (),
        adjustments: typing.Iterable[ProductAdjustmentFact] | None = None,
    ) -> None:
        self._product_sales = tuple(product_sales)
        self._adjustments = None if adjustments is None else tuple(adjustments)

    async def snapshot(
        self, filters: AnalyticsFilter | None = None
    ) -> tuple[tuple[ProductSaleFact, ...], tuple[ProductAdjustmentFact, ...] | None]:
        del filters
        return self._product_sales, self._adjustments
