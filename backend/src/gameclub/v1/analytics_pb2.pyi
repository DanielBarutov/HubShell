import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetAnalyticsOverviewRequest(_message.Message):
    __slots__ = ("start_at", "end_at", "limit")
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    limit: int
    def __init__(self, start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., limit: _Optional[int] = ...) -> None: ...

class GetClientAnalyticsRequest(_message.Message):
    __slots__ = ("client_id", "start_at", "end_at", "limit")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    limit: int
    def __init__(self, client_id: _Optional[str] = ..., start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., limit: _Optional[int] = ...) -> None: ...

class AnalyticsTopProduct(_message.Message):
    __slots__ = ("product_id", "product_name", "units", "revenue_cents", "gross_profit_cents")
    PRODUCT_ID_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_NAME_FIELD_NUMBER: _ClassVar[int]
    UNITS_FIELD_NUMBER: _ClassVar[int]
    REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    GROSS_PROFIT_CENTS_FIELD_NUMBER: _ClassVar[int]
    product_id: str
    product_name: str
    units: int
    revenue_cents: int
    gross_profit_cents: int
    def __init__(self, product_id: _Optional[str] = ..., product_name: _Optional[str] = ..., units: _Optional[int] = ..., revenue_cents: _Optional[int] = ..., gross_profit_cents: _Optional[int] = ...) -> None: ...

class AnalyticsTopClient(_message.Message):
    __slots__ = ("client_id", "nickname", "played_minutes", "session_spend_cents", "product_spend_cents", "product_units", "session_count")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PLAYED_MINUTES_FIELD_NUMBER: _ClassVar[int]
    SESSION_SPEND_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_SPEND_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_UNITS_FIELD_NUMBER: _ClassVar[int]
    SESSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    nickname: str
    played_minutes: int
    session_spend_cents: int
    product_spend_cents: int
    product_units: int
    session_count: int
    def __init__(self, client_id: _Optional[str] = ..., nickname: _Optional[str] = ..., played_minutes: _Optional[int] = ..., session_spend_cents: _Optional[int] = ..., product_spend_cents: _Optional[int] = ..., product_units: _Optional[int] = ..., session_count: _Optional[int] = ...) -> None: ...

class AnalyticsBucket(_message.Message):
    __slots__ = ("key", "label", "session_revenue_cents", "product_revenue_cents", "total_revenue_cents", "session_count", "product_sale_count", "product_units", "played_minutes", "guest_session_count")
    KEY_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    SESSION_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    SESSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_SALE_COUNT_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_UNITS_FIELD_NUMBER: _ClassVar[int]
    PLAYED_MINUTES_FIELD_NUMBER: _ClassVar[int]
    GUEST_SESSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    key: str
    label: str
    session_revenue_cents: int
    product_revenue_cents: int
    total_revenue_cents: int
    session_count: int
    product_sale_count: int
    product_units: int
    played_minutes: int
    guest_session_count: int
    def __init__(self, key: _Optional[str] = ..., label: _Optional[str] = ..., session_revenue_cents: _Optional[int] = ..., product_revenue_cents: _Optional[int] = ..., total_revenue_cents: _Optional[int] = ..., session_count: _Optional[int] = ..., product_sale_count: _Optional[int] = ..., product_units: _Optional[int] = ..., played_minutes: _Optional[int] = ..., guest_session_count: _Optional[int] = ...) -> None: ...

class AnalyticsBreakdown(_message.Message):
    __slots__ = ("key", "label", "session_revenue_cents", "product_revenue_cents", "revenue_cents", "product_cost_cents", "gross_profit_cents", "session_count", "product_sale_count", "product_units", "played_minutes", "share_bps", "discount_cents")
    KEY_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    SESSION_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_COST_CENTS_FIELD_NUMBER: _ClassVar[int]
    GROSS_PROFIT_CENTS_FIELD_NUMBER: _ClassVar[int]
    SESSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_SALE_COUNT_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_UNITS_FIELD_NUMBER: _ClassVar[int]
    PLAYED_MINUTES_FIELD_NUMBER: _ClassVar[int]
    SHARE_BPS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    key: str
    label: str
    session_revenue_cents: int
    product_revenue_cents: int
    revenue_cents: int
    product_cost_cents: int
    gross_profit_cents: int
    session_count: int
    product_sale_count: int
    product_units: int
    played_minutes: int
    share_bps: int
    discount_cents: int
    def __init__(self, key: _Optional[str] = ..., label: _Optional[str] = ..., session_revenue_cents: _Optional[int] = ..., product_revenue_cents: _Optional[int] = ..., revenue_cents: _Optional[int] = ..., product_cost_cents: _Optional[int] = ..., gross_profit_cents: _Optional[int] = ..., session_count: _Optional[int] = ..., product_sale_count: _Optional[int] = ..., product_units: _Optional[int] = ..., played_minutes: _Optional[int] = ..., share_bps: _Optional[int] = ..., discount_cents: _Optional[int] = ...) -> None: ...

class AnalyticsPayment(_message.Message):
    __slots__ = ("key", "label", "revenue_cents", "operation_count", "share_bps")
    KEY_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    OPERATION_COUNT_FIELD_NUMBER: _ClassVar[int]
    SHARE_BPS_FIELD_NUMBER: _ClassVar[int]
    key: str
    label: str
    revenue_cents: int
    operation_count: int
    share_bps: int
    def __init__(self, key: _Optional[str] = ..., label: _Optional[str] = ..., revenue_cents: _Optional[int] = ..., operation_count: _Optional[int] = ..., share_bps: _Optional[int] = ...) -> None: ...

class AnalyticsOverview(_message.Message):
    __slots__ = ("start_at", "end_at", "session_revenue_cents", "product_revenue_cents", "total_revenue_cents", "session_count", "product_sale_count", "product_units", "played_minutes", "guest_session_count", "client_count", "top_products", "top_clients", "product_cost_cents", "gross_profit_cents", "discount_cents", "active_client_count", "new_client_count", "returning_client_count", "unique_visitor_count", "workstation_count", "occupancy_percent", "peak_usage_hour", "daily_activity", "hourly_activity", "zones", "workstations", "tariffs", "payment_methods", "product_categories")
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    SESSION_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    SESSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_SALE_COUNT_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_UNITS_FIELD_NUMBER: _ClassVar[int]
    PLAYED_MINUTES_FIELD_NUMBER: _ClassVar[int]
    GUEST_SESSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    CLIENT_COUNT_FIELD_NUMBER: _ClassVar[int]
    TOP_PRODUCTS_FIELD_NUMBER: _ClassVar[int]
    TOP_CLIENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_COST_CENTS_FIELD_NUMBER: _ClassVar[int]
    GROSS_PROFIT_CENTS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_CLIENT_COUNT_FIELD_NUMBER: _ClassVar[int]
    NEW_CLIENT_COUNT_FIELD_NUMBER: _ClassVar[int]
    RETURNING_CLIENT_COUNT_FIELD_NUMBER: _ClassVar[int]
    UNIQUE_VISITOR_COUNT_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_COUNT_FIELD_NUMBER: _ClassVar[int]
    OCCUPANCY_PERCENT_FIELD_NUMBER: _ClassVar[int]
    PEAK_USAGE_HOUR_FIELD_NUMBER: _ClassVar[int]
    DAILY_ACTIVITY_FIELD_NUMBER: _ClassVar[int]
    HOURLY_ACTIVITY_FIELD_NUMBER: _ClassVar[int]
    ZONES_FIELD_NUMBER: _ClassVar[int]
    WORKSTATIONS_FIELD_NUMBER: _ClassVar[int]
    TARIFFS_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_METHODS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    session_revenue_cents: int
    product_revenue_cents: int
    total_revenue_cents: int
    session_count: int
    product_sale_count: int
    product_units: int
    played_minutes: int
    guest_session_count: int
    client_count: int
    top_products: _containers.RepeatedCompositeFieldContainer[AnalyticsTopProduct]
    top_clients: _containers.RepeatedCompositeFieldContainer[AnalyticsTopClient]
    product_cost_cents: int
    gross_profit_cents: int
    discount_cents: int
    active_client_count: int
    new_client_count: int
    returning_client_count: int
    unique_visitor_count: int
    workstation_count: int
    occupancy_percent: float
    peak_usage_hour: str
    daily_activity: _containers.RepeatedCompositeFieldContainer[AnalyticsBucket]
    hourly_activity: _containers.RepeatedCompositeFieldContainer[AnalyticsBucket]
    zones: _containers.RepeatedCompositeFieldContainer[AnalyticsBreakdown]
    workstations: _containers.RepeatedCompositeFieldContainer[AnalyticsBreakdown]
    tariffs: _containers.RepeatedCompositeFieldContainer[AnalyticsBreakdown]
    payment_methods: _containers.RepeatedCompositeFieldContainer[AnalyticsPayment]
    product_categories: _containers.RepeatedCompositeFieldContainer[AnalyticsBreakdown]
    def __init__(self, start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., session_revenue_cents: _Optional[int] = ..., product_revenue_cents: _Optional[int] = ..., total_revenue_cents: _Optional[int] = ..., session_count: _Optional[int] = ..., product_sale_count: _Optional[int] = ..., product_units: _Optional[int] = ..., played_minutes: _Optional[int] = ..., guest_session_count: _Optional[int] = ..., client_count: _Optional[int] = ..., top_products: _Optional[_Iterable[_Union[AnalyticsTopProduct, _Mapping]]] = ..., top_clients: _Optional[_Iterable[_Union[AnalyticsTopClient, _Mapping]]] = ..., product_cost_cents: _Optional[int] = ..., gross_profit_cents: _Optional[int] = ..., discount_cents: _Optional[int] = ..., active_client_count: _Optional[int] = ..., new_client_count: _Optional[int] = ..., returning_client_count: _Optional[int] = ..., unique_visitor_count: _Optional[int] = ..., workstation_count: _Optional[int] = ..., occupancy_percent: _Optional[float] = ..., peak_usage_hour: _Optional[str] = ..., daily_activity: _Optional[_Iterable[_Union[AnalyticsBucket, _Mapping]]] = ..., hourly_activity: _Optional[_Iterable[_Union[AnalyticsBucket, _Mapping]]] = ..., zones: _Optional[_Iterable[_Union[AnalyticsBreakdown, _Mapping]]] = ..., workstations: _Optional[_Iterable[_Union[AnalyticsBreakdown, _Mapping]]] = ..., tariffs: _Optional[_Iterable[_Union[AnalyticsBreakdown, _Mapping]]] = ..., payment_methods: _Optional[_Iterable[_Union[AnalyticsPayment, _Mapping]]] = ..., product_categories: _Optional[_Iterable[_Union[AnalyticsBreakdown, _Mapping]]] = ...) -> None: ...

class ClientAnalytics(_message.Message):
    __slots__ = ("client_id", "nickname", "phone", "start_at", "end_at", "played_minutes", "session_count", "session_spend_cents", "product_spend_cents", "product_units", "first_session_at", "last_session_at", "last_purchase_at", "favorite_products", "product_cost_cents", "daily_activity", "payment_methods")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    PLAYED_MINUTES_FIELD_NUMBER: _ClassVar[int]
    SESSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    SESSION_SPEND_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_SPEND_CENTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_UNITS_FIELD_NUMBER: _ClassVar[int]
    FIRST_SESSION_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_SESSION_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_PURCHASE_AT_FIELD_NUMBER: _ClassVar[int]
    FAVORITE_PRODUCTS_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_COST_CENTS_FIELD_NUMBER: _ClassVar[int]
    DAILY_ACTIVITY_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_METHODS_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    nickname: str
    phone: str
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    played_minutes: int
    session_count: int
    session_spend_cents: int
    product_spend_cents: int
    product_units: int
    first_session_at: _timestamp_pb2.Timestamp
    last_session_at: _timestamp_pb2.Timestamp
    last_purchase_at: _timestamp_pb2.Timestamp
    favorite_products: _containers.RepeatedCompositeFieldContainer[AnalyticsTopProduct]
    product_cost_cents: int
    daily_activity: _containers.RepeatedCompositeFieldContainer[AnalyticsBucket]
    payment_methods: _containers.RepeatedCompositeFieldContainer[AnalyticsPayment]
    def __init__(self, client_id: _Optional[str] = ..., nickname: _Optional[str] = ..., phone: _Optional[str] = ..., start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., played_minutes: _Optional[int] = ..., session_count: _Optional[int] = ..., session_spend_cents: _Optional[int] = ..., product_spend_cents: _Optional[int] = ..., product_units: _Optional[int] = ..., first_session_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_session_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_purchase_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., favorite_products: _Optional[_Iterable[_Union[AnalyticsTopProduct, _Mapping]]] = ..., product_cost_cents: _Optional[int] = ..., daily_activity: _Optional[_Iterable[_Union[AnalyticsBucket, _Mapping]]] = ..., payment_methods: _Optional[_Iterable[_Union[AnalyticsPayment, _Mapping]]] = ...) -> None: ...
