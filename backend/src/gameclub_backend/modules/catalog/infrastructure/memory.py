import asyncio
import dataclasses
import datetime
import uuid

from gameclub_backend.modules.catalog.domain import DiscountRule, Product, ProductCategory, Tariff


class InMemoryCatalogRepository:
    def __init__(self) -> None:
        self._products: dict[uuid.UUID, Product] = {}
        self._categories: dict[str, ProductCategory] = {}
        self._tariffs: dict[uuid.UUID, Tariff] = {}
        self._discount_rules: dict[uuid.UUID, DiscountRule] = {}
        self._product_lock = asyncio.Lock()
        self._tariff_lock = asyncio.Lock()

    async def save_product(self, product: Product) -> Product:
        self._products[product.id] = product
        return product

    async def list_products(self) -> list[Product]:
        return sorted(self._products.values(), key=lambda item: item.name.lower())

    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        return self._products.get(product_id)

    async def delete_product(self, product_id: uuid.UUID) -> None:
        self._products.pop(product_id, None)

    async def reserve_stock(
        self,
        product_id: uuid.UUID,
        quantity: int,
        expected_price_cents: int,
        expected_cost_price_cents: int,
    ) -> None:
        async with self._product_lock:
            product = self._products.get(product_id)
            if product is None:
                raise ValueError("Product not found")
            if not product.active:
                raise ValueError("Product is inactive")
            if product.stock_quantity < quantity:
                raise ValueError("Insufficient product stock")
            if (
                product.price_cents != expected_price_cents
                or product.cost_price_cents != expected_cost_price_cents
            ):
                raise ValueError("Product price changed, retry the sale")
            self._products[product_id] = dataclasses.replace(
                product,
                stock_quantity=product.stock_quantity - quantity,
            )

    async def release_stock(self, product_id: uuid.UUID, quantity: int) -> None:
        async with self._product_lock:
            product = self._products.get(product_id)
            if product is not None:
                self._products[product_id] = dataclasses.replace(
                    product,
                    stock_quantity=product.stock_quantity + quantity,
                )

    async def save_category(self, category: ProductCategory) -> ProductCategory:
        self._categories[category.id] = category
        return category

    async def list_categories(self) -> list[ProductCategory]:
        return sorted(self._categories.values(), key=lambda item: item.name.lower())

    async def get_category(self, category_id: str) -> ProductCategory | None:
        return self._categories.get(category_id)

    async def delete_category(self, category_id: str) -> None:
        self._categories.pop(category_id, None)

    async def save_tariff(self, tariff: Tariff) -> Tariff:
        self._tariffs[tariff.id] = tariff
        return tariff

    async def create_tariff(self, tariff: Tariff) -> Tariff:
        async with self._tariff_lock:
            next_version = (
                max(
                    (
                        item.version
                        for item in self._tariffs.values()
                        if item.tariff_key == tariff.tariff_key
                    ),
                    default=0,
                )
                + 1
            )
            created = dataclasses.replace(tariff, version=next_version)
            self._tariffs[created.id] = created
            return created

    async def list_tariffs(self) -> list[Tariff]:
        return sorted(
            self._tariffs.values(), key=lambda item: (item.name.lower(), item.duration_minutes)
        )

    async def get_tariff(self, tariff_id: uuid.UUID) -> Tariff | None:
        return self._tariffs.get(tariff_id)

    async def find_tariffs(
        self,
        group_id: str | None,
        moment: datetime.datetime,
    ) -> list[Tariff]:
        return [tariff for tariff in self._tariffs.values() if tariff.applies_at(moment, group_id)]

    async def save_discount_rule(self, rule: DiscountRule) -> DiscountRule:
        self._discount_rules[rule.id] = rule
        return rule

    async def list_discount_rules(self) -> list[DiscountRule]:
        return sorted(
            self._discount_rules.values(),
            key=lambda item: (-item.priority, item.category, str(item.id)),
        )

    async def find_discount_rules(
        self,
        category: str | None,
        moment: datetime.datetime,
    ) -> list[DiscountRule]:
        return [rule for rule in self._discount_rules.values() if rule.applies_at(moment, category)]
