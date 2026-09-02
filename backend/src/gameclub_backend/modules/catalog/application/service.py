import datetime
import math
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.catalog.application.ports import CatalogRepository
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


class CatalogService:
    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    async def create_product(
        self,
        name: str,
        category: str,
        price_cents: int,
        cost_price_cents: int = 0,
        stock_quantity: int = 0,
        active: bool = True,
    ) -> Product:
        if (
            not name.strip()
            or not category.strip()
            or price_cents < 0
            or cost_price_cents < 0
            or stock_quantity < 0
        ):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid product data")
        try:
            product = Product(
                id=uuid.uuid4(),
                name=name.strip(),
                category=category.strip(),
                price_cents=price_cents,
                active=active,
                cost_price_cents=cost_price_cents,
                stock_quantity=stock_quantity,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save_product(product)

    async def list_products(self) -> list[Product]:
        return await self._repository.list_products()

    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        return await self._repository.get_product(product_id)

    async def update_product(
        self,
        product_id: uuid.UUID,
        name: str,
        category: str,
        price_cents: int,
        cost_price_cents: int,
        stock_quantity: int,
        active: bool = True,
    ) -> Product:
        current = await self._repository.get_product(product_id)
        if current is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Product not found")
        if (
            not name.strip()
            or not category.strip()
            or price_cents < 0
            or cost_price_cents < 0
            or stock_quantity < 0
        ):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid product data")
        try:
            updated = Product(
                id=current.id,
                name=name.strip(),
                category=category.strip(),
                price_cents=price_cents,
                active=active,
                cost_price_cents=cost_price_cents,
                stock_quantity=stock_quantity,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save_product(updated)

    async def delete_product(self, product_id: uuid.UUID) -> None:
        if await self._repository.get_product(product_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Product not found")
        await self._repository.delete_product(product_id)

    async def create_category(self, category_id: str, name: str, kind: str) -> ProductCategory:
        normalized_id = category_id.strip().lower().replace(" ", "-")
        try:
            category = ProductCategory(normalized_id, name.strip(), kind.strip().lower())
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        if await self._repository.get_category(category.id) is not None:
            raise ApplicationError(ErrorCode.CONFLICT, "Catalog category already exists")
        return await self._repository.save_category(category)

    async def list_categories(self) -> list[ProductCategory]:
        return await self._repository.list_categories()

    async def update_category(self, category_id: str, name: str, kind: str) -> ProductCategory:
        if await self._repository.get_category(category_id.strip().lower()) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Catalog category not found")
        try:
            category = ProductCategory(
                category_id.strip().lower(), name.strip(), kind.strip().lower()
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save_category(category)

    async def delete_category(self, category_id: str) -> None:
        normalized_id = category_id.strip().lower()
        if await self._repository.get_category(normalized_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Catalog category not found")
        if any(
            product.category == normalized_id for product in await self._repository.list_products()
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Catalog category is used by a product",
            )
        await self._repository.delete_category(normalized_id)

    async def create_tariff(
        self,
        name: str,
        group_id: str | None,
        duration_minutes: int,
        price_cents: int,
        valid_from: datetime.datetime,
        valid_to: datetime.datetime | None,
        tariff_key: str | None = None,
        lifecycle: TariffLifecycle = TariffLifecycle.PUBLISHED,
        billing_mode: BillingMode = BillingMode.BLOCK,
        price_per_minute_cents: int = 0,
        free_minutes: int = 0,
        window_start_minute: int | None = None,
        window_end_minute: int | None = None,
        window_timezone: str | None = None,
    ) -> Tariff:
        try:
            lifecycle = TariffLifecycle(lifecycle)
        except (TypeError, ValueError) as error:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Invalid tariff lifecycle"
            ) from error
        try:
            billing_mode = BillingMode(billing_mode)
        except (TypeError, ValueError) as error:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Invalid tariff billing mode",
            ) from error
        if (
            not name.strip()
            or duration_minutes <= 0
            or price_cents < 0
            or price_per_minute_cents < 0
            or free_minutes < 0
        ):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid tariff data")
        if billing_mode is BillingMode.PER_MINUTE and price_per_minute_cents <= 0:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Per-minute tariff must have a positive minute price",
            )
        if valid_from.tzinfo is None or valid_to and valid_to.tzinfo is None:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Tariff dates must include timezone")
        if valid_to and valid_to <= valid_from:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Tariff period is invalid")
        tariff = Tariff(
            id=uuid.uuid4(),
            name=name.strip(),
            group_id=group_id,
            duration_minutes=duration_minutes,
            price_cents=price_cents,
            valid_from=valid_from,
            valid_to=valid_to,
            active=lifecycle is TariffLifecycle.PUBLISHED,
            tariff_key=tariff_key.strip()
            if tariff_key and tariff_key.strip()
            else f"tariff-{uuid.uuid4().hex}",
            lifecycle=lifecycle,
            billing_mode=billing_mode,
            price_per_minute_cents=price_per_minute_cents,
            free_minutes=free_minutes,
            window_start_minute=window_start_minute,
            window_end_minute=window_end_minute,
            window_timezone=window_timezone.strip() if window_timezone else None,
        )
        return await self._repository.create_tariff(tariff)

    async def list_tariffs(self) -> list[Tariff]:
        return await self._repository.list_tariffs()

    async def get_tariff(self, tariff_id: uuid.UUID) -> Tariff | None:
        return await self._repository.get_tariff(tariff_id)

    async def publish_tariff(self, tariff_id: uuid.UUID) -> Tariff:
        tariff = await self._repository.get_tariff(tariff_id)
        if tariff is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Tariff not found")
        try:
            return await self._repository.save_tariff(tariff.publish())
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def archive_tariff(self, tariff_id: uuid.UUID) -> Tariff:
        tariff = await self._repository.get_tariff(tariff_id)
        if tariff is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Tariff not found")
        try:
            return await self._repository.save_tariff(tariff.archive())
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def create_discount_rule(
        self,
        category: str,
        percent_bps: int,
        priority: int,
        valid_from: datetime.datetime,
        valid_to: datetime.datetime | None,
    ) -> DiscountRule:
        normalized_category = category.strip().lower()
        if not normalized_category or percent_bps < 0 or percent_bps > 10_000 or priority < 0:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid discount rule data")
        if valid_from.tzinfo is None or valid_to and valid_to.tzinfo is None:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Discount dates must include timezone"
            )
        if valid_to and valid_to <= valid_from:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Discount period is invalid")
        rule = DiscountRule(
            id=uuid.uuid4(),
            category=normalized_category,
            percent_bps=percent_bps,
            priority=priority,
            valid_from=valid_from,
            valid_to=valid_to,
            active=True,
        )
        return await self._repository.save_discount_rule(rule)

    async def list_discount_rules(self) -> list[DiscountRule]:
        return await self._repository.list_discount_rules()

    async def snapshot(self) -> CatalogSnapshot:
        tariffs = [
            tariff
            for tariff in await self._repository.list_tariffs()
            if tariff.active and tariff.lifecycle is TariffLifecycle.PUBLISHED
        ]
        discount_rules = [
            rule for rule in await self._repository.list_discount_rules() if rule.active
        ]
        return CatalogSnapshot(tuple(tariffs), tuple(discount_rules))

    async def quote(
        self,
        duration_minutes: int,
        group_id: str | None,
        moment: datetime.datetime,
        discount_category: str | None = None,
    ) -> Quote:
        if duration_minutes <= 0 or moment.tzinfo is None:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid quote input")
        tariffs = await self._repository.find_tariffs(group_id, moment)
        matching = [
            tariff
            for tariff in tariffs
            if tariff.billing_mode is BillingMode.PER_MINUTE
            or tariff.duration_minutes >= duration_minutes
        ]
        if not matching:
            raise ApplicationError(ErrorCode.NOT_FOUND, "No applicable tariff found")
        normalized_category = discount_category.strip().lower() if discount_category else None
        rules = await self._repository.find_discount_rules(normalized_category, moment)
        selected_rule = max(
            rules,
            key=lambda item: (item.priority, item.percent_bps, str(item.id)),
            default=None,
        )
        discount_percent_bps = selected_rule.percent_bps if selected_rule else 0
        tariff = min(
            matching,
            key=lambda item: (
                self._gross_price(item, duration_minutes, 1),
                item.duration_minutes,
                str(item.id),
            ),
        )
        price_before_discount_cents = self._gross_price(tariff, duration_minutes, 1)
        discount_amount_cents = price_before_discount_cents * discount_percent_bps // 10_000
        return Quote(
            tariff_id=tariff.id,
            duration_minutes=duration_minutes,
            price_cents=price_before_discount_cents - discount_amount_cents,
            price_before_discount_cents=price_before_discount_cents,
            discount_amount_cents=discount_amount_cents,
            discount_percent_bps=discount_percent_bps,
            discount_category=normalized_category,
        )

    async def quote_for_tariff(
        self,
        tariff_id: uuid.UUID,
        group_id: str | None,
        moment: datetime.datetime,
        discount_category: str | None = None,
        duration_minutes: int | None = None,
        quantity: int = 1,
    ) -> Quote:
        if moment.tzinfo is None:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid quote input")
        tariff = await self._repository.get_tariff(tariff_id)
        if tariff is None or not tariff.applies_at(moment, group_id):
            raise ApplicationError(ErrorCode.NOT_FOUND, "Selected tariff is not applicable")
        if quantity <= 0 or duration_minutes is not None and duration_minutes <= 0:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid tariff quote quantity")
        normalized_category = discount_category.strip().lower() if discount_category else None
        rules = await self._repository.find_discount_rules(normalized_category, moment)
        selected_rule = max(
            rules,
            key=lambda item: (item.priority, item.percent_bps, str(item.id)),
            default=None,
        )
        discount_percent_bps = selected_rule.percent_bps if selected_rule else 0
        quoted_duration = duration_minutes or tariff.duration_minutes * quantity
        price_before_discount_cents = self._gross_price(tariff, quoted_duration, quantity)
        discount_amount_cents = price_before_discount_cents * discount_percent_bps // 10_000
        return Quote(
            tariff_id=tariff.id,
            duration_minutes=quoted_duration,
            price_cents=price_before_discount_cents - discount_amount_cents,
            price_before_discount_cents=price_before_discount_cents,
            discount_amount_cents=discount_amount_cents,
            discount_percent_bps=discount_percent_bps,
            discount_category=normalized_category,
        )

    @staticmethod
    def _gross_price(tariff: Tariff, duration_minutes: int, quantity: int) -> int:
        if tariff.billing_mode is BillingMode.PER_MINUTE:
            billable_minutes = max(0, duration_minutes - tariff.free_minutes)
            return billable_minutes * tariff.price_per_minute_cents
        units = max(quantity, math.ceil(duration_minutes / tariff.duration_minutes))
        return tariff.price_cents * units
