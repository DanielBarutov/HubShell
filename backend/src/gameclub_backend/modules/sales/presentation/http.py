import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.domain import ProductSale
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("sales.manage"))]


class ProductSaleRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0, le=10_000)
    client_id: uuid.UUID | None = None
    payment_method: str = Field(pattern="^(balance|cash)$")
    cash_shift_id: uuid.UUID | None = None


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

    return router
