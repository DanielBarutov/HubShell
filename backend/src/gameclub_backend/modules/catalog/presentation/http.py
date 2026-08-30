import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import (
    BillingMode,
    CatalogSnapshot,
    DiscountRule,
    Product,
    ProductCategory,
    Quote,
    Tariff,
    TariffLifecycle,
)
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("catalog.manage"))]


class ProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    price_cents: int = Field(ge=0)
    cost_price_cents: int = Field(default=0, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    active: bool = True


class ProductCategoryRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="product", pattern="^(product|drink)$")


class ProductCategoryResponse(BaseModel):
    id: str
    name: str
    kind: str
    active: bool

    @classmethod
    def from_domain(cls, category: ProductCategory) -> "ProductCategoryResponse":
        return cls.model_validate(category, from_attributes=True)


class TariffRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    group_id: str | None = Field(default=None, max_length=128)
    duration_minutes: int = Field(gt=0)
    price_cents: int = Field(ge=0)
    valid_from: datetime.datetime
    valid_to: datetime.datetime | None = None
    tariff_key: str | None = Field(default=None, max_length=128)
    lifecycle: TariffLifecycle = TariffLifecycle.PUBLISHED
    billing_mode: BillingMode = BillingMode.BLOCK
    price_per_minute_cents: int = Field(default=0, ge=0)
    free_minutes: int = Field(default=0, ge=0)


class DiscountRuleRequest(BaseModel):
    category: str = Field(min_length=1, max_length=64)
    percent_bps: int = Field(ge=0, le=10_000)
    priority: int = Field(ge=0)
    valid_from: datetime.datetime
    valid_to: datetime.datetime | None = None


class QuoteRequest(BaseModel):
    duration_minutes: int = Field(gt=0)
    group_id: str | None = None
    moment: datetime.datetime
    discount_category: str | None = Field(default=None, max_length=64)


class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    price_cents: int
    active: bool
    cost_price_cents: int
    stock_quantity: int

    @classmethod
    def from_domain(cls, product: Product) -> "ProductResponse":
        return cls.model_validate(product, from_attributes=True)


class TariffResponse(BaseModel):
    id: uuid.UUID
    name: str
    group_id: str | None
    duration_minutes: int
    price_cents: int
    valid_from: datetime.datetime
    valid_to: datetime.datetime | None
    active: bool
    tariff_key: str
    version: int
    lifecycle: TariffLifecycle
    billing_mode: BillingMode
    price_per_minute_cents: int
    free_minutes: int

    @classmethod
    def from_domain(cls, tariff: Tariff) -> "TariffResponse":
        return cls.model_validate(tariff, from_attributes=True)


class DiscountRuleResponse(BaseModel):
    id: uuid.UUID
    category: str
    percent_bps: int
    priority: int
    valid_from: datetime.datetime
    valid_to: datetime.datetime | None
    active: bool

    @classmethod
    def from_domain(cls, rule: DiscountRule) -> "DiscountRuleResponse":
        return cls.model_validate(rule, from_attributes=True)


class QuoteResponse(BaseModel):
    tariff_id: uuid.UUID
    duration_minutes: int
    price_cents: int
    price_before_discount_cents: int
    discount_amount_cents: int
    discount_percent_bps: int
    discount_category: str | None

    @classmethod
    def from_domain(cls, quote: Quote) -> "QuoteResponse":
        return cls.model_validate(quote, from_attributes=True)


class CatalogSnapshotResponse(BaseModel):
    tariffs: list[TariffResponse]
    discount_rules: list[DiscountRuleResponse]

    @classmethod
    def from_domain(cls, snapshot: CatalogSnapshot) -> "CatalogSnapshotResponse":
        return cls(
            tariffs=[TariffResponse.from_domain(item) for item in snapshot.tariffs],
            discount_rules=[
                DiscountRuleResponse.from_domain(item) for item in snapshot.discount_rules
            ],
        )


def create_router(service: CatalogService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

    @router.get("/categories", response_model=list[ProductCategoryResponse])
    async def list_categories(principal: Operator) -> list[ProductCategoryResponse]:
        del principal
        categories = await service.list_categories()
        return [ProductCategoryResponse.from_domain(item) for item in categories]

    @router.post(
        "/categories",
        response_model=ProductCategoryResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_category(
        body: ProductCategoryRequest,
        principal: Operator,
    ) -> ProductCategoryResponse:
        del principal
        category_id = body.id or body.name
        return ProductCategoryResponse.from_domain(
            await service.create_category(category_id, body.name, body.kind)
        )

    @router.put("/categories/{category_id}", response_model=ProductCategoryResponse)
    async def update_category(
        category_id: str,
        body: ProductCategoryRequest,
        principal: Operator,
    ) -> ProductCategoryResponse:
        del principal
        return ProductCategoryResponse.from_domain(
            await service.update_category(category_id, body.name, body.kind)
        )

    @router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_category(category_id: str, principal: Operator) -> None:
        del principal
        await service.delete_category(category_id)

    @router.get("/products", response_model=list[ProductResponse])
    async def list_products(principal: Operator) -> list[ProductResponse]:
        del principal
        return [ProductResponse.from_domain(item) for item in await service.list_products()]

    @router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
    async def create_product(
        body: ProductRequest,
        principal: Operator,
    ) -> ProductResponse:
        del principal
        return ProductResponse.from_domain(await service.create_product(**body.model_dump()))

    @router.put("/products/{product_id}", response_model=ProductResponse)
    async def update_product(
        product_id: uuid.UUID,
        body: ProductRequest,
        principal: Operator,
    ) -> ProductResponse:
        del principal
        return ProductResponse.from_domain(
            await service.update_product(product_id=product_id, **body.model_dump())
        )

    @router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_product(product_id: uuid.UUID, principal: Operator) -> None:
        del principal
        await service.delete_product(product_id)

    @router.post("/tariffs", response_model=TariffResponse, status_code=status.HTTP_201_CREATED)
    async def create_tariff(
        body: TariffRequest,
        principal: Operator,
    ) -> TariffResponse:
        del principal
        return TariffResponse.from_domain(await service.create_tariff(**body.model_dump()))

    @router.get("/tariffs", response_model=list[TariffResponse])
    async def list_tariffs(principal: Operator) -> list[TariffResponse]:
        del principal
        return [TariffResponse.from_domain(item) for item in await service.list_tariffs()]

    @router.post("/tariffs/{tariff_id}/publish", response_model=TariffResponse)
    async def publish_tariff(
        tariff_id: uuid.UUID,
        principal: Operator,
    ) -> TariffResponse:
        del principal
        return TariffResponse.from_domain(await service.publish_tariff(tariff_id))

    @router.post("/tariffs/{tariff_id}/archive", response_model=TariffResponse)
    async def archive_tariff(
        tariff_id: uuid.UUID,
        principal: Operator,
    ) -> TariffResponse:
        del principal
        return TariffResponse.from_domain(await service.archive_tariff(tariff_id))

    @router.post(
        "/discount-rules",
        response_model=DiscountRuleResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_discount_rule(
        body: DiscountRuleRequest,
        principal: Operator,
    ) -> DiscountRuleResponse:
        del principal
        return DiscountRuleResponse.from_domain(
            await service.create_discount_rule(**body.model_dump())
        )

    @router.get("/discount-rules", response_model=list[DiscountRuleResponse])
    async def list_discount_rules(principal: Operator) -> list[DiscountRuleResponse]:
        del principal
        return [
            DiscountRuleResponse.from_domain(item) for item in await service.list_discount_rules()
        ]

    @router.get("/snapshot", response_model=CatalogSnapshotResponse)
    async def get_snapshot(principal: Operator) -> CatalogSnapshotResponse:
        del principal
        return CatalogSnapshotResponse.from_domain(await service.snapshot())

    @router.post("/quote", response_model=QuoteResponse)
    async def quote(
        body: QuoteRequest,
        principal: Operator,
    ) -> QuoteResponse:
        del principal
        return QuoteResponse.from_domain(await service.quote(**body.model_dump()))

    return router
