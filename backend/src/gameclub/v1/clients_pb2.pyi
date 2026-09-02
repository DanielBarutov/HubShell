import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Client(_message.Message):
    __slots__ = ("id", "nickname", "phone", "discount_category", "balance_cents", "balance_bonus", "created_at", "updated_at", "blocked_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    BALANCE_BONUS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    BLOCKED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    nickname: str
    phone: str
    discount_category: str
    balance_cents: int
    balance_bonus: int
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    blocked_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., nickname: _Optional[str] = ..., phone: _Optional[str] = ..., discount_category: _Optional[str] = ..., balance_cents: _Optional[int] = ..., balance_bonus: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., blocked_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateClientRequest(_message.Message):
    __slots__ = ("nickname", "phone", "discount_category")
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    nickname: str
    phone: str
    discount_category: str
    def __init__(self, nickname: _Optional[str] = ..., phone: _Optional[str] = ..., discount_category: _Optional[str] = ...) -> None: ...

class SearchClientsRequest(_message.Message):
    __slots__ = ("query", "field")
    class Field(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        FIELD_UNSPECIFIED: _ClassVar[SearchClientsRequest.Field]
        FIELD_NICKNAME: _ClassVar[SearchClientsRequest.Field]
        FIELD_PHONE: _ClassVar[SearchClientsRequest.Field]
    FIELD_UNSPECIFIED: SearchClientsRequest.Field
    FIELD_NICKNAME: SearchClientsRequest.Field
    FIELD_PHONE: SearchClientsRequest.Field
    QUERY_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    query: str
    field: SearchClientsRequest.Field
    def __init__(self, query: _Optional[str] = ..., field: _Optional[_Union[SearchClientsRequest.Field, str]] = ...) -> None: ...

class SearchClientsResponse(_message.Message):
    __slots__ = ("clients",)
    CLIENTS_FIELD_NUMBER: _ClassVar[int]
    clients: _containers.RepeatedCompositeFieldContainer[Client]
    def __init__(self, clients: _Optional[_Iterable[_Union[Client, _Mapping]]] = ...) -> None: ...

class GetClientRequest(_message.Message):
    __slots__ = ("client_id",)
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    def __init__(self, client_id: _Optional[str] = ...) -> None: ...

class TopUpRequest(_message.Message):
    __slots__ = ("client_id", "amount_cents", "bonus_amount", "reason", "idempotency_key")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    amount_cents: int
    bonus_amount: int
    reason: str
    idempotency_key: str
    def __init__(self, client_id: _Optional[str] = ..., amount_cents: _Optional[int] = ..., bonus_amount: _Optional[int] = ..., reason: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class TopUpResponse(_message.Message):
    __slots__ = ("client", "operation_id", "idempotency_key")
    CLIENT_FIELD_NUMBER: _ClassVar[int]
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    client: Client
    operation_id: str
    idempotency_key: str
    def __init__(self, client: _Optional[_Union[Client, _Mapping]] = ..., operation_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class BalanceOperation(_message.Message):
    __slots__ = ("id", "client_id", "operation_type", "amount_cents", "bonus_amount", "reason", "actor_id", "idempotency_key", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    ACTOR_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    client_id: str
    operation_type: str
    amount_cents: int
    bonus_amount: int
    reason: str
    actor_id: str
    idempotency_key: str
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., client_id: _Optional[str] = ..., operation_type: _Optional[str] = ..., amount_cents: _Optional[int] = ..., bonus_amount: _Optional[int] = ..., reason: _Optional[str] = ..., actor_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ListBalanceOperationsRequest(_message.Message):
    __slots__ = ("client_id", "limit")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    limit: int
    def __init__(self, client_id: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class ListBalanceOperationsResponse(_message.Message):
    __slots__ = ("operations",)
    OPERATIONS_FIELD_NUMBER: _ClassVar[int]
    operations: _containers.RepeatedCompositeFieldContainer[BalanceOperation]
    def __init__(self, operations: _Optional[_Iterable[_Union[BalanceOperation, _Mapping]]] = ...) -> None: ...

class Guest(_message.Message):
    __slots__ = ("id", "nickname", "phone", "discount_category", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    nickname: str
    phone: str
    discount_category: str
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., nickname: _Optional[str] = ..., phone: _Optional[str] = ..., discount_category: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateGuestRequest(_message.Message):
    __slots__ = ("nickname", "phone", "discount_category")
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    nickname: str
    phone: str
    discount_category: str
    def __init__(self, nickname: _Optional[str] = ..., phone: _Optional[str] = ..., discount_category: _Optional[str] = ...) -> None: ...

class SearchGuestsRequest(_message.Message):
    __slots__ = ("query", "field")
    class Field(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        FIELD_UNSPECIFIED: _ClassVar[SearchGuestsRequest.Field]
        FIELD_NICKNAME: _ClassVar[SearchGuestsRequest.Field]
        FIELD_PHONE: _ClassVar[SearchGuestsRequest.Field]
    FIELD_UNSPECIFIED: SearchGuestsRequest.Field
    FIELD_NICKNAME: SearchGuestsRequest.Field
    FIELD_PHONE: SearchGuestsRequest.Field
    QUERY_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    query: str
    field: SearchGuestsRequest.Field
    def __init__(self, query: _Optional[str] = ..., field: _Optional[_Union[SearchGuestsRequest.Field, str]] = ...) -> None: ...

class SearchGuestsResponse(_message.Message):
    __slots__ = ("guests",)
    GUESTS_FIELD_NUMBER: _ClassVar[int]
    guests: _containers.RepeatedCompositeFieldContainer[Guest]
    def __init__(self, guests: _Optional[_Iterable[_Union[Guest, _Mapping]]] = ...) -> None: ...

class GetGuestRequest(_message.Message):
    __slots__ = ("guest_id",)
    GUEST_ID_FIELD_NUMBER: _ClassVar[int]
    guest_id: str
    def __init__(self, guest_id: _Optional[str] = ...) -> None: ...

class ListGuestsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListGuestsResponse(_message.Message):
    __slots__ = ("guests",)
    GUESTS_FIELD_NUMBER: _ClassVar[int]
    guests: _containers.RepeatedCompositeFieldContainer[Guest]
    def __init__(self, guests: _Optional[_Iterable[_Union[Guest, _Mapping]]] = ...) -> None: ...

class RegisterPortalRequest(_message.Message):
    __slots__ = ("nickname", "phone", "pin", "device_id")
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    PIN_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    nickname: str
    phone: str
    pin: str
    device_id: str
    def __init__(self, nickname: _Optional[str] = ..., phone: _Optional[str] = ..., pin: _Optional[str] = ..., device_id: _Optional[str] = ...) -> None: ...

class LoginPortalRequest(_message.Message):
    __slots__ = ("identifier", "pin", "device_id")
    IDENTIFIER_FIELD_NUMBER: _ClassVar[int]
    PIN_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    identifier: str
    pin: str
    device_id: str
    def __init__(self, identifier: _Optional[str] = ..., pin: _Optional[str] = ..., device_id: _Optional[str] = ...) -> None: ...

class GetPortalRequest(_message.Message):
    __slots__ = ("device_id", "limit")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    limit: int
    def __init__(self, device_id: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class ClientPortalSession(_message.Message):
    __slots__ = ("access_token", "expires_in", "snapshot")
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_IN_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    access_token: str
    expires_in: int
    snapshot: ClientPortalSnapshot
    def __init__(self, access_token: _Optional[str] = ..., expires_in: _Optional[int] = ..., snapshot: _Optional[_Union[ClientPortalSnapshot, _Mapping]] = ...) -> None: ...

class ClientPortalSnapshot(_message.Message):
    __slots__ = ("client", "balance_operations", "sessions", "charges", "purchases", "available_time_minutes")
    CLIENT_FIELD_NUMBER: _ClassVar[int]
    BALANCE_OPERATIONS_FIELD_NUMBER: _ClassVar[int]
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    CHARGES_FIELD_NUMBER: _ClassVar[int]
    PURCHASES_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_TIME_MINUTES_FIELD_NUMBER: _ClassVar[int]
    client: Client
    balance_operations: _containers.RepeatedCompositeFieldContainer[PortalBalanceOperation]
    sessions: _containers.RepeatedCompositeFieldContainer[PortalSession]
    charges: _containers.RepeatedCompositeFieldContainer[PortalCharge]
    purchases: _containers.RepeatedCompositeFieldContainer[PortalPurchase]
    available_time_minutes: int
    def __init__(self, client: _Optional[_Union[Client, _Mapping]] = ..., balance_operations: _Optional[_Iterable[_Union[PortalBalanceOperation, _Mapping]]] = ..., sessions: _Optional[_Iterable[_Union[PortalSession, _Mapping]]] = ..., charges: _Optional[_Iterable[_Union[PortalCharge, _Mapping]]] = ..., purchases: _Optional[_Iterable[_Union[PortalPurchase, _Mapping]]] = ..., available_time_minutes: _Optional[int] = ...) -> None: ...

class PortalBalanceOperation(_message.Message):
    __slots__ = ("id", "operation_type", "amount_cents", "bonus_amount", "reason", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    operation_type: str
    amount_cents: int
    bonus_amount: int
    reason: str
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., operation_type: _Optional[str] = ..., amount_cents: _Optional[int] = ..., bonus_amount: _Optional[int] = ..., reason: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class PortalSession(_message.Message):
    __slots__ = ("id", "workstation_id", "status", "started_at", "ended_at", "tariff_id", "tariff_quantity", "tariff_name")
    ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    ENDED_AT_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    TARIFF_NAME_FIELD_NUMBER: _ClassVar[int]
    id: str
    workstation_id: str
    status: str
    started_at: _timestamp_pb2.Timestamp
    ended_at: _timestamp_pb2.Timestamp
    tariff_id: str
    tariff_quantity: int
    tariff_name: str
    def __init__(self, id: _Optional[str] = ..., workstation_id: _Optional[str] = ..., status: _Optional[str] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., ended_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., tariff_id: _Optional[str] = ..., tariff_quantity: _Optional[int] = ..., tariff_name: _Optional[str] = ...) -> None: ...

class PortalCharge(_message.Message):
    __slots__ = ("id", "session_id", "tariff_id", "duration_minutes", "amount_cents", "created_at", "tariff_name")
    ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    TARIFF_NAME_FIELD_NUMBER: _ClassVar[int]
    id: str
    session_id: str
    tariff_id: str
    duration_minutes: int
    amount_cents: int
    created_at: _timestamp_pb2.Timestamp
    tariff_name: str
    def __init__(self, id: _Optional[str] = ..., session_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., amount_cents: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., tariff_name: _Optional[str] = ...) -> None: ...

class PortalPurchase(_message.Message):
    __slots__ = ("id", "product_name", "quantity", "total_price_cents", "payment_method", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_NAME_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_METHOD_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    product_name: str
    quantity: int
    total_price_cents: int
    payment_method: str
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., product_name: _Optional[str] = ..., quantity: _Optional[int] = ..., total_price_cents: _Optional[int] = ..., payment_method: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
