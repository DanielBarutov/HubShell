from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.payment_methods.domain import PaymentPart
from gameclub_backend.modules.sales.domain import (
    ProductPaymentMethod,
    ProductSale,
    ProductSaleStatus,
)


class SalesBase(DeclarativeBase):
    pass


class ProductSaleModel(SalesBase):
    __tablename__ = "product_sales"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    product_name: Mapped[str] = mapped_column(String(128))
    product_category: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    guest_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer())
    unit_price_cents: Mapped[int] = mapped_column()
    unit_cost_price_cents: Mapped[int] = mapped_column()
    total_price_cents: Mapped[int] = mapped_column()
    total_cost_price_cents: Mapped[int] = mapped_column()
    payment_method: Mapped[str] = mapped_column(String(16))
    cash_shift_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    sold_by: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_parts: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    settlement_error: Mapped[str | None] = mapped_column(String(1_000), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    def to_domain(self) -> ProductSale:
        return ProductSale(
            id=self.id,
            product_id=self.product_id,
            product_name=self.product_name,
            product_category=self.product_category,
            client_id=self.client_id,
            guest_name=self.guest_name,
            quantity=self.quantity,
            unit_price_cents=self.unit_price_cents,
            unit_cost_price_cents=self.unit_cost_price_cents,
            total_price_cents=self.total_price_cents,
            total_cost_price_cents=self.total_cost_price_cents,
            payment_method=ProductPaymentMethod(self.payment_method),
            cash_shift_id=self.cash_shift_id,
            status=ProductSaleStatus(self.status),
            sold_by=self.sold_by,
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
            completed_at=self.completed_at,
            payment_parts=tuple(PaymentPart.from_dict(part) for part in (self.payment_parts or [])),
            settlement_error=self.settlement_error,
            attempts=self.attempts,
            next_attempt_at=self.next_attempt_at,
        )

    @classmethod
    def from_domain(cls, sale: ProductSale) -> ProductSaleModel:
        return cls(
            **{
                key: value
                for key, value in {
                    "id": sale.id,
                    "product_id": sale.product_id,
                    "product_name": sale.product_name,
                    "product_category": sale.product_category,
                    "client_id": sale.client_id,
                    "guest_name": sale.guest_name,
                    "quantity": sale.quantity,
                    "unit_price_cents": sale.unit_price_cents,
                    "unit_cost_price_cents": sale.unit_cost_price_cents,
                    "total_price_cents": sale.total_price_cents,
                    "total_cost_price_cents": sale.total_cost_price_cents,
                    "payment_method": sale.payment_method.value,
                    "cash_shift_id": sale.cash_shift_id,
                    "status": sale.status.value,
                    "sold_by": sale.sold_by,
                    "idempotency_key": sale.idempotency_key,
                    "created_at": sale.created_at,
                    "completed_at": sale.completed_at,
                    "payment_parts": [part.as_dict() for part in sale.payment_parts],
                    "settlement_error": sale.settlement_error,
                    "attempts": sale.attempts,
                    "next_attempt_at": sale.next_attempt_at,
                }.items()
            }
        )


class PostgresProductSaleRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get_by_idempotency_key(self, idempotency_key: str) -> ProductSale | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(ProductSaleModel).where(ProductSaleModel.idempotency_key == idempotency_key)
            )
            return model.to_domain() if model else None

    async def get_by_id(self, sale_id: uuid.UUID) -> ProductSale | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ProductSaleModel, sale_id)
            return model.to_domain() if model else None

    async def create_pending(self, sale: ProductSale) -> ProductSale:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"product-sale:{sale.idempotency_key}"},
                )
                existing = await session.scalar(
                    select(ProductSaleModel).where(
                        ProductSaleModel.idempotency_key == sale.idempotency_key
                    )
                )
                if existing is not None:
                    return existing.to_domain()
                product = (
                    (
                        await session.execute(
                            text(
                                "SELECT price_cents, cost_price_cents, stock_quantity, active "
                                "FROM products WHERE id = :product_id FOR UPDATE"
                            ),
                            {"product_id": sale.product_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if product is None:
                    raise ValueError("Product not found")
                if not product["active"]:
                    raise ValueError("Product is inactive")
                if product["stock_quantity"] < sale.quantity:
                    raise ValueError("Insufficient product stock")
                if (
                    product["price_cents"] != sale.unit_price_cents
                    or product["cost_price_cents"] != sale.unit_cost_price_cents
                ):
                    raise ValueError("Product price changed, retry the sale")
                session.add(ProductSaleModel.from_domain(sale))
                await session.execute(
                    text(
                        "UPDATE products SET stock_quantity = stock_quantity - :quantity "
                        "WHERE id = :product_id"
                    ),
                    {"quantity": sale.quantity, "product_id": sale.product_id},
                )
                return sale

    async def complete(self, sale: ProductSale) -> ProductSale:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.get(ProductSaleModel, sale.id, with_for_update=True)
                if model is None:
                    raise ValueError("Product sale not found")
                if model.status == ProductSaleStatus.COMPLETED.value:
                    return model.to_domain()
                if model.status != ProductSaleStatus.PENDING.value:
                    raise ValueError("Product sale is not pending")
                model.status = ProductSaleStatus.COMPLETED.value
                model.completed_at = sale.completed_at
                return model.to_domain()

    async def cancel(self, sale: ProductSale) -> ProductSale:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.get(ProductSaleModel, sale.id, with_for_update=True)
                if model is None:
                    raise ValueError("Product sale not found")
                if model.status == ProductSaleStatus.CANCELLED.value:
                    return model.to_domain()
                if model.status == ProductSaleStatus.COMPLETED.value:
                    return model.to_domain()
                await session.execute(
                    text(
                        "UPDATE products SET stock_quantity = stock_quantity + :quantity "
                        "WHERE id = :product_id"
                    ),
                    {"quantity": model.quantity, "product_id": model.product_id},
                )
                model.status = ProductSaleStatus.CANCELLED.value
                return model.to_domain()

    async def mark_needs_review(
        self,
        sale: ProductSale,
        error: str,
        now: datetime.datetime | None = None,
    ) -> ProductSale:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.get(ProductSaleModel, sale.id, with_for_update=True)
                if model is None:
                    raise ValueError("Product sale not found")
                if model.status == ProductSaleStatus.COMPLETED.value:
                    return model.to_domain()
                reviewed = model.to_domain().needs_review(error, now)
                model.status = reviewed.status.value
                model.settlement_error = reviewed.settlement_error
                model.attempts = reviewed.attempts
                model.next_attempt_at = reviewed.next_attempt_at
                return reviewed

    async def mark_retryable(
        self,
        sale: ProductSale,
        error: str,
        now: datetime.datetime,
    ) -> ProductSale:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.get(ProductSaleModel, sale.id, with_for_update=True)
                if model is None:
                    raise ValueError("Product sale not found")
                if model.status == ProductSaleStatus.COMPLETED.value:
                    return model.to_domain()
                retryable = model.to_domain().schedule_retry(error, now)
                model.status = retryable.status.value
                model.attempts = retryable.attempts
                model.next_attempt_at = retryable.next_attempt_at
                model.settlement_error = retryable.settlement_error
                return retryable

    async def reopen_for_reconciliation(
        self,
        sale: ProductSale,
        now: datetime.datetime,
    ) -> ProductSale:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.get(ProductSaleModel, sale.id, with_for_update=True)
                if model is None:
                    raise ValueError("Product sale not found")
                if model.status == ProductSaleStatus.COMPLETED.value:
                    return model.to_domain()
                reopened = model.to_domain().reopen_for_review(now)
                model.status = reopened.status.value
                model.next_attempt_at = reopened.next_attempt_at
                model.settlement_error = reopened.settlement_error
                return reopened

    async def list_sales(
        self,
        start_at: datetime.datetime | None = None,
        end_at: datetime.datetime | None = None,
        client_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[ProductSale]:
        filters = [
            ProductSaleModel.status.in_(
                [ProductSaleStatus.COMPLETED.value, ProductSaleStatus.NEEDS_REVIEW.value]
            )
        ]
        if start_at is not None:
            filters.append(ProductSaleModel.created_at >= start_at)
        if end_at is not None:
            filters.append(ProductSaleModel.created_at < end_at)
        if client_id is not None:
            filters.append(ProductSaleModel.client_id == client_id)
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ProductSaleModel)
                .where(*filters)
                .order_by(ProductSaleModel.created_at.desc())
                .limit(max(1, min(limit, 500)))
            )
            return [model.to_domain() for model in result]

    async def list_recoverable(
        self,
        limit: int = 100,
        now: datetime.datetime | None = None,
    ) -> list[ProductSale]:
        moment = now or datetime.datetime.now(datetime.UTC)
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ProductSaleModel)
                .where(
                    ProductSaleModel.status == ProductSaleStatus.PENDING.value,
                    ProductSaleModel.next_attempt_at <= moment,
                )
                .order_by(ProductSaleModel.created_at)
                .limit(max(1, min(limit, 500)))
            )
            return [model.to_domain() for model in result]
