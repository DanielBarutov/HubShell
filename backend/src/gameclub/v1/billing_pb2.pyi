import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SessionCharge(_message.Message):
    __slots__ = ("id", "session_id", "client_id", "balance_operation_id", "tariff_id", "duration_minutes", "amount_cents", "amount_before_discount_cents", "discount_amount_cents", "discount_percent_bps", "discount_category", "charged_by", "idempotency_key", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    BALANCE_OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_BEFORE_DISCOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_PERCENT_BPS_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    CHARGED_BY_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    session_id: str
    client_id: str
    balance_operation_id: str
    tariff_id: str
    duration_minutes: int
    amount_cents: int
    amount_before_discount_cents: int
    discount_amount_cents: int
    discount_percent_bps: int
    discount_category: str
    charged_by: str
    idempotency_key: str
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., session_id: _Optional[str] = ..., client_id: _Optional[str] = ..., balance_operation_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., amount_cents: _Optional[int] = ..., amount_before_discount_cents: _Optional[int] = ..., discount_amount_cents: _Optional[int] = ..., discount_percent_bps: _Optional[int] = ..., discount_category: _Optional[str] = ..., charged_by: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ChargeSessionRequest(_message.Message):
    __slots__ = ("session_id", "idempotency_key")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    idempotency_key: str
    def __init__(self, session_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class GetSessionChargeRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class GetRevenueRequest(_message.Message):
    __slots__ = ("start_at", "end_at")
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    def __init__(self, start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class RevenueSummary(_message.Message):
    __slots__ = ("start_at", "end_at", "amount_cents", "charge_count")
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    CHARGE_COUNT_FIELD_NUMBER: _ClassVar[int]
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    amount_cents: int
    charge_count: int
    def __init__(self, start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., amount_cents: _Optional[int] = ..., charge_count: _Optional[int] = ...) -> None: ...
