from __future__ import annotations

import datetime
import logging
import uuid
from collections.abc import Mapping, Sequence

from gameclub_backend.application.audit import AuditEvent, AuditRepository
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.payment_methods.domain import PaymentPart, normalize_payment_parts
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
        audit: AuditRepository | None = None,
    ) -> None:
        self._repository = repository
        self._products = products
        self._clients = clients
        self._cash = cash
        self._clock = clock or UtcClock()
        self._audit = audit

    async def sell(
        self,
        product_id: uuid.UUID,
        quantity: int,
        client_id: uuid.UUID | None,
        payment_method: str,
        cash_shift_id: uuid.UUID | None,
        sold_by: str,
        idempotency_key: str,
        payment_parts: Sequence[PaymentPart | Mapping[str, object]] | None = None,
    ) -> ProductSale:
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        existing = await self._repository.get_by_idempotency_key(key)
        if existing is not None:
            try:
                existing_parts = normalize_payment_parts(payment_parts, existing.total_price_cents)
            except ValueError as error:
                raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
            if not self._matches_request(
                existing,
                product_id=product_id,
                quantity=quantity,
                client_id=client_id,
                payment_method=payment_method,
                cash_shift_id=cash_shift_id,
                payment_parts=existing_parts,
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
        try:
            normalized_parts = normalize_payment_parts(
                payment_parts,
                product.price_cents * quantity,
            )
            method = ProductPaymentMethod(payment_method.strip().lower())
            if normalized_parts:
                if len(normalized_parts) > 1 and method is not ProductPaymentMethod.MIXED:
                    raise ValueError("Multiple payment parts require mixed payment")
                if len(normalized_parts) == 1 and method is ProductPaymentMethod.MIXED:
                    raise ValueError("Mixed payment requires at least two payment parts")
                if len(normalized_parts) == 1 and normalized_parts[0].method != method.value:
                    raise ValueError("Payment method does not match the payment part")
                if any(part.method not in {"balance", "cash"} for part in normalized_parts):
                    raise ApplicationError(
                        ErrorCode.DEPENDENCY_UNAVAILABLE,
                        "Direct payment provider is not configured for this payment method",
                    )
                if client_id is None and any(part.method == "balance" for part in normalized_parts):
                    raise ValueError("Balance payment requires a client")
                if (
                    any(part.method == "cash" for part in normalized_parts)
                    and cash_shift_id is None
                ):
                    raise ValueError("Cash payment requires a cash shift")
        except ApplicationError:
            raise
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
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
                payment_parts=normalized_parts,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        settled_any = False
        settlement_attempted = False
        try:
            pending = await self._repository.create_pending(sale)
            if pending.id != sale.id:
                # Another request with the same key won the reservation lock.
                # The first lookup can race with that request, so never settle
                # a pending row that this invocation did not create.
                if not self._matches_request(
                    pending,
                    product_id=product_id,
                    quantity=quantity,
                    client_id=client_id,
                    payment_method=method.value,
                    cash_shift_id=cash_shift_id,
                    payment_parts=sale.payment_parts,
                ):
                    raise ApplicationError(
                        ErrorCode.CONFLICT, "Idempotency key belongs to another sale"
                    )
                return pending
            if pending.status is ProductSaleStatus.COMPLETED:
                return pending
            settlement_parts = pending.payment_parts or (
                PaymentPart(method.value, pending.total_price_cents),
            )
            for index, part in enumerate(settlement_parts):
                if part.method == ProductPaymentMethod.BALANCE.value:
                    settlement_attempted = True
                    await self._clients.debit(
                        client_id=client_id,
                        amount_cents=part.amount_cents,
                        reason=f"Product sale {pending.id}",
                        actor_id=actor,
                        idempotency_key=f"product-sale-balance:{key}:{index}",
                    )
                else:
                    if self._cash is None or cash_shift_id is None:
                        raise ApplicationError(
                            ErrorCode.DEPENDENCY_UNAVAILABLE,
                            "Cash settlement is not configured",
                        )
                    settlement_attempted = True
                    await self._cash.settle(
                        shift_id=cash_shift_id,
                        amount_cents=part.amount_cents,
                        sale_idempotency_key=f"{key}:{index}",
                        actor_id=actor,
                    )
                settled_any = True
            result = await self._repository.complete(pending.complete(self._clock.now()))
            await self._record_audit(
                action="product_sale.settlement",
                sale=result,
                actor_id=actor,
                outcome="success",
                status_code=200,
            )
            return result
        except ApplicationError as error:
            if not settled_any and not settlement_attempted:
                await self._cancel_pending(sale)
                outcome = "cancelled"
            elif self._is_retryable(error):
                await self._mark_retryable(sale, str(error), self._clock.now())
                outcome = "retryable"
            else:
                await self._mark_needs_review(
                    sale,
                    "Payment settlement may have been applied; manual review is required",
                )
                outcome = "needs_review"
            await self._record_audit(
                action="product_sale.settlement",
                sale=sale,
                actor_id=actor,
                outcome=outcome,
                status_code=500,
            )
            raise
        except ValueError as error:
            if not settled_any and not settlement_attempted:
                await self._cancel_pending(sale)
                outcome = "cancelled"
            else:
                await self._mark_needs_review(sale, str(error))
                outcome = "needs_review"
            await self._record_audit(
                action="product_sale.settlement",
                sale=sale,
                actor_id=actor,
                outcome=outcome,
                status_code=500,
            )
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

        except Exception as error:
            if not settled_any and not settlement_attempted:
                await self._cancel_pending(sale)
                outcome = "cancelled"
            else:
                await self._mark_needs_review(sale, f"Manual review required: {error}")
                outcome = "needs_review"
            await self._record_audit(
                action="product_sale.settlement",
                sale=sale,
                actor_id=actor,
                outcome=outcome,
                status_code=500,
            )
            raise

    async def _cancel_pending(self, sale: ProductSale) -> None:
        try:
            if sale.status is ProductSaleStatus.PENDING:
                await self._repository.cancel(sale)
        except Exception:
            # The pending row is intentionally retained for reconciliation if the
            # compensating stock update cannot be completed immediately.
            return

    async def _mark_needs_review(
        self,
        sale: ProductSale,
        error: str,
        now: datetime.datetime | None = None,
    ) -> None:
        try:
            await self._repository.mark_needs_review(sale, error, now)
        except Exception:
            # Preserve the settlement failure; an operator can still inspect the
            # durable pending row if the review transition itself is unavailable.
            return

    async def _mark_retryable(
        self,
        sale: ProductSale,
        error: str,
        now: datetime.datetime,
    ) -> None:
        try:
            await self._repository.mark_retryable(sale, error, now)
        except Exception:
            # Keep the original settlement failure visible. The durable pending
            # row remains available for the next reconciliation sweep.
            return

    async def reconcile(self, sale_id: uuid.UUID) -> ProductSale:
        """Retry a pending/review sale using the original idempotent side effects.

        This is an explicit operator action. Pending rows are safe worker input;
        needs_review rows are never retried implicitly after an unknown cash
        result.
        """
        sale = await self._repository.get_by_id(sale_id)
        if sale is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Product sale not found")
        if sale.status is ProductSaleStatus.COMPLETED:
            return sale
        if sale.status is ProductSaleStatus.CANCELLED:
            raise ApplicationError(ErrorCode.CONFLICT, "Cancelled sale cannot be reconciled")
        if sale.status not in {ProductSaleStatus.PENDING, ProductSaleStatus.NEEDS_REVIEW}:
            raise ApplicationError(ErrorCode.CONFLICT, "Sale is not recoverable")
        if sale.status is ProductSaleStatus.NEEDS_REVIEW:
            sale = await self._repository.reopen_for_reconciliation(
                sale,
                self._clock.now(),
            )
        parts = sale.payment_parts or (
            PaymentPart(sale.payment_method.value, sale.total_price_cents),
        )
        try:
            for index, part in enumerate(parts):
                if part.method == ProductPaymentMethod.BALANCE.value:
                    if sale.client_id is None:
                        raise ApplicationError(
                            ErrorCode.CONFLICT,
                            "Balance payment requires a client",
                        )
                    await self._clients.debit(
                        client_id=sale.client_id,
                        amount_cents=part.amount_cents,
                        reason=f"Product sale {sale.id}",
                        actor_id=sale.sold_by,
                        idempotency_key=f"product-sale-balance:{sale.idempotency_key}:{index}",
                    )
                else:
                    if self._cash is None or sale.cash_shift_id is None:
                        raise ApplicationError(
                            ErrorCode.DEPENDENCY_UNAVAILABLE,
                            "Cash settlement is not configured",
                        )
                    await self._cash.settle(
                        shift_id=sale.cash_shift_id,
                        amount_cents=part.amount_cents,
                        sale_idempotency_key=f"{sale.idempotency_key}:{index}",
                        actor_id=sale.sold_by,
                    )
            result = await self._repository.complete(sale.complete(self._clock.now()))
            await self._record_audit(
                action="product_sale.settlement",
                sale=result,
                actor_id=sale.sold_by,
                outcome="success",
                status_code=200,
            )
            return result
        except Exception as error:
            now = self._clock.now()
            message = (
                f"Settlement retry scheduled: {error}"
                if self._is_retryable(error)
                else f"Manual review required: {error}"
            )
            if self._is_retryable(error):
                await self._mark_retryable(sale, message, now)
            else:
                await self._mark_needs_review(sale, message, now)
            await self._record_audit(
                action="product_sale.settlement",
                sale=sale,
                actor_id=sale.sold_by,
                outcome="retryable" if self._is_retryable(error) else "needs_review",
                status_code=500,
            )
            raise

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        return isinstance(error, ApplicationError) and error.code in {
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            ErrorCode.INTERNAL,
        }

    async def _record_audit(
        self,
        *,
        action: str,
        sale: ProductSale,
        actor_id: str,
        outcome: str,
        status_code: int,
    ) -> None:
        if self._audit is None:
            return
        event = AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id.strip() or None,
            action=action,
            resource_path=f"/api/v1/sales/{sale.id}",
            outcome=outcome,
            status_code=status_code,
            request_id=sale.idempotency_key,
            created_at=self._clock.now(),
        )
        try:
            await self._audit.record(event)
        except Exception:
            logging.getLogger(__name__).warning(
                "product_sale_audit_write_failed sale_id=%s",
                sale.id,
            )

    @staticmethod
    def _matches_request(
        sale: ProductSale,
        *,
        product_id: uuid.UUID,
        quantity: int,
        client_id: uuid.UUID | None,
        payment_method: str,
        cash_shift_id: uuid.UUID | None,
        payment_parts: tuple[PaymentPart, ...],
    ) -> bool:
        return (
            sale.product_id == product_id
            and sale.quantity == quantity
            and sale.client_id == client_id
            and sale.payment_method.value == payment_method.strip().lower()
            and sale.cash_shift_id == cash_shift_id
            and sale.payment_parts == payment_parts
        )

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
