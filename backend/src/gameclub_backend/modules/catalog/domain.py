import dataclasses
import datetime
import enum
import uuid


@dataclasses.dataclass(frozen=True)
class ProductCategory:
    id: str
    name: str
    kind: str = "product"
    active: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("Category id and name are required")
        if self.kind not in {"product", "drink"}:
            raise ValueError("Category kind must be product or drink")


@dataclasses.dataclass(frozen=True)
class Product:
    id: uuid.UUID
    name: str
    category: str
    price_cents: int
    active: bool = True
    cost_price_cents: int = 0
    stock_quantity: int = 0

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.category.strip():
            raise ValueError("Product name and category are required")
        if self.price_cents < 0 or self.cost_price_cents < 0 or self.stock_quantity < 0:
            raise ValueError("Product prices and stock must be non-negative")


class TariffLifecycle(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class BillingMode(enum.StrEnum):
    BLOCK = "block"
    PER_MINUTE = "per_minute"


@dataclasses.dataclass(frozen=True)
class Tariff:
    id: uuid.UUID
    name: str
    group_id: str | None
    duration_minutes: int
    price_cents: int
    valid_from: datetime.datetime
    valid_to: datetime.datetime | None
    active: bool
    tariff_key: str = ""
    version: int = 1
    lifecycle: TariffLifecycle = TariffLifecycle.PUBLISHED
    billing_mode: BillingMode = BillingMode.BLOCK
    price_per_minute_cents: int = 0
    free_minutes: int = 0

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0:
            raise ValueError("Tariff duration must be positive")
        if self.price_cents < 0 or self.price_per_minute_cents < 0 or self.free_minutes < 0:
            raise ValueError("Tariff prices and free minutes must be non-negative")
        try:
            BillingMode(self.billing_mode)
        except ValueError as error:
            raise ValueError("Invalid tariff billing mode") from error

    def applies_at(self, moment: datetime.datetime, group_id: str | None) -> bool:
        return (
            self.active
            and self.lifecycle is TariffLifecycle.PUBLISHED
            and (self.group_id is None or self.group_id == group_id)
            and self.valid_from <= moment
            and (self.valid_to is None or moment < self.valid_to)
        )

    def publish(self) -> "Tariff":
        if self.lifecycle is TariffLifecycle.ARCHIVED:
            raise ValueError("Archived tariff cannot be published")
        return dataclasses.replace(
            self,
            active=True,
            lifecycle=TariffLifecycle.PUBLISHED,
        )

    def archive(self) -> "Tariff":
        if self.lifecycle is TariffLifecycle.ARCHIVED:
            return self
        return dataclasses.replace(
            self,
            active=False,
            lifecycle=TariffLifecycle.ARCHIVED,
        )


@dataclasses.dataclass(frozen=True)
class DiscountRule:
    id: uuid.UUID
    category: str
    percent_bps: int
    priority: int
    valid_from: datetime.datetime
    valid_to: datetime.datetime | None
    active: bool

    def applies_at(self, moment: datetime.datetime, category: str | None) -> bool:
        return (
            self.active
            and category is not None
            and self.category == category
            and self.valid_from <= moment
            and (self.valid_to is None or moment < self.valid_to)
        )


@dataclasses.dataclass(frozen=True)
class CatalogSnapshot:
    tariffs: tuple[Tariff, ...]
    discount_rules: tuple[DiscountRule, ...]


@dataclasses.dataclass(frozen=True)
class Quote:
    tariff_id: uuid.UUID
    duration_minutes: int
    price_cents: int
    price_before_discount_cents: int
    discount_amount_cents: int
    discount_percent_bps: int
    discount_category: str | None

    @property
    def is_free(self) -> bool:
        return self.price_cents == 0
