import datetime
import typing
import uuid

from gameclub_backend.modules.catalog.domain import Product
from gameclub_backend.modules.sales.domain import ProductSale


class ProductLookup(typing.Protocol):
    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        """Return the current product card."""


class ProductSaleRepository(typing.Protocol):
    async def get_by_idempotency_key(self, idempotency_key: str) -> ProductSale | None:
        """Return a sale created by the same request key."""

    async def create_pending(self, sale: ProductSale) -> ProductSale:
        """Reserve stock and persist one pending sale atomically."""

    async def complete(self, sale: ProductSale) -> ProductSale:
        """Mark a pending sale as completed."""

    async def cancel(self, sale: ProductSale) -> ProductSale:
        """Cancel a pending sale and return reserved stock."""

    async def list_sales(
        self,
        start_at: datetime.datetime | None = None,
        end_at: datetime.datetime | None = None,
        client_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[ProductSale]:
        """Return completed sales for operator and analytics reads."""


class ClientSale(typing.Protocol):
    async def debit(
        self,
        client_id: uuid.UUID,
        amount_cents: int,
        reason: str,
        actor_id: str,
        idempotency_key: str,
    ) -> tuple[object, object]:
        """Debit a client's spendable balance."""


class CashSaleSettlement(typing.Protocol):
    async def settle(
        self,
        shift_id: uuid.UUID,
        amount_cents: int,
        sale_idempotency_key: str,
        actor_id: str,
    ) -> None:
        """Record a confirmed product sale in an open cash shift."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
