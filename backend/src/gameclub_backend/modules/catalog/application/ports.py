import datetime
import typing
import uuid

from gameclub_backend.modules.catalog.domain import DiscountRule, Product, ProductCategory, Tariff


class CatalogRepository(typing.Protocol):
    async def save_category(self, category: ProductCategory) -> ProductCategory:
        """Persist a product or drink category."""

    async def list_categories(self) -> list[ProductCategory]:
        """Return catalog categories."""

    async def get_category(self, category_id: str) -> ProductCategory | None:
        """Return a catalog category by stable key."""

    async def delete_category(self, category_id: str) -> None:
        """Delete a catalog category."""

    async def save_product(self, product: Product) -> Product:
        """Persist a product."""

    async def list_products(self) -> list[Product]:
        """Return all products."""

    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        """Return a product by ID."""

    async def delete_product(self, product_id: uuid.UUID) -> None:
        """Remove a product from the catalog."""

    async def save_tariff(self, tariff: Tariff) -> Tariff:
        """Persist a tariff."""

    async def create_tariff(self, tariff: Tariff) -> Tariff:
        """Create an immutable tariff version and assign its next version number."""

    async def list_tariffs(self) -> list[Tariff]:
        """Return all tariffs ordered for operator display."""

    async def get_tariff(self, tariff_id: uuid.UUID) -> Tariff | None:
        """Return a tariff by ID."""

    async def find_tariffs(
        self,
        group_id: str | None,
        moment: datetime.datetime,
    ) -> list[Tariff]:
        """Return tariffs applicable at a moment."""

    async def save_discount_rule(self, rule: DiscountRule) -> DiscountRule:
        """Persist an extensible discount rule."""

    async def list_discount_rules(self) -> list[DiscountRule]:
        """Return discount rules ordered for operator display."""

    async def find_discount_rules(
        self,
        category: str | None,
        moment: datetime.datetime,
    ) -> list[DiscountRule]:
        """Return discount rules applicable at a moment."""
