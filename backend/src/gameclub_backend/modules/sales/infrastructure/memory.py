import asyncio
import datetime
import uuid

from gameclub_backend.modules.sales.domain import ProductSale, ProductSaleStatus


class InMemoryProductSaleRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, ProductSale] = {}
        self._by_key: dict[str, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get_by_idempotency_key(self, idempotency_key: str) -> ProductSale | None:
        sale_id = self._by_key.get(idempotency_key)
        return self._items.get(sale_id) if sale_id else None

    async def create_pending(self, sale: ProductSale) -> ProductSale:
        async with self._lock:
            existing_id = self._by_key.get(sale.idempotency_key)
            if existing_id is not None:
                return self._items[existing_id]
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
            self._items[sale.id] = cancelled
            return cancelled

    async def mark_needs_review(self, sale: ProductSale, error: str) -> ProductSale:
        async with self._lock:
            current = self._items.get(sale.id)
            if current is None:
                raise ValueError("Product sale not found")
            if current.status is ProductSaleStatus.COMPLETED:
                return current
            reviewed = current.needs_review(error)
            self._items[sale.id] = reviewed
            return reviewed

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
