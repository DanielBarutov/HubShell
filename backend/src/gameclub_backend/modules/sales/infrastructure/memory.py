import asyncio
import datetime
import uuid

from gameclub_backend.modules.catalog.application.ports import ProductInventory
from gameclub_backend.modules.sales.domain import ProductSale, ProductSaleStatus


class InMemoryProductSaleRepository:
    def __init__(self, inventory: ProductInventory | None = None) -> None:
        self._items: dict[uuid.UUID, ProductSale] = {}
        self._by_key: dict[str, uuid.UUID] = {}
        self._inventory = inventory
        self._lock = asyncio.Lock()

    async def get_by_idempotency_key(self, idempotency_key: str) -> ProductSale | None:
        sale_id = self._by_key.get(idempotency_key)
        return self._items.get(sale_id) if sale_id else None

    async def get_by_id(self, sale_id: uuid.UUID) -> ProductSale | None:
        return self._items.get(sale_id)

    async def create_pending(self, sale: ProductSale) -> ProductSale:
        async with self._lock:
            existing_id = self._by_key.get(sale.idempotency_key)
            if existing_id is not None:
                return self._items[existing_id]
            if self._inventory is not None:
                await self._inventory.reserve_stock(
                    sale.product_id,
                    sale.quantity,
                    sale.unit_price_cents,
                    sale.unit_cost_price_cents,
                )
            self._items[sale.id] = sale
            self._by_key[sale.idempotency_key] = sale.id
            return sale

    async def complete(self, sale: ProductSale) -> ProductSale:
        async with self._lock:
            current = self._items.get(sale.id)
            if current is None:
                raise ValueError("Product sale not found")
            if current.status is ProductSaleStatus.COMPLETED:
                return current
            self._items[sale.id] = sale
            return sale

    async def cancel(self, sale: ProductSale) -> ProductSale:
        async with self._lock:
            current = self._items.get(sale.id)
            if current is None:
                raise ValueError("Product sale not found")
            if current.status is ProductSaleStatus.COMPLETED:
                return current
            cancelled = current.cancel()
            if self._inventory is not None and current.status is ProductSaleStatus.PENDING:
                await self._inventory.release_stock(current.product_id, current.quantity)
            self._items[sale.id] = cancelled
            return cancelled

    async def mark_needs_review(
        self,
        sale: ProductSale,
        error: str,
        now: datetime.datetime | None = None,
    ) -> ProductSale:
        async with self._lock:
            current = self._items.get(sale.id)
            if current is None:
                raise ValueError("Product sale not found")
            if current.status is ProductSaleStatus.COMPLETED:
                return current
            reviewed = current.needs_review(error, now)
            self._items[sale.id] = reviewed
            return reviewed

    async def mark_retryable(
        self,
        sale: ProductSale,
        error: str,
        now: datetime.datetime,
    ) -> ProductSale:
        async with self._lock:
            current = self._items.get(sale.id)
            if current is None:
                raise ValueError("Product sale not found")
            if current.status is ProductSaleStatus.COMPLETED:
                return current
            retryable = current.schedule_retry(error, now)
            self._items[sale.id] = retryable
            return retryable

    async def reopen_for_reconciliation(
        self,
        sale: ProductSale,
        now: datetime.datetime,
    ) -> ProductSale:
        async with self._lock:
            current = self._items.get(sale.id)
            if current is None:
                raise ValueError("Product sale not found")
            reopened = current.reopen_for_review(now)
            self._items[sale.id] = reopened
            return reopened

    async def list_sales(
        self,
        start_at: datetime.datetime | None = None,
        end_at: datetime.datetime | None = None,
        client_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[ProductSale]:
        items = [
            item
            for item in self._items.values()
            if item.status in {ProductSaleStatus.COMPLETED, ProductSaleStatus.NEEDS_REVIEW}
        ]
        if start_at is not None:
            items = [item for item in items if item.created_at >= start_at]
        if end_at is not None:
            items = [item for item in items if item.created_at < end_at]
        if client_id is not None:
            items = [item for item in items if item.client_id == client_id]
        return sorted(items, key=lambda item: item.created_at, reverse=True)[:limit]

    async def list_recoverable(
        self,
        limit: int = 100,
        now: datetime.datetime | None = None,
    ) -> list[ProductSale]:
        moment = now or datetime.datetime.now(datetime.UTC)
        return [item for item in self._items.values() if item.is_due(moment)][
            : max(1, min(limit, 500))
        ]
