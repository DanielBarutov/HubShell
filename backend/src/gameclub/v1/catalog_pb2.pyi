import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BillingMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BILLING_MODE_UNSPECIFIED: _ClassVar[BillingMode]
    BILLING_MODE_BLOCK: _ClassVar[BillingMode]
    BILLING_MODE_PER_MINUTE: _ClassVar[BillingMode]

class TariffLifecycle(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TARIFF_LIFECYCLE_UNSPECIFIED: _ClassVar[TariffLifecycle]
    TARIFF_LIFECYCLE_DRAFT: _ClassVar[TariffLifecycle]
    TARIFF_LIFECYCLE_PUBLISHED: _ClassVar[TariffLifecycle]
    TARIFF_LIFECYCLE_ARCHIVED: _ClassVar[TariffLifecycle]
BILLING_MODE_UNSPECIFIED: BillingMode
BILLING_MODE_BLOCK: BillingMode
BILLING_MODE_PER_MINUTE: BillingMode
TARIFF_LIFECYCLE_UNSPECIFIED: TariffLifecycle
TARIFF_LIFECYCLE_DRAFT: TariffLifecycle
TARIFF_LIFECYCLE_PUBLISHED: TariffLifecycle
TARIFF_LIFECYCLE_ARCHIVED: TariffLifecycle

class Product(_message.Message):
    __slots__ = ("id", "name", "category", "price_cents", "active", "cost_price_cents", "stock_quantity")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    COST_PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    STOCK_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    category: str
    price_cents: int
    active: bool
    cost_price_cents: int
    stock_quantity: int
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., category: _Optional[str] = ..., price_cents: _Optional[int] = ..., active: _Optional[bool] = ..., cost_price_cents: _Optional[int] = ..., stock_quantity: _Optional[int] = ...) -> None: ...

class CreateProductRequest(_message.Message):
    __slots__ = ("name", "category", "price_cents", "cost_price_cents", "stock_quantity", "active")
    NAME_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    COST_PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    STOCK_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    name: str
    category: str
    price_cents: int
    cost_price_cents: int
    stock_quantity: int
    active: bool
    def __init__(self, name: _Optional[str] = ..., category: _Optional[str] = ..., price_cents: _Optional[int] = ..., cost_price_cents: _Optional[int] = ..., stock_quantity: _Optional[int] = ..., active: _Optional[bool] = ...) -> None: ...

class ListProductsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListProductsResponse(_message.Message):
    __slots__ = ("products",)
    PRODUCTS_FIELD_NUMBER: _ClassVar[int]
    products: _containers.RepeatedCompositeFieldContainer[Product]
    def __init__(self, products: _Optional[_Iterable[_Union[Product, _Mapping]]] = ...) -> None: ...

class Tariff(_message.Message):
    __slots__ = ("id", "name", "group_id", "duration_minutes", "price_cents", "valid_from", "valid_to", "active", "tariff_key", "version", "lifecycle", "billing_mode", "price_per_minute_cents", "free_minutes", "window_start_minute", "window_end_minute", "window_timezone")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    VALID_FROM_FIELD_NUMBER: _ClassVar[int]
    VALID_TO_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    TARIFF_KEY_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    LIFECYCLE_FIELD_NUMBER: _ClassVar[int]
    BILLING_MODE_FIELD_NUMBER: _ClassVar[int]
    PRICE_PER_MINUTE_CENTS_FIELD_NUMBER: _ClassVar[int]
    FREE_MINUTES_FIELD_NUMBER: _ClassVar[int]
    WINDOW_START_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_END_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    group_id: str
    duration_minutes: int
    price_cents: int
    valid_from: _timestamp_pb2.Timestamp
    valid_to: _timestamp_pb2.Timestamp
    active: bool
    tariff_key: str
    version: int
    lifecycle: TariffLifecycle
    billing_mode: BillingMode
    price_per_minute_cents: int
    free_minutes: int
    window_start_minute: int
    window_end_minute: int
    window_timezone: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., group_id: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., price_cents: _Optional[int] = ..., valid_from: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., valid_to: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., active: _Optional[bool] = ..., tariff_key: _Optional[str] = ..., version: _Optional[int] = ..., lifecycle: _Optional[_Union[TariffLifecycle, str]] = ..., billing_mode: _Optional[_Union[BillingMode, str]] = ..., price_per_minute_cents: _Optional[int] = ..., free_minutes: _Optional[int] = ..., window_start_minute: _Optional[int] = ..., window_end_minute: _Optional[int] = ..., window_timezone: _Optional[str] = ...) -> None: ...

class CreateTariffRequest(_message.Message):
    __slots__ = ("name", "group_id", "duration_minutes", "price_cents", "valid_from", "valid_to", "tariff_key", "lifecycle", "billing_mode", "price_per_minute_cents", "free_minutes", "window_start_minute", "window_end_minute", "window_timezone")
    NAME_FIELD_NUMBER: _ClassVar[int]
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    VALID_FROM_FIELD_NUMBER: _ClassVar[int]
    VALID_TO_FIELD_NUMBER: _ClassVar[int]
    TARIFF_KEY_FIELD_NUMBER: _ClassVar[int]
    LIFECYCLE_FIELD_NUMBER: _ClassVar[int]
    BILLING_MODE_FIELD_NUMBER: _ClassVar[int]
    PRICE_PER_MINUTE_CENTS_FIELD_NUMBER: _ClassVar[int]
    FREE_MINUTES_FIELD_NUMBER: _ClassVar[int]
    WINDOW_START_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_END_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    name: str
    group_id: str
    duration_minutes: int
    price_cents: int
    valid_from: _timestamp_pb2.Timestamp
    valid_to: _timestamp_pb2.Timestamp
    tariff_key: str
    lifecycle: TariffLifecycle
    billing_mode: BillingMode
    price_per_minute_cents: int
    free_minutes: int
    window_start_minute: int
    window_end_minute: int
    window_timezone: str
    def __init__(self, name: _Optional[str] = ..., group_id: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., price_cents: _Optional[int] = ..., valid_from: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., valid_to: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., tariff_key: _Optional[str] = ..., lifecycle: _Optional[_Union[TariffLifecycle, str]] = ..., billing_mode: _Optional[_Union[BillingMode, str]] = ..., price_per_minute_cents: _Optional[int] = ..., free_minutes: _Optional[int] = ..., window_start_minute: _Optional[int] = ..., window_end_minute: _Optional[int] = ..., window_timezone: _Optional[str] = ...) -> None: ...

class ListTariffsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListTariffsResponse(_message.Message):
    __slots__ = ("tariffs",)
    TARIFFS_FIELD_NUMBER: _ClassVar[int]
    tariffs: _containers.RepeatedCompositeFieldContainer[Tariff]
    def __init__(self, tariffs: _Optional[_Iterable[_Union[Tariff, _Mapping]]] = ...) -> None: ...

class PublishTariffRequest(_message.Message):
    __slots__ = ("tariff_id",)
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    tariff_id: str
    def __init__(self, tariff_id: _Optional[str] = ...) -> None: ...

class ArchiveTariffRequest(_message.Message):
    __slots__ = ("tariff_id",)
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    tariff_id: str
    def __init__(self, tariff_id: _Optional[str] = ...) -> None: ...

class DiscountRule(_message.Message):
    __slots__ = ("id", "category", "percent_bps", "priority", "valid_from", "valid_to", "active")
    ID_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    PERCENT_BPS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    VALID_FROM_FIELD_NUMBER: _ClassVar[int]
    VALID_TO_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    id: str
    category: str
    percent_bps: int
    priority: int
    valid_from: _timestamp_pb2.Timestamp
    valid_to: _timestamp_pb2.Timestamp
    active: bool
    def __init__(self, id: _Optional[str] = ..., category: _Optional[str] = ..., percent_bps: _Optional[int] = ..., priority: _Optional[int] = ..., valid_from: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., valid_to: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., active: _Optional[bool] = ...) -> None: ...

class CreateDiscountRuleRequest(_message.Message):
    __slots__ = ("category", "percent_bps", "priority", "valid_from", "valid_to")
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    PERCENT_BPS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    VALID_FROM_FIELD_NUMBER: _ClassVar[int]
    VALID_TO_FIELD_NUMBER: _ClassVar[int]
    category: str
    percent_bps: int
    priority: int
    valid_from: _timestamp_pb2.Timestamp
    valid_to: _timestamp_pb2.Timestamp
    def __init__(self, category: _Optional[str] = ..., percent_bps: _Optional[int] = ..., priority: _Optional[int] = ..., valid_from: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., valid_to: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ListDiscountRulesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListDiscountRulesResponse(_message.Message):
    __slots__ = ("rules",)
    RULES_FIELD_NUMBER: _ClassVar[int]
    rules: _containers.RepeatedCompositeFieldContainer[DiscountRule]
    def __init__(self, rules: _Optional[_Iterable[_Union[DiscountRule, _Mapping]]] = ...) -> None: ...

class GetCatalogSnapshotRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CatalogSnapshot(_message.Message):
    __slots__ = ("tariffs", "discount_rules")
    TARIFFS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_RULES_FIELD_NUMBER: _ClassVar[int]
    tariffs: _containers.RepeatedCompositeFieldContainer[Tariff]
    discount_rules: _containers.RepeatedCompositeFieldContainer[DiscountRule]
    def __init__(self, tariffs: _Optional[_Iterable[_Union[Tariff, _Mapping]]] = ..., discount_rules: _Optional[_Iterable[_Union[DiscountRule, _Mapping]]] = ...) -> None: ...

class QuoteRequest(_message.Message):
    __slots__ = ("duration_minutes", "group_id", "moment", "discount_category")
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    MOMENT_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    duration_minutes: int
    group_id: str
    moment: _timestamp_pb2.Timestamp
    discount_category: str
    def __init__(self, duration_minutes: _Optional[int] = ..., group_id: _Optional[str] = ..., moment: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., discount_category: _Optional[str] = ...) -> None: ...

class QuoteResponse(_message.Message):
    __slots__ = ("tariff_id", "duration_minutes", "price_cents", "price_before_discount_cents", "discount_amount_cents", "discount_percent_bps", "discount_category")
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRICE_BEFORE_DISCOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_PERCENT_BPS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    tariff_id: str
    duration_minutes: int
    price_cents: int
    price_before_discount_cents: int
    discount_amount_cents: int
    discount_percent_bps: int
    discount_category: str
    def __init__(self, tariff_id: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., price_cents: _Optional[int] = ..., price_before_discount_cents: _Optional[int] = ..., discount_amount_cents: _Optional[int] = ..., discount_percent_bps: _Optional[int] = ..., discount_category: _Optional[str] = ...) -> None: ...
