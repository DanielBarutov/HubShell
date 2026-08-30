from __future__ import annotations

import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.sales.application.ports import (
    CashSaleSettlement,
    ClientSale,
    Clock,
    ProductLookup,
    ProductSaleRepository,
)
from gameclub_backend.modules.sales.domain import (
    ProductPaymentMethod,
    ProductSale,
    ProductSaleStatus,
)


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class ProductSaleService:
    def __init__(
        self,
        repository: ProductSaleRepository,
        products: ProductLookup,
        clients: ClientSale,
        cash: CashSaleSettlement | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._products = products
        self._clients = clients
        self._cash = cash
        self._clock = clock or UtcClock()

    async def sell(
        self,
        product_id: uuid.UUID,
        quantity: int,
        client_id: uuid.UUID | None,
        payment_method: str,
        cash_shift_id: uuid.UUID | None,
        sold_by: str,
        idempotency_key: str,
    ) -> ProductSale:
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        existing = await self._repository.get_by_idempotency_key(key)
        if existing is not None:
            if (
                existing.product_id != product_id
                or existing.quantity != quantity
                or existing.client_id != client_id
                or existing.payment_method.value != payment_method.strip().lower()
                or existing.cash_shift_id != cash_shift_id
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Idempotency key belongs to another sale"
                )
            return existing
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Quantity must be a positive integer"
            )
        try:
            method = ProductPaymentMethod(payment_method.strip().lower())
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Unknown payment method") from error
        product = await self._products.get_product(product_id)
        if product is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Product not found")
        if not product.active:
            raise ApplicationError(ErrorCode.CONFLICT, "Product is inactive")
        if product.stock_quantity < quantity:
            raise ApplicationError(ErrorCode.CONFLICT, "Insufficient product stock")
        actor = sold_by.strip()
        if not actor:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Sale author is required")
        try:
            sale = ProductSale(
                id=uuid.uuid4(),
                product_id=product.id,
                product_name=product.name,
                product_category=product.category,
                client_id=client_id,
                guest_name=None if client_id is not None else "Гость",
                quantity=quantity,
                unit_price_cents=product.price_cents,
                unit_cost_price_cents=product.cost_price_cents,
                total_price_cents=product.price_cents * quantity,
                total_cost_price_cents=product.cost_price_cents * quantity,
                payment_method=method,
                cash_shift_id=cash_shift_id,
                status=ProductSaleStatus.PENDING,
                sold_by=actor,
                idempotency_key=key,
                created_at=self._clock.now(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        settled = False
        try:
            pending = await self._repository.create_pending(sale)
            if pending.id != sale.id:
                # Another request with the same key won the reservation lock.
                # The first lookup can race with that request, so never settle
                # a pending row that this invocation did not create.
                return pending
            if pending.status is ProductSaleStatus.COMPLETED:
                return pending
            if method is ProductPaymentMethod.BALANCE:
                await self._clients.debit(
                    client_id=client_id,
                    amount_cents=pending.total_price_cents,
                    reason=f"Product sale {pending.id}",
                    actor_id=actor,
                    idempotency_key=f"product-sale-balance:{key}",
                )
            else:
                if self._cash is None or cash_shift_id is None:
                    raise ApplicationError(
                        ErrorCode.DEPENDENCY_UNAVAILABLE,
                        "Cash settlement is not configured",
                    )
                await self._cash.settle(
                    shift_id=cash_shift_id,
                    amount_cents=pending.total_price_cents,
                    sale_idempotency_key=key,
                    actor_id=actor,
                )
            settled = True
            return await self._repository.complete(pending.complete(self._clock.now()))
        except ApplicationError:
            if not settled:
                await self._cancel_pending(sale)
            raise
        except ValueError as error:
            if not settled:
                await self._cancel_pending(sale)
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def _cancel_pending(self, sale: ProductSale) -> None:
        try:
            if sale.status is ProductSaleStatus.PENDING:
                await self._repository.cancel(sale)
        except Exception:
            # The pending row is intentionally retained for reconciliation if the
            # compensating stock update cannot be completed immediately.
            return

    async def list_sales(
        self,
        start_at: datetime.datetime | None = None,
        end_at: datetime.datetime | None = None,
        client_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[ProductSale]:
        return await self._repository.list_sales(
            start_at, end_at, client_id, max(1, min(limit, 500))
        )
