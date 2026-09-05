import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.payment_methods.domain import PaymentPart
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.domain import ProductSale
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("sales.manage"))]


class ProductSaleRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0, le=10_000)
    client_id: uuid.UUID | None = None
    payment_method: str = Field(pattern="^(balance|cash|transfer|mixed)$")
    cash_shift_id: uuid.UUID | None = None
    payment_parts: list["PaymentPartRequest"] = Field(default_factory=list)


class PaymentPartRequest(BaseModel):
    method: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=256)


class PaymentPartResponse(BaseModel):
    method: str
    amount_cents: int
    reference: str | None

    @classmethod
    def from_domain(cls, part: PaymentPart) -> "PaymentPartResponse":
        return cls(
            method=part.method,
            amount_cents=part.amount_cents,
            reference=part.reference,
        )


class ProductSaleResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    product_category: str
    client_id: uuid.UUID | None
    guest_name: str | None
    quantity: int
    unit_price_cents: int
    unit_cost_price_cents: int
    total_price_cents: int
    total_cost_price_cents: int
    payment_method: str
    cash_shift_id: uuid.UUID | None
    status: str
    sold_by: str
    idempotency_key: str
    created_at: datetime.datetime
    completed_at: datetime.datetime | None
    payment_parts: list[PaymentPartResponse]
    settlement_error: str | None
    attempts: int
    next_attempt_at: datetime.datetime

    @classmethod
    def from_domain(cls, sale: ProductSale) -> "ProductSaleResponse":
        return cls(
            id=sale.id,
            product_id=sale.product_id,
            product_name=sale.product_name,
            product_category=sale.product_category,
            client_id=sale.client_id,
            guest_name=sale.guest_name,
            quantity=sale.quantity,
            unit_price_cents=sale.unit_price_cents,
            unit_cost_price_cents=sale.unit_cost_price_cents,
            total_price_cents=sale.total_price_cents,
            total_cost_price_cents=sale.total_cost_price_cents,
            payment_method=sale.payment_method.value,
            cash_shift_id=sale.cash_shift_id,
            status=sale.status.value,
            sold_by=sale.sold_by,
            idempotency_key=sale.idempotency_key,
            created_at=sale.created_at,
            completed_at=sale.completed_at,
            payment_parts=[PaymentPartResponse.from_domain(part) for part in sale.payment_parts],
            settlement_error=sale.settlement_error,
            attempts=sale.attempts,
            next_attempt_at=sale.next_attempt_at,
        )


def create_router(service: ProductSaleService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/sales", tags=["sales"])

    @router.post("", response_model=ProductSaleResponse, status_code=status.HTTP_201_CREATED)
    async def sell_product(
        body: ProductSaleRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> ProductSaleResponse:
        sale = await service.sell(
            product_id=body.product_id,
            quantity=body.quantity,
            client_id=body.client_id,
            payment_method=body.payment_method,
            cash_shift_id=body.cash_shift_id,
            sold_by=principal.subject_id,
            idempotency_key=idempotency_key,
            payment_parts=[part.model_dump() for part in body.payment_parts],
        )
        return ProductSaleResponse.from_domain(sale)

    @router.get("", response_model=list[ProductSaleResponse])
    async def list_sales(
        principal: Operator,
        start_at: typing.Annotated[datetime.datetime | None, Query()] = None,
        end_at: typing.Annotated[datetime.datetime | None, Query()] = None,
        client_id: typing.Annotated[uuid.UUID | None, Query()] = None,
        limit: typing.Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[ProductSaleResponse]:
        del principal
        sales = await service.list_sales(start_at, end_at, client_id, limit)
        return [ProductSaleResponse.from_domain(sale) for sale in sales]

    @router.post("/{sale_id}/reconcile", response_model=ProductSaleResponse)
    async def reconcile_sale(
        sale_id: uuid.UUID,
        principal: typing.Annotated[
            Principal,
            Depends(require_permissions("sales.manage", "cashier.supervise")),
        ],
    ) -> ProductSaleResponse:
        del principal
        return ProductSaleResponse.from_domain(await service.reconcile(sale_id))

    return router
