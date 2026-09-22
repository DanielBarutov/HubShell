import datetime
import typing
import uuid

from gameclub_backend.modules.analytics.domain import AnalyticsOverview, ClientAnalytics
from gameclub_backend.modules.analytics.finance import (
    FinanceFactsSnapshot,
    FinanceFilters,
    FinancialFact,
    WalletFact,
)


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


class FinanceAnalyticsRepository(typing.Protocol):
    async def snapshot(self, filters: FinanceFilters | None = None) -> FinanceFactsSnapshot:
        """Return analytics-owned immutable facts or None for unavailable sources."""
        ...


class ClientFinanceReadPort(typing.Protocol):
    async def read_wallet_facts(self, filters: FinanceFilters) -> tuple[WalletFact, ...]:
        """Read balance-ledger facts owned by Clients."""
        ...


class BillingFinanceReadPort(typing.Protocol):
    async def read_payment_facts(self, filters: FinanceFilters) -> tuple[FinancialFact, ...]:
        """Read confirmed payment facts owned by Billing."""
        ...


class EntitlementsFinanceReadPort(typing.Protocol):
    async def read_entitlement_facts(
        self,
        filters: FinanceFilters,
    ) -> tuple[FinancialFact, ...]:
        """Read entitlement settlement facts owned by Entitlements."""
        ...


class ProductSalesFinanceReadPort(typing.Protocol):
    async def read_product_sale_facts(
        self,
        filters: FinanceFilters,
    ) -> tuple[FinancialFact, ...]:
        """Read completed product-sale payment facts."""
        ...


class DirectPaymentsFinanceReadPort(typing.Protocol):
    async def read_direct_payment_facts(
        self,
        filters: FinanceFilters,
    ) -> tuple[FinancialFact, ...]:
        """Read direct guest/session payment facts."""
        ...


class CashShiftsFinanceReadPort(typing.Protocol):
    async def read_cash_movement_facts(
        self,
        filters: FinanceFilters,
    ) -> tuple[FinancialFact, ...]:
        """Read cash movement facts and cash-shift references."""
        ...
