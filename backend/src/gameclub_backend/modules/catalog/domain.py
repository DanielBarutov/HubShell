import dataclasses
import datetime
import enum
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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


class TariffAudience(enum.StrEnum):
    ALL = "all"
    GUEST = "guest"
    REGISTERED = "registered"


class TariffSaleChannel(enum.StrEnum):
    OPERATOR = "operator"
    SELF_SERVICE = "self_service"
    BOTH = "both"


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
    time_restricted: bool = False
    sale_window_start_minute: int | None = None
    sale_window_end_minute: int | None = None
    usage_window_start_minute: int | None = None
    usage_window_end_minute: int | None = None
    window_timezone: str | None = None
    audience: TariffAudience = TariffAudience.ALL
    sale_channel: TariffSaleChannel = TariffSaleChannel.BOTH

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0:
            raise ValueError("Tariff duration must be positive")
        if self.price_cents < 0 or self.price_per_minute_cents < 0 or self.free_minutes < 0:
            raise ValueError("Tariff prices and free minutes must be non-negative")
        try:
            BillingMode(self.billing_mode)
        except ValueError as error:
            raise ValueError("Invalid tariff billing mode") from error
        try:
            normalized_audience = TariffAudience(self.audience)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid tariff audience") from error
        object.__setattr__(self, "audience", normalized_audience)
        try:
            object.__setattr__(self, "sale_channel", TariffSaleChannel(self.sale_channel))
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid tariff sale channel") from error
        object.__setattr__(
            self,
            "window_timezone",
            self.window_timezone.strip() if self.window_timezone else None,
        )
        sale_window_set = (
            self.sale_window_start_minute is not None or self.sale_window_end_minute is not None
        )
        usage_window_set = (
            self.usage_window_start_minute is not None or self.usage_window_end_minute is not None
        )
        if not self.time_restricted and (
            sale_window_set or usage_window_set or self.window_timezone
        ):
            raise ValueError("Unrestricted tariff cannot have time windows")
        if self.time_restricted and not (sale_window_set and usage_window_set):
            raise ValueError("Restricted tariff requires sale and usage windows")
        self._validate_window(
            self.sale_window_start_minute,
            self.sale_window_end_minute,
            "sale",
        )
        self._validate_window(
            self.usage_window_start_minute,
            self.usage_window_end_minute,
            "usage",
        )
        if self.window_timezone is not None and not self.window_timezone.strip():
            raise ValueError("Tariff time window timezone cannot be empty")
        if self.time_restricted and self.window_timezone is None:
            raise ValueError("Tariff time window timezone is required")
        if self.window_timezone:
            try:
                ZoneInfo(self.window_timezone.strip())
            except ZoneInfoNotFoundError as error:
                raise ValueError("Tariff time window timezone is invalid") from error

    @staticmethod
    def _validate_window(
        start_minute: int | None,
        end_minute: int | None,
        name: str,
    ) -> None:
        if (start_minute is None) != (end_minute is None):
            raise ValueError(f"Tariff {name} window requires both start and end")
        if start_minute is not None:
            assert end_minute is not None
            if not (
                0 <= start_minute < 24 * 60
                and 0 <= end_minute < 24 * 60
                and start_minute != end_minute
            ):
                raise ValueError(f"Tariff {name} window minutes are invalid")

    def is_visible_to(self, moment: datetime.datetime, audience: TariffAudience) -> bool:
        if self.audience not in {TariffAudience.ALL, TariffAudience(audience)}:
            return False
        if not self.time_restricted:
            return True
        return self._is_in_window(
            moment,
            self.sale_window_start_minute,
            self.sale_window_end_minute,
        )

    def is_sellable_through(self, channel: TariffSaleChannel) -> bool:
        return self.sale_channel in {TariffSaleChannel.BOTH, TariffSaleChannel(channel)}

    def is_usable_at(self, moment: datetime.datetime) -> bool:
        if not self.time_restricted:
            return True
        return self._is_in_window(
            moment,
            self.usage_window_start_minute,
            self.usage_window_end_minute,
        )

    def _is_in_window(
        self,
        moment: datetime.datetime,
        start_minute: int | None,
        end_minute: int | None,
    ) -> bool:
        if moment.tzinfo is None:
            raise ValueError("Tariff window time must include timezone")
        if start_minute is None or end_minute is None:
            return True
        local = moment.astimezone(ZoneInfo(self.window_timezone or "UTC"))
        minute = local.hour * 60 + local.minute
        if start_minute < end_minute:
            return start_minute <= minute < end_minute
        return minute >= start_minute or minute < end_minute

    def applies_at(
        self,
        moment: datetime.datetime,
        group_id: str | None,
        audience: TariffAudience = TariffAudience.ALL,
    ) -> bool:
        normalized_group_id = group_id.strip().lower() if group_id else None
        return (
            self.active
            and self.lifecycle is TariffLifecycle.PUBLISHED
            and (self.group_id is None or self.group_id.strip().lower() == normalized_group_id)
            and self.valid_from <= moment
            and (self.valid_to is None or moment < self.valid_to)
            and self.is_visible_to(moment, audience)
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
