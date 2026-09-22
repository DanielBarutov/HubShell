from __future__ import annotations

import typing

from gameclub_backend.modules.analytics.finance import (
    FinanceFactsSnapshot,
    FinanceFilters,
    FinancialFact,
    WalletFact,
)


class InMemoryFinanceAnalyticsRepository:
    """Analytics-only fixture repository; missing sources stay unavailable."""

    def __init__(
        self,
        financial_facts: typing.Iterable[FinancialFact] | None = None,
        wallet_facts: typing.Iterable[WalletFact] | None = None,
        *,
        refunds_available: bool = False,
        history_available: bool = False,
    ) -> None:
        self._snapshot = FinanceFactsSnapshot(
            financial_facts=None if financial_facts is None else tuple(financial_facts),
            wallet_facts=None if wallet_facts is None else tuple(wallet_facts),
            refunds_available=refunds_available,
            history_available=history_available,
        )

    async def snapshot(self, filters: FinanceFilters | None = None) -> FinanceFactsSnapshot:
        del filters
        return self._snapshot
